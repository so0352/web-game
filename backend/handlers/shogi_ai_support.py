from shogi_ai import select_shogi_move

from game_store import (
    ai_settings,
    begin_ai_run,
    build_game_state_payload,
    finish_ai_run,
    get_game_entry,
    should_continue_ai_run,
)


def get_current_shogi_ai_config(game_id, game):
    settings = ai_settings.get(game_id) or {}
    key = "black_ai" if game.current_player == 1 else "white_ai"
    config = settings.get(key)
    if not isinstance(config, dict):
        return None

    if config.get("game_type") not in (None, "shogi"):
        return None

    engine = str(config.get("engine") or config.get("algorithm") or "none").lower()
    if engine == "none":
        return None

    return config


def _emit_shogi_ai_thinking(socketio, game_id, sid, active, player_label, algorithm):
    payload = {
        "game_id": game_id,
        "active": active,
        "player": player_label,
        "algorithm": algorithm,
    }

    socketio.emit("ai_thinking", payload, room=game_id)
    if sid:
        socketio.emit("ai_thinking", payload, room=sid)


def run_shogi_ai_turns(socketio, game_id, max_turns=1, sid=None):
    generation = begin_ai_run(game_id)
    if generation is None:
        return False

    socketio.start_background_task(
        _run_shogi_ai_turns_task, socketio, game_id, max_turns, generation, sid
    )
    return True


def start_shogi_ai_turns_if_needed(socketio, game_id, max_turns=1, sid=None):
    game_type, game = get_game_entry(game_id)
    if game_type != "shogi" or game is None or game.game_over:
        return False

    if get_current_shogi_ai_config(game_id, game) is None:
        return False

    return run_shogi_ai_turns(socketio, game_id, max_turns=max_turns, sid=sid)


def _run_shogi_ai_turns_task(socketio, game_id, max_turns, generation, sid=None):
    schedule_follow_up = False

    try:
        game_type, game = get_game_entry(game_id)
        if game_type != "shogi" or game is None:
            return

        applied_turns = 0

        while applied_turns < max_turns and not game.game_over:
            if not should_continue_ai_run(game_id, generation):
                break

            config = get_current_shogi_ai_config(game_id, game)
            if config is None:
                break

            player_label = "black" if game.current_player == 1 else "white"
            algorithm = str(
                config.get("engine") or config.get("algorithm") or "rule_based"
            ).lower()

            _emit_shogi_ai_thinking(
                socketio,
                game_id,
                sid,
                True,
                player_label,
                algorithm,
            )

            try:
                move_payload = select_shogi_move(
                    game,
                    config,
                    should_stop=lambda: not should_continue_ai_run(game_id, generation),
                    yield_fn=lambda: socketio.sleep(0),
                )
            finally:
                _emit_shogi_ai_thinking(
                    socketio,
                    game_id,
                    sid,
                    False,
                    player_label,
                    algorithm,
                )

            if move_payload is None:
                break

            if not should_continue_ai_run(game_id, generation):
                break

            if not game.make_move(move_payload):
                break

            applied_turns += 1
            game_state = build_game_state_payload(game_type, game)
            socketio.emit("game_state", game_state, room=game_id)
            socketio.sleep(0)

        if (
            not game.game_over
            and get_current_shogi_ai_config(game_id, game) is not None
        ):
            schedule_follow_up = True
    finally:
        finish_ai_run(game_id, generation)

        if schedule_follow_up:
            run_shogi_ai_turns(socketio, game_id, max_turns=max_turns, sid=sid)
