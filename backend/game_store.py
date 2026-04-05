from game_logic import GameState
from shogi_logic import ShogiGameState

# ゲームインスタンスとAI設定を保持する辞書
games = {}
ai_settings = {}  # ゲームIDごとのAI設定情報（ブラウザ側での使用）
client_games = {}
game_clients = {}
ai_runtime_state = {}


def create_game_state(game_type):
    if game_type == "shogi":
        return ShogiGameState()
    return GameState()


def get_game_entry(game_id):
    entry = games.get(game_id)
    if entry is None:
        return None, None

    # 旧フォーマット互換（GameState を直接保持していた場合）
    if isinstance(entry, dict) and "state" in entry and "type" in entry:
        return entry["type"], entry["state"]

    return "othello", entry


def set_game_entry(game_id, game_type, state, meta=None):
    existing_meta = get_game_meta(game_id)
    merged_meta = dict(existing_meta)
    if isinstance(meta, dict):
        merged_meta.update(meta)
    games[game_id] = {"type": game_type, "state": state, "meta": merged_meta}


def get_game_meta(game_id):
    entry = games.get(game_id)
    if not isinstance(entry, dict):
        return {}
    meta = entry.get("meta")
    if isinstance(meta, dict):
        return meta
    return {}


def update_game_meta(game_id, updates):
    if not isinstance(updates, dict):
        return {}
    entry = games.get(game_id)
    if entry is None:
        return {}

    if isinstance(entry, dict) and "state" in entry and "type" in entry:
        current_meta = get_game_meta(game_id)
        current_meta.update(updates)
        entry["meta"] = current_meta
        return current_meta

    games[game_id] = {"type": "othello", "state": entry, "meta": dict(updates)}
    return games[game_id]["meta"]


def get_game_mode(game_id, default="singleplayer"):
    meta = get_game_meta(game_id)
    mode = meta.get("mode")
    if mode in {"singleplayer", "multiplayer"}:
        return mode
    return default


def build_game_state_payload(game_type, state):
    payload = state.get_game_info()
    if "game_type" not in payload:
        payload["game_type"] = game_type
    return payload


def ensure_ai_settings(game_id):
    if game_id not in ai_settings:
        ai_settings[game_id] = {
            "black_ai": None,
            "white_ai": None,
            "engine_scope": "server",
        }
    return ai_settings[game_id]


def ensure_ai_runtime_state(game_id):
    if game_id not in ai_runtime_state:
        ai_runtime_state[game_id] = {
            "running": False,
            "cancelled": False,
            "generation": 0,
        }
    return ai_runtime_state[game_id]


def register_client_game(sid, game_id):
    previous_game_id = client_games.get(sid)
    if previous_game_id and previous_game_id != game_id:
        previous_clients = game_clients.get(previous_game_id)
        if previous_clients is not None:
            previous_clients.discard(sid)
            if not previous_clients:
                cleanup_game(previous_game_id)

    client_games[sid] = game_id
    game_clients.setdefault(game_id, set()).add(sid)


def detach_client_game(sid, allow_cleanup=True):
    game_id = client_games.pop(sid, None)
    if game_id is None:
        return None

    clients = game_clients.get(game_id)
    if clients is not None:
        clients.discard(sid)
        if not clients and allow_cleanup:
            cleanup_game(game_id)

    return game_id


def unregister_client_game(sid):
    return detach_client_game(sid, allow_cleanup=True)


def get_client_game(sid):
    return client_games.get(sid)


def cancel_ai_run(game_id):
    runtime = ensure_ai_runtime_state(game_id)
    runtime["cancelled"] = True
    runtime["running"] = False
    runtime["generation"] += 1
    return runtime["generation"]


def begin_ai_run(game_id):
    runtime = ensure_ai_runtime_state(game_id)
    if runtime["running"]:
        return None

    runtime["running"] = True
    runtime["cancelled"] = False
    runtime["generation"] += 1
    return runtime["generation"]


def should_continue_ai_run(game_id, generation):
    runtime = ai_runtime_state.get(game_id)
    if runtime is None:
        return False

    return (
        runtime["running"]
        and not runtime["cancelled"]
        and runtime["generation"] == generation
        and game_id in games
    )


def finish_ai_run(game_id, generation):
    runtime = ai_runtime_state.get(game_id)
    if runtime is None:
        return

    if runtime["generation"] == generation:
        runtime["running"] = False


def cleanup_game(game_id):
    games.pop(game_id, None)
    ai_settings.pop(game_id, None)
    ai_runtime_state.pop(game_id, None)
    game_clients.pop(game_id, None)
