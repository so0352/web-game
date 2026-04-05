import hashlib
import hmac
import os
import threading
import time
import uuid

from flask import request
from flask_socketio import emit, join_room
from werkzeug.security import check_password_hash, generate_password_hash

from game_logic import Player
from game_store import (
    build_game_state_payload,
    cleanup_game,
    create_game_state,
    detach_client_game,
    ensure_ai_settings,
    get_game_entry,
    register_client_game,
    set_game_entry,
    update_game_meta,
)
from handlers.shogi_ai_support import start_shogi_ai_turns_if_needed

_MATCH_LOCK = threading.Lock()
WAITING_QUEUES = {}
MATCH_SESSIONS = {}
ROLE_CHOICE_TIMEOUT_SECONDS = 15
RECONNECT_GRACE_SECONDS = 30
_PASSWORD_PEPPER = os.environ.get("MATCH_PASSWORD_PEPPER") or os.environ.get(
    "SECRET_KEY", ""
)


def reset_matchmaking_state():
    with _MATCH_LOCK:
        WAITING_QUEUES.clear()
        MATCH_SESSIONS.clear()


def _normalize_game_type(game_type):
    return "shogi" if game_type == "shogi" else "othello"


def _now():
    return time.time()


def _queue_key(game_type, password):
    return (_normalize_game_type(game_type), password)


def _fingerprint_password(password):
    key = (_PASSWORD_PEPPER or "othello-matchmaking-pepper").encode("utf-8")
    message = str(password or "").encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _build_waiting_entry(sid, player_name, game_type, password_fingerprint):
    return {
        "sid": sid,
        "player_name": player_name,
        "game_type": _normalize_game_type(game_type),
        "password_fingerprint": password_fingerprint,
        "created_at": _now(),
    }


def _remove_waiting_sid_locked(sid):
    removed = False
    empty_keys = []
    for key, queue in WAITING_QUEUES.items():
        new_queue = [entry for entry in queue if entry["sid"] != sid]
        if len(new_queue) != len(queue):
            removed = True
        if new_queue:
            WAITING_QUEUES[key] = new_queue
        else:
            empty_keys.append(key)
    for key in empty_keys:
        WAITING_QUEUES.pop(key, None)
    return removed


def _find_session_by_sid_locked(sid):
    for session in MATCH_SESSIONS.values():
        if session["creator"]["sid"] == sid:
            return session, "creator"
        if session["guest"]["sid"] == sid:
            return session, "guest"
    return None, None


def _find_reconnect_target_locked(player_name, game_type, password, password_fingerprint):
    now = _now()
    normalized_game_type = _normalize_game_type(game_type)
    for session in MATCH_SESSIONS.values():
        if session["game_type"] != normalized_game_type:
            continue
        if session.get("password_fingerprint") != password_fingerprint:
            continue
        if not check_password_hash(session.get("password_hash", ""), password):
            continue
        for slot in ("creator", "guest"):
            participant = session[slot]
            if participant["player_name"] != player_name:
                continue
            deadline = participant.get("reconnect_deadline")
            if participant["connected"]:
                continue
            if deadline is None or deadline < now:
                continue
            return session, slot
    return None, None


def _public_role_name(game_type, seat):
    if _normalize_game_type(game_type) == "othello":
        return "black" if seat == "first" else "white"
    return "sente" if seat == "first" else "gote"


def _current_player_from_creator_choice(game_type, creator_choice):
    # first always starts. For othello first=black(1), second=white(2).
    if _normalize_game_type(game_type) == "othello":
        return Player.BLACK if creator_choice == "first" else Player.WHITE
    return 1


def get_multiplayer_slot(game_id, sid):
    with _MATCH_LOCK:
        session = MATCH_SESSIONS.get(game_id)
        if session is None:
            return None, None
        if session["creator"]["sid"] == sid:
            return "creator", session
        if session["guest"]["sid"] == sid:
            return "guest", session
        return None, session


def _seat_by_slot(creator_choice):
    if creator_choice == "second":
        return {"creator": "second", "guest": "first"}
    return {"creator": "first", "guest": "second"}


def _emit_role_assigned(socketio, session):
    game_type = session["game_type"]
    seat_map = session["seat_by_slot"]

    for slot in ("creator", "guest"):
        participant = session[slot]
        sid = participant["sid"]
        your_seat = seat_map[slot]
        opponent_slot = "guest" if slot == "creator" else "creator"
        opponent_name = session[opponent_slot]["player_name"]
        socketio.emit(
            "role_assigned",
            {
                "game_id": session["game_id"],
                "game_type": game_type,
                "your_seat": your_seat,
                "your_role": _public_role_name(game_type, your_seat),
                "opponent_name": opponent_name,
            },
            room=sid,
        )


def _emit_game_state(socketio, session):
    game_type, game_state_obj = get_game_entry(session["game_id"])
    if game_state_obj is None:
        return

    payload = build_game_state_payload(game_type, game_state_obj)
    socketio.emit("game_state", payload, room=session["game_id"])
    socketio.emit("game_state", payload, room=session["creator"]["sid"])
    socketio.emit("game_state", payload, room=session["guest"]["sid"])


