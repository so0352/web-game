from flask import request
from flask_socketio import emit

from game_logic import Player
from game_store import build_game_state_payload, get_game_entry, get_game_mode
from handlers.matchmaking_handlers import get_multiplayer_slot
from handlers.shogi_ai_support import run_shogi_ai_turns


def _is_expected_player_turn(game_type, game, seat):
    if seat not in {"first", "second"}:
        return False
    if game_type == "shogi":
        expected_player = 1 if seat == "first" else 2
        return game.current_player == expected_player
    expected_player = Player.BLACK if seat == "first" else Player.WHITE
    return game.current_player == expected_player


def register_move_handlers(socketio):
    @socketio.on("make_move")
    def handle_make_move(data):
        """ゲームの手を処理（ブラウザ側でAI判定を行う）"""
        game_id = data.get("game_id", "default")
        game_type, game = get_game_entry(game_id)

        if game is None:
            emit("error", {"message": "Game not found"})
            return

        if get_game_mode(game_id) == "multiplayer":
            slot, session = get_multiplayer_slot(game_id, request.sid)
            if session is None or slot is None:
                emit(
                    "error", {"message": "この対局に参加していません"}, room=request.sid
                )
                return
            if session.get("status") != "active" or not session.get("seat_by_slot"):
                emit(
                    "error",
                    {"message": "先攻/後攻の確定を待っています"},
                    room=request.sid,
                )
                return

            seat = session["seat_by_slot"].get(slot)
            if not _is_expected_player_turn(game_type, game, seat):
                emit(
                    "error",
                    {"message": "現在あなたのターンではありません"},
                    room=request.sid,
                )
                return

        if game_type == "shogi":
            move = data.get("move")
            if game.make_move(move):
                game_state = build_game_state_payload(game_type, game)
                emit("game_state", game_state, room=game_id)
                run_shogi_ai_turns(socketio, game_id, max_turns=1, sid=request.sid)
            else:
                emit("error", {"message": "Invalid shogi move"}, room=request.sid)
            return

        row = data.get("row")
        col = data.get("col")

        # パスの場合（row/col が -1）
        if row == -1 and col == -1:
            game.current_player = (
                Player.WHITE if game.current_player == Player.BLACK else Player.BLACK
            )
            if not game.get_valid_moves():
                game.game_over = True
                game._determine_winner()
            game_state = build_game_state_payload(game_type, game)
            emit("game_state", game_state, room=game_id)
            return

        if game.make_move(row, col):
            game_state = build_game_state_payload(game_type, game)
            emit("game_state", game_state, room=game_id)
        else:
            emit("error", {"message": "Invalid move"}, room=request.sid)
