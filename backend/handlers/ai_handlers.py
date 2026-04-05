from flask import request
from flask_socketio import emit

from game_logic import GameState
from game_store import (
    ai_settings,
    build_game_state_payload,
    ensure_ai_settings,
    get_game_entry,
    get_game_mode,
    set_game_entry,
)
from handlers.shogi_ai_support import run_shogi_ai_turns
from handlers.ai_params import normalize_ai_engine, parse_optional_int


def register_ai_handlers(socketio):
    @socketio.on("set_ai")
    def handle_set_ai(data):
        """AIプレイヤーの設定（ブラウザ側での使用）"""
        game_id = data.get("game_id", "default")
        if get_game_mode(game_id) == "multiplayer":
            emit(
                "error",
                {"message": "マルチプレイではAI設定は利用できません"},
                room=request.sid,
            )
            return

        game_type, game = get_game_entry(game_id)
        color = data.get("color")  # 'black' or 'white'
        difficulty = data.get("difficulty", "medium")  # 'easy', 'medium', 'hard'
        algorithm = data.get("algorithm")
        engine = data.get("engine")
        selected_engine = normalize_ai_engine(game_type, engine, algorithm)
        minmax_depth = parse_optional_int(data.get("depth"), 1, 8)
        mcts_iterations = parse_optional_int(data.get("iterations"), 10, 100000)
        time_budget_ms = parse_optional_int(data.get("time_budget_ms"), 50, 30000)

        if game is None:
            game_type = "othello"
            game = GameState()
            set_game_entry(game_id, game_type, game)

        settings = ensure_ai_settings(game_id)
        settings["engine_scope"] = str(data.get("engine_scope") or "server").lower()

        if selected_engine is None:
            error_message = (
                "Unsupported shogi AI engine"
                if game_type == "shogi"
                else "Unsupported othello AI algorithm"
            )
            emit("error", {"message": error_message}, room=request.sid)
            return

        if color == "black":
            settings["black_ai"] = (
                None
                if selected_engine == "none"
                else {
                    "difficulty": difficulty,
                    "algorithm": selected_engine,
                    "engine": selected_engine,
                    "game_type": game_type,
                    "minmax_depth": minmax_depth,
                    "mcts_iterations": mcts_iterations,
                    "time_budget_ms": time_budget_ms,
                }
            )
        elif color == "white":
            settings["white_ai"] = (
                None
                if selected_engine == "none"
                else {
                    "difficulty": difficulty,
                    "algorithm": selected_engine,
                    "engine": selected_engine,
                    "game_type": game_type,
                    "minmax_depth": minmax_depth,
                    "mcts_iterations": mcts_iterations,
                    "time_budget_ms": time_budget_ms,
                }
            )
        else:
            emit("error", {"message": "Invalid AI color"}, room=request.sid)
            return

        if game_type == "shogi":
            # If current turn is AI after configuration, progress one or more turns.
            run_shogi_ai_turns(socketio, game_id, max_turns=40, sid=request.sid)

        game_state = build_game_state_payload(game_type, game)
        emit("game_state", game_state, room=game_id)
        emit("game_state", game_state, room=request.sid)
        emit(
            "ai_updated",
            {
                "color": color,
                "difficulty": difficulty,
                "algorithm": selected_engine,
                "engine": selected_engine,
                "engine_scope": settings["engine_scope"],
                "depth": minmax_depth,
                "iterations": mcts_iterations,
                "time_budget_ms": time_budget_ms,
            },
            room=request.sid,
        )

    @socketio.on("get_ai_info")
    def handle_get_ai_info(data):
        """現在のAI設定を取得"""
        game_id = data.get("game_id", "default")
        game_type, _ = get_game_entry(game_id)
        settings = ai_settings.get(game_id)
        if settings:
            emit(
                "ai_info",
                {
                    "black_ai": settings["black_ai"],
                    "white_ai": settings["white_ai"],
                    "engine_scope": settings.get("engine_scope", "server"),
                },
                room=request.sid,
            )
        else:
            emit(
                "ai_info",
                {"black_ai": None, "white_ai": None, "engine_scope": "server"},
                room=request.sid,
            )