def _activate_roles_locked(socketio, session, creator_choice):
    if creator_choice not in {"first", "second"}:
        creator_choice = "first"

    seat_map = _seat_by_slot(creator_choice)
    session["seat_by_slot"] = seat_map
    session["status"] = "active"

    game_type, game_state_obj = get_game_entry(session["game_id"])
    if game_state_obj is not None:
        if game_type == "othello":
            # black always starts in othello.
            game_state_obj.current_player = Player.BLACK
        else:
            game_state_obj.current_player = 1

    _emit_role_assigned(socketio, session)
    _emit_game_state(socketio, session)

    if game_type == "shogi":
        start_shogi_ai_turns_if_needed(socketio, session["game_id"], max_turns=40)


def _remove_session_locked(game_id):
    session = MATCH_SESSIONS.pop(game_id, None)
    if session is None:
        return

    for slot in ("creator", "guest"):
        sid = session[slot]["sid"]
        detach_client_game(sid, allow_cleanup=False)

    cleanup_game(game_id)


def _start_role_choice_timeout(socketio, game_id):
    def finalize_if_pending():
        with _MATCH_LOCK:
            session = MATCH_SESSIONS.get(game_id)
            if session is None:
                return
            if session["status"] != "pending_role":
                return
            _activate_roles_locked(socketio, session, "first")

    timer = threading.Timer(ROLE_CHOICE_TIMEOUT_SECONDS, finalize_if_pending)
    timer.daemon = True
    timer.start()


def _start_disconnect_timeout(socketio, game_id, slot, sid_snapshot):
    def finalize_if_missing():
        with _MATCH_LOCK:
            session = MATCH_SESSIONS.get(game_id)
            if session is None:
                return
            participant = session.get(slot)
            if participant is None:
                return
            if participant["sid"] != sid_snapshot:
                return
            if participant["connected"]:
                return
            deadline = participant.get("reconnect_deadline")
            if deadline is None or deadline > _now():
                return

            opponent_slot = "guest" if slot == "creator" else "creator"
            opponent_sid = session[opponent_slot]["sid"]
            socketio.emit(
                "match_ended",
                {
                    "reason": "reconnect_timeout",
                    "message": "相手の再接続待機時間(30秒)が過ぎたため対局を終了しました。",
                },
                room=opponent_sid,
            )
            _remove_session_locked(game_id)

    timer = threading.Timer(RECONNECT_GRACE_SECONDS + 0.5, finalize_if_missing)
    timer.daemon = True
    timer.start()


def handle_disconnect(socketio, sid):
    with _MATCH_LOCK:
        session, slot = _find_session_by_sid_locked(sid)
        _remove_waiting_sid_locked(sid)

        if session is None:
            return False

        participant = session[slot]
        participant["connected"] = False
        participant["reconnect_deadline"] = _now() + RECONNECT_GRACE_SECONDS

        opponent_slot = "guest" if slot == "creator" else "creator"
        opponent_sid = session[opponent_slot]["sid"]
        socketio.emit(
            "opponent_disconnected",
            {
                "message": "相手が切断しました。30秒待機して再接続を待ちます。",
                "reconnect_seconds": RECONNECT_GRACE_SECONDS,
            },
            room=opponent_sid,
        )

        _start_disconnect_timeout(socketio, session["game_id"], slot, sid)
        return True


