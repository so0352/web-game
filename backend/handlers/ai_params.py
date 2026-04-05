def parse_optional_int(value, min_value, max_value):
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(min_value, min(max_value, parsed))


def normalize_ai_engine(game_type, engine, algorithm):
    default_engine = "minimax" if game_type == "shogi" else "minmax"
    selected_engine = str(engine or algorithm or default_engine).lower()

    if game_type == "shogi":
        if selected_engine in {"rule", "rulebased", "random"}:
            selected_engine = "rule_based"
        if selected_engine == "minmax":
            selected_engine = "minimax"
        if selected_engine not in {
            "none",
            "rule_based",
            "minimax",
            "mcts",
            "onnx",
            "ml",
        }:
            return None
        return selected_engine

    if selected_engine not in {"none", "minmax", "mcts"}:
        return None
    return selected_engine
