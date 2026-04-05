import re

from flask import request
from flask_socketio import emit, join_room

from game_store import (
    build_game_state_payload,
    create_game_state,
    ensure_ai_settings,
    get_game_entry,
    get_game_meta,
    get_game_mode,
    register_client_game,
    set_game_entry,
)
from handlers.matchmaking_handlers import get_multiplayer_slot
from handlers.shogi_ai_support import start_shogi_ai_turns_if_needed


_GAME_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _parse_game_id(data):
    raw_game_id = str((data or {}).get("game_id") or "default").strip()
    if _GAME_ID_PATTERN.fullmatch(raw_game_id):
        return raw_game_id, None
    return None, "不正な game_id です"


def register_game_handlers(socketio):
    @socketio.on("create_game")
    def handle_create_game(data):
        game_id, error_message = _parse_game_id(data)
        if error_message:
            emit("error", {"message": error_message}, room=request.sid)
            return
        game_type = data.get("game_type", "othello")
        mode = data.get("mode", "singleplayer")

        _existing_type, existing_state = get_game_entry(game_id)
        if existing_state is not None:
            existing_mode = get_game_mode(game_id)
            if existing_mode == "multiplayer":
                slot, _session = get_multiplayer_slot(game_id, request.sid)
                if slot != "creator":
                    emit(
                        "error",
                        {"message": "部屋作成者のみ再作成できます"},
                        room=request.sid,
                    )
                    return
            else:
                owner_sid = get_game_meta(game_id).get("owner_sid")
                if owner_sid and owner_sid != request.sid:
                    emit(
                        "error",
                        {"message": "このゲームを上書きする権限がありません"},
                        room=request.sid,
                    )
                    return

        set_game_entry(
            game_id,
            game_type,
            create_game_state(game_type),
            meta={"mode": mode, "owner_sid": request.sid},
        )

        # ルーム参加後に配信することで初回の取りこぼしを防ぐ
        join_room(game_id)
        register_client_game(request.sid, game_id)
        ensure_ai_settings(game_id)

        _, game_state_obj = get_game_entry(game_id)
        game_state = build_game_state_payload(game_type, game_state_obj)
        emit("game_state", game_state, room=game_id)
        emit("game_state", game_state, room=request.sid)

        if game_type == "shogi":
            start_shogi_ai_turns_if_needed(
                socketio,
                game_id,
                max_turns=40,
                sid=request.sid,
            )

    @socketio.on("join_game")
    def handle_join_game(data):
        game_id, error_message = _parse_game_id(data)
        if error_message:
            emit("error", {"message": error_message}, room=request.sid)
            return
        requested_type = data.get("game_type", "othello")
        game_type, game_state_obj = get_game_entry(game_id)

        if game_state_obj is None:
            game_type = requested_type
            game_state_obj = create_game_state(game_type)
            set_game_entry(
                game_id,
                game_type,
                game_state_obj,
                meta={
                    "mode": data.get("mode", "singleplayer"),
                    "owner_sid": request.sid,
                },
            )
            ensure_ai_settings(game_id)

        join_room(game_id)
        register_client_game(request.sid, game_id)
        game_state = build_game_state_payload(game_type, game_state_obj)
        emit("game_state", game_state, room=request.sid)

        if game_type == "shogi":
            start_shogi_ai_turns_if_needed(
                socketio,
                game_id,
                max_turns=40,
                sid=request.sid,
            )

    @socketio.on("reset_game")
    def handle_reset_game(data):
        game_id, error_message = _parse_game_id(data)
        if error_message:
            emit("error", {"message": error_message}, room=request.sid)
            return
        game_type, game = get_game_entry(game_id)

        if game is None:
            game_type = data.get("game_type", "othello")
            set_game_entry(
                game_id,
                game_type,
                create_game_state(game_type),
                meta={
                    "mode": data.get("mode", "singleplayer"),
                    "owner_sid": request.sid,
                },
            )
            ensure_ai_settings(game_id)
        else:
            mode = get_game_mode(game_id)
            if mode == "multiplayer":
                slot, _session = get_multiplayer_slot(game_id, request.sid)
                if slot != "creator":
                    emit(
                        "error",
                        {"message": "部屋作成者のみリセットできます"},
                        room=request.sid,
                    )
                    return
            else:
                owner_sid = get_game_meta(game_id).get("owner_sid")
                if owner_sid and owner_sid != request.sid:
                    emit(
                        "error",
                        {"message": "このゲームをリセットする権限がありません"},
                        room=request.sid,
                    )
                    return

            previous_mode = get_game_meta(game_id).get("mode", "singleplayer")
            mode = data.get("mode", previous_mode)
            set_game_entry(
                game_id,
                game_type,
                create_game_state(game_type),
                meta={"mode": mode, "owner_sid": request.sid},
            )

        # 認可済みのクライアントのみroom参加させる
        join_room(game_id)
        register_client_game(request.sid, game_id)

        _, reset_state = get_game_entry(game_id)
        game_state = build_game_state_payload(game_type, reset_state)
        emit("game_state", game_state, room=game_id)
        emit("game_state", game_state, room=request.sid)

        if game_type == "shogi":
            start_shogi_ai_turns_if_needed(
                socketio,
                game_id,
                max_turns=40,
                sid=request.sid,
            )