def register_matchmaking_handlers(socketio):
    @socketio.on("start_matchmaking")
    def handle_start_matchmaking(data):
        player_name = str(data.get("player_name") or "").strip()
        password = str(data.get("password") or "").strip()
        game_type = _normalize_game_type(data.get("game_type", "othello"))
        password_fingerprint = _fingerprint_password(password)

        if len(player_name) < 1:
            emit(
                "match_error",
                {"message": "プレイヤー名を入力してください"},
                room=request.sid,
            )
            return
        if len(password) < 1:
            emit(
                "match_error", {"message": "合言葉を入力してください"}, room=request.sid
            )
            return

        with _MATCH_LOCK:
            _remove_waiting_sid_locked(request.sid)

            reconnect_session, reconnect_slot = _find_reconnect_target_locked(
                player_name, game_type, password, password_fingerprint
            )
            if reconnect_session is not None:
                reconnect_session[reconnect_slot]["sid"] = request.sid
                reconnect_session[reconnect_slot]["connected"] = True
                reconnect_session[reconnect_slot]["reconnect_deadline"] = None

                join_room(reconnect_session["game_id"])
                register_client_game(request.sid, reconnect_session["game_id"])

                emit(
                    "match_found",
                    {
                        "game_id": reconnect_session["game_id"],
                        "game_type": reconnect_session["game_type"],
                        "is_creator": reconnect_slot == "creator",
                        "reconnected": True,
                        "opponent_name": reconnect_session[
                            "guest" if reconnect_slot == "creator" else "creator"
                        ]["player_name"],
                    },
                    room=request.sid,
                )

                if reconnect_session["status"] == "pending_role":
                    if reconnect_slot == "creator":
                        emit(
                            "role_choice_required",
                            {
                                "game_id": reconnect_session["game_id"],
                                "timeout_seconds": ROLE_CHOICE_TIMEOUT_SECONDS,
                            },
                            room=request.sid,
                        )
                    else:
                        emit(
                            "role_waiting",
                            {"message": "部屋作成者が先攻/後攻を選択中です..."},
                            room=request.sid,
                        )
                else:
                    _emit_role_assigned(socketio, reconnect_session)
                    _emit_game_state(socketio, reconnect_session)

                emit(
                    "opponent_reconnected",
                    {"message": "相手が再接続しました。対局を再開します。"},
                    room=reconnect_session[
                        "guest" if reconnect_slot == "creator" else "creator"
                    ]["sid"],
                )
                return

            key = _queue_key(game_type, password_fingerprint)
            queue = WAITING_QUEUES.setdefault(key, [])
            if queue:
                creator_entry = queue.pop(0)
                if not queue:
                    WAITING_QUEUES.pop(key, None)

                game_id = f"{game_type}-match-{uuid.uuid4().hex[:10]}"
                game_state = create_game_state(game_type)
                set_game_entry(game_id, game_type, game_state)
                update_game_meta(game_id, {"mode": "multiplayer"})
                ensure_ai_settings(game_id)

                guest_entry = _build_waiting_entry(
                    request.sid, player_name, game_type, password_fingerprint
                )

                session = {
                    "game_id": game_id,
                    "game_type": game_type,
                    "password_hash": generate_password_hash(password),
                    "password_fingerprint": password_fingerprint,
                    "status": "pending_role",
                    "creator": {
                        "sid": creator_entry["sid"],
                        "player_name": creator_entry["player_name"],
                        "connected": True,
                        "reconnect_deadline": None,
                    },
                    "guest": {
                        "sid": guest_entry["sid"],
                        "player_name": guest_entry["player_name"],
                        "connected": True,
                        "reconnect_deadline": None,
                    },
                    "seat_by_slot": None,
                    "created_at": _now(),
                }
                MATCH_SESSIONS[game_id] = session

                join_room(game_id)
                register_client_game(request.sid, game_id)
                socketio.server.enter_room(creator_entry["sid"], game_id)
                register_client_game(creator_entry["sid"], game_id)

                emit(
                    "match_found",
                    {
                        "game_id": game_id,
                        "game_type": game_type,
                        "is_creator": True,
                        "opponent_name": guest_entry["player_name"],
                    },
                    room=creator_entry["sid"],
                )
                emit(
                    "match_found",
                    {
                        "game_id": game_id,
                        "game_type": game_type,
                        "is_creator": False,
                        "opponent_name": creator_entry["player_name"],
                    },
                    room=request.sid,
                )

                emit(
                    "role_choice_required",
                    {
                        "game_id": game_id,
                        "timeout_seconds": ROLE_CHOICE_TIMEOUT_SECONDS,
                    },
                    room=creator_entry["sid"],
                )
                emit(
                    "role_waiting",
                    {"message": "部屋作成者が先攻/後攻を選択中です..."},
                    room=request.sid,
                )

                _start_role_choice_timeout(socketio, game_id)
                return

            queue.append(
                _build_waiting_entry(
                    request.sid, player_name, game_type, password_fingerprint
                )
            )
            emit(
                "matchmaking_status",
                {"status": "waiting", "message": "相手を待っています..."},
                room=request.sid,
            )

    @socketio.on("cancel_matchmaking")
    def handle_cancel_matchmaking(_data):
        with _MATCH_LOCK:
            removed = _remove_waiting_sid_locked(request.sid)

        if removed:
            emit(
                "matchmaking_status",
                {
                    "status": "cancelled",
                    "message": "マッチング待機をキャンセルしました。",
                },
                room=request.sid,
            )
        else:
            emit(
                "matchmaking_status",
                {"status": "idle", "message": "現在待機中ではありません。"},
                room=request.sid,
            )

    @socketio.on("choose_role_after_match")
    def handle_choose_role_after_match(data):
        game_id = str(data.get("game_id") or "")
        creator_choice = str(data.get("role") or "first")

        with _MATCH_LOCK:
            session = MATCH_SESSIONS.get(game_id)
            if session is None:
                emit(
                    "match_error",
                    {"message": "対局セッションが見つかりません"},
                    room=request.sid,
                )
                return
            if session["status"] != "pending_role":
                emit(
                    "match_error",
                    {"message": "先攻/後攻はすでに確定しています"},
                    room=request.sid,
                )
                return
            if session["creator"]["sid"] != request.sid:
                emit(
                    "match_error",
                    {"message": "部屋作成者のみ選択できます"},
                    room=request.sid,
                )
                return

            _activate_roles_locked(socketio, session, creator_choice)
