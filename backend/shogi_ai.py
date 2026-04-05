from __future__ import annotations

import hashlib
import math
import multiprocessing as mp
import os
import random
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, List, Optional, Tuple
from threading import Lock

from shogi_logic import (
    BISHOP,
    DRAGON,
    GOLD,
    HAND_TYPES,
    HORSE,
    KING,
    KNIGHT,
    LANCE,
    PAWN,
    PROM_KNIGHT,
    PROM_LANCE,
    PROM_PAWN,
    PROM_SILVER,
    ROOK,
    SILVER,
    Move,
)
from shogi_ml_features import FEATURE_DIM, extract_move_features

PIECE_VALUES = {
    PAWN: 1.0,
    LANCE: 4.0,
    KNIGHT: 4.3,
    SILVER: 5.2,
    GOLD: 6.2,
    BISHOP: 8.6,
    ROOK: 9.2,
    KING: 1000.0,
    PROM_PAWN: 6.1,
    PROM_LANCE: 6.1,
    PROM_KNIGHT: 6.1,
    PROM_SILVER: 6.1,
    HORSE: 11.0,
    DRAGON: 11.4,
}

DIFFICULTY_DEPTH = {
    "easy": 1,
    "medium": 2,
    "hard": 3,
}

DIFFICULTY_ITERATIONS = {
    "easy": 70,
    "medium": 180,
    "hard": 420,
}

ENGINE_ALIAS = {
    "minmax": "minimax",
    "rule": "rule_based",
    "rulebased": "rule_based",
    "random": "rule_based",
    "machine_learning": "ml",
}


@dataclass
class _RootMoveStat:
    visits: int = 0
    reward: float = 0.0


_PARALLEL_EXECUTOR: Optional[ProcessPoolExecutor] = None
_PARALLEL_EXECUTOR_MAX_WORKERS = 0
_PARALLEL_EXECUTOR_LOCK = Lock()


def _resolve_parallel_workers(config: Optional[dict], workload_size: int) -> int:
    cpu_count = os.cpu_count() or 1
    requested = (config or {}).get("parallel_workers")
    try:
        workers = int(requested) if requested is not None else min(4, cpu_count)
    except (TypeError, ValueError):
        workers = min(4, cpu_count)
    return max(1, min(workers, cpu_count, max(1, workload_size)))


def _parallel_inference_enabled(config: Optional[dict]) -> bool:
    if config is None:
        return True
    value = config.get("parallel_inference")
    if value is None:
        return True
    return bool(value)


def _get_parallel_executor(max_workers: int) -> ProcessPoolExecutor:
    global _PARALLEL_EXECUTOR, _PARALLEL_EXECUTOR_MAX_WORKERS

    with _PARALLEL_EXECUTOR_LOCK:
        if _PARALLEL_EXECUTOR is None or _PARALLEL_EXECUTOR_MAX_WORKERS < max_workers:
            if _PARALLEL_EXECUTOR is not None:
                _PARALLEL_EXECUTOR.shutdown(wait=False, cancel_futures=True)
            _PARALLEL_EXECUTOR = ProcessPoolExecutor(
                max_workers=max_workers,
                mp_context=mp.get_context("spawn"),
            )
            _PARALLEL_EXECUTOR_MAX_WORKERS = max_workers
        return _PARALLEL_EXECUTOR


def _score_rule_move(game_state, move: Move, player: int) -> float:
    score = 0.0
    to_piece = game_state.board[move.to_row][move.to_col]
    if to_piece != 0:
        score += 7.5 + PIECE_VALUES.get(abs(to_piece), 1.0)

    if move.promote:
        score += 2.5
    if move.drop_piece is not None:
        score += 0.3

    center_distance = abs(4 - move.to_row) + abs(4 - move.to_col)
    score += max(0.0, 2.8 - 0.35 * center_distance)

    state_backup = game_state._snapshot()
    game_state._apply_move(move, player)
    if game_state.is_in_check(3 - player):
        score += 4.2
    game_state._restore_snapshot(state_backup)
    return score


def _score_rule_move_task(task) -> Tuple[int, float]:
    index, game_state, move, player = task
    return index, _score_rule_move(game_state, move, player)


def _score_minimax_move(game_state, move: Move, player: int, depth: int) -> float:
    state_backup = game_state._snapshot()
    try:
        game_state._apply_move(move, player)
        game_state.current_player = 3 - player
        return MinimaxShogiAI()._search(
            game_state,
            root_player=player,
            to_move=3 - player,
            depth=depth - 1,
            alpha=-math.inf,
            beta=math.inf,
        )
    finally:
        game_state._restore_snapshot(state_backup)


def _score_minimax_move_task(task) -> Tuple[int, float]:
    index, game_state, move, player, depth = task
    return index, _score_minimax_move(game_state, move, player, depth)


class RuleBasedShogiAI:
    def select(
        self,
        game_state,
        player: int,
        config: dict,
        should_stop: Optional[Callable[[], bool]] = None,
        yield_fn: Optional[Callable[[], None]] = None,
    ) -> Optional[Move]:
        legal_moves = game_state.get_valid_moves()
        if not legal_moves:
            return None

        if _should_stop(should_stop):
            return None

        rng = random.Random(_seed_from_state(game_state, config, "rule"))
        if _parallel_inference_enabled(config) and len(legal_moves) >= 8:
            workers = _resolve_parallel_workers(config, len(legal_moves))
            if workers > 1:
                try:
                    executor = _get_parallel_executor(workers)
                    scored = sorted(
                        (
                            (score, legal_moves[index])
                            for index, score in executor.map(
                                _score_rule_move_task,
                                [
                                    (index, game_state, move, player)
                                    for index, move in enumerate(legal_moves)
                                ],
                                chunksize=1,
                            )
                        ),
                        key=lambda item: item[0],
                        reverse=True,
                    )
                except Exception:
                    scored = sorted(
                        (
                            (self._score_move(game_state, move, player), move)
                            for move in legal_moves
                        ),
                        key=lambda item: item[0],
                        reverse=True,
                    )
            else:
                scored = sorted(
                    (
                        (self._score_move(game_state, move, player), move)
                        for move in legal_moves
                    ),
                    key=lambda item: item[0],
                    reverse=True,
                )
        else:
            scored = sorted(
                (
                    (self._score_move(game_state, move, player), move)
                    for move in legal_moves
                ),
                key=lambda item: item[0],
                reverse=True,
            )

        _yield_control(yield_fn)

        if _should_stop(should_stop):
            return None

        difficulty = (config or {}).get("difficulty", "medium")
        if difficulty == "easy":
            top_k = min(7, len(scored))
        elif difficulty == "hard":
            top_k = min(2, len(scored))
        else:
            top_k = min(4, len(scored))

        return rng.choice([item[1] for item in scored[:top_k]])

    def _score_move(self, game_state, move: Move, player: int) -> float:
        return _score_rule_move(game_state, move, player)


class MinimaxShogiAI:
    def select(
        self,
        game_state,
        player: int,
        config: dict,
        should_stop: Optional[Callable[[], bool]] = None,
        yield_fn: Optional[Callable[[], None]] = None,
    ) -> Optional[Move]:
        legal_moves = game_state.get_valid_moves()
        if not legal_moves:
            return None

        if _should_stop(should_stop):
            return None

        difficulty = (config or {}).get("difficulty", "medium")
        depth = _bounded_int(
            (config or {}).get("minmax_depth"),
            DIFFICULTY_DEPTH.get(difficulty, 2),
            1,
            4,
        )

        rng = random.Random(_seed_from_state(game_state, config, "minimax"))
        scored: List[Tuple[float, Move]] = []

        use_parallel = (
            _parallel_inference_enabled(config)
            and len(legal_moves) >= 4
            and _resolve_parallel_workers(config, len(legal_moves)) > 1
        )

        if use_parallel:
            workers = _resolve_parallel_workers(config, len(legal_moves))
            try:
                executor = _get_parallel_executor(workers)
                parallel_results = list(
                    executor.map(
                        _score_minimax_move_task,
                        [
                            (index, game_state, move, player, depth)
                            for index, move in enumerate(legal_moves)
                        ],
                        chunksize=1,
                    )
                )
                if _should_stop(should_stop):
                    return None
                scored = [
                    (score, legal_moves[index]) for index, score in parallel_results
                ]
            except Exception:
                for move in legal_moves:
                    if _should_stop(should_stop):
                        return None

                    score = _score_minimax_move(game_state, move, player, depth)
                    scored.append((score, move))
                    _yield_control(yield_fn)

                    if _should_stop(should_stop):
                        return None
        else:
            for move in legal_moves:
                if _should_stop(should_stop):
                    return None

                score = _score_minimax_move(game_state, move, player, depth)
                scored.append((score, move))
                _yield_control(yield_fn)

                if _should_stop(should_stop):
                    return None

        best_score = max(item[0] for item in scored)
        best_moves = [item[1] for item in scored if abs(item[0] - best_score) < 1e-9]
        return rng.choice(best_moves)

    def _search(
        self,
        game_state,
        root_player: int,
        to_move: int,
        depth: int,
        alpha: float,
        beta: float,
        should_stop: Optional[Callable[[], bool]] = None,
        yield_fn: Optional[Callable[[], None]] = None,
    ) -> float:
        if _should_stop(should_stop):
            return 0.0

        if depth <= 0:
            return _evaluate_position(game_state, root_player)

        legal = game_state._generate_legal_moves(to_move, validate_pawn_drop_mate=True)
        if not legal:
            if game_state.is_in_check(to_move):
                return -10000.0 if to_move == root_player else 10000.0
            return 0.0

        maximizing = to_move == root_player
        if maximizing:
            best = -math.inf
            for move in legal:
                if _should_stop(should_stop):
                    return 0.0

                state_backup = game_state._snapshot()
                game_state._apply_move(move, to_move)
                game_state.current_player = 3 - to_move
                score = self._search(
                    game_state,
                    root_player,
                    3 - to_move,
                    depth - 1,
                    alpha,
                    beta,
                    should_stop=should_stop,
                    yield_fn=yield_fn,
                )
                game_state._restore_snapshot(state_backup)
                best = max(best, score)
                alpha = max(alpha, score)
                if beta <= alpha:
                    break
                _yield_control(yield_fn)
            return best

        best = math.inf
        for move in legal:
            if _should_stop(should_stop):
                return 0.0

            state_backup = game_state._snapshot()
            game_state._apply_move(move, to_move)
            game_state.current_player = 3 - to_move
            score = self._search(
                game_state,
                root_player,
                3 - to_move,
                depth - 1,
                alpha,
                beta,
                should_stop=should_stop,
                yield_fn=yield_fn,
            )
            game_state._restore_snapshot(state_backup)
            best = min(best, score)
            beta = min(beta, score)
            if beta <= alpha:
                break
            _yield_control(yield_fn)
        return best


class MCTSShogiAI:
    def select(
        self,
        game_state,
        player: int,
        config: dict,
        should_stop: Optional[Callable[[], bool]] = None,
        yield_fn: Optional[Callable[[], None]] = None,
    ) -> Optional[Move]:
        legal_moves = game_state.get_valid_moves()
        if not legal_moves:
            return None

        if _should_stop(should_stop):
            return None

        difficulty = (config or {}).get("difficulty", "medium")
        iterations = _bounded_int(
            (config or {}).get("mcts_iterations"),
            DIFFICULTY_ITERATIONS.get(difficulty, 180),
            20,
            3000,
        )
        rollout_depth = _bounded_int((config or {}).get("rollout_depth"), 20, 6, 40)

        rng = random.Random(_seed_from_state(game_state, config, "mcts"))
        stats = [_RootMoveStat() for _ in legal_moves]

        for _ in range(iterations):
            if _should_stop(should_stop):
                return None

            move_idx = self._select_root_index(stats, rng)
            root_move = legal_moves[move_idx]

            state_backup = game_state._snapshot()
            game_state._apply_move(root_move, player)
            game_state.current_player = 3 - player
            winner = self._rollout(
                game_state,
                root_player=player,
                to_move=3 - player,
                depth=rollout_depth,
                rng=rng,
                should_stop=should_stop,
                yield_fn=yield_fn,
            )
            game_state._restore_snapshot(state_backup)

            stats[move_idx].visits += 1
            if winner is None:
                stats[move_idx].reward += 0.5
            elif winner == player:
                stats[move_idx].reward += 1.0

            _yield_control(yield_fn)

        best_idx = max(
            range(len(legal_moves)),
            key=lambda i: (
                stats[i].reward / stats[i].visits if stats[i].visits else 0.0,
                stats[i].visits,
            ),
        )
        return legal_moves[best_idx]

    def _select_root_index(self, stats: List[_RootMoveStat], rng: random.Random) -> int:
        unexplored = [idx for idx, item in enumerate(stats) if item.visits == 0]
        if unexplored:
            return rng.choice(unexplored)

        total_visits = sum(item.visits for item in stats)
        c = 1.35
        best_score = -math.inf
        candidates: List[int] = []

        for idx, item in enumerate(stats):
            exploit = item.reward / item.visits
            explore = c * math.sqrt(math.log(total_visits) / item.visits)
            score = exploit + explore
            if score > best_score + 1e-12:
                best_score = score
                candidates = [idx]
            elif abs(score - best_score) < 1e-12:
                candidates.append(idx)

        return rng.choice(candidates)

    def _rollout(
        self,
        game_state,
        root_player: int,
        to_move: int,
        depth: int,
        rng: random.Random,
        should_stop: Optional[Callable[[], bool]] = None,
        yield_fn: Optional[Callable[[], None]] = None,
    ) -> Optional[int]:
        current = to_move

        for _ in range(depth):
            if _should_stop(should_stop):
                return None

            legal = game_state._generate_legal_moves(
                current, validate_pawn_drop_mate=True
            )
            if not legal:
                if game_state.is_in_check(current):
                    return 3 - current
                return None

            move = self._sample_rollout_move(game_state, legal, current, rng)
            game_state._apply_move(move, current)
            current = 3 - current
            game_state.current_player = current
            _yield_control(yield_fn)

        score = _evaluate_position(game_state, root_player)
        if score > 0.8:
            return root_player
        if score < -0.8:
            return 3 - root_player
        return None

    def _sample_rollout_move(
        self,
        game_state,
        legal_moves: List[Move],
        player: int,
        rng: random.Random,
    ) -> Move:
        evaluator = RuleBasedShogiAI()
        scored = [
            (evaluator._score_move(game_state, move, player), move)
            for move in legal_moves
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        top_k = min(6, len(scored))
        return rng.choice([item[1] for item in scored[:top_k]])


class MLShogiAI:
    def __init__(self):
        self._session = None
        self._model_path = None
        self._load_error = False

    def select(
        self,
        game_state,
        player: int,
        config: dict,
        should_stop: Optional[Callable[[], bool]] = None,
        yield_fn: Optional[Callable[[], None]] = None,
    ) -> Optional[Move]:
        legal_moves = game_state.get_valid_moves()
        if not legal_moves:
            return None

        if _should_stop(should_stop):
            return None

        # Safe fallback if runtime/model is unavailable.
        if not self._ensure_model_loaded(config):
            return MinimaxShogiAI().select(
                game_state,
                player,
                config,
                should_stop=should_stop,
                yield_fn=yield_fn,
            )

        try:
            import numpy as np

            features = np.asarray(
                [
                    extract_move_features(game_state, move, player)
                    for move in legal_moves
                ],
                dtype=np.float32,
            )

            if features.ndim != 2 or features.shape[1] != FEATURE_DIM:
                return MinimaxShogiAI().select(
                    game_state,
                    player,
                    config,
                    should_stop=should_stop,
                    yield_fn=yield_fn,
                )

            input_name = self._session.get_inputs()[0].name
            output = self._session.run(None, {input_name: features})[0]
            flat_scores = output.reshape(-1)
            if flat_scores.size != len(legal_moves):
                return MinimaxShogiAI().select(
                    game_state,
                    player,
                    config,
                    should_stop=should_stop,
                    yield_fn=yield_fn,
                )

            difficulty = (config or {}).get("difficulty", "medium")
            rng = random.Random(_seed_from_state(game_state, config, "ml"))
            scored_indices = sorted(
                range(len(legal_moves)),
                key=lambda idx: float(flat_scores[idx]),
                reverse=True,
            )

            if difficulty == "easy":
                top_k = min(6, len(scored_indices))
            elif difficulty == "hard":
                top_k = 1
            else:
                top_k = min(3, len(scored_indices))

            _yield_control(yield_fn)
            if _should_stop(should_stop):
                return None
            return legal_moves[rng.choice(scored_indices[:top_k])]
        except Exception:
            return MinimaxShogiAI().select(
                game_state,
                player,
                config,
                should_stop=should_stop,
                yield_fn=yield_fn,
            )

    def _ensure_model_loaded(self, config: dict) -> bool:
        if self._load_error:
            return False

        model_path = (config or {}).get("model_path")
        if not model_path:
            model_path = os.path.join(
                os.path.dirname(__file__), "models", "shogi_policy.onnx"
            )
        model_path = os.path.abspath(model_path)

        if self._session is not None and self._model_path == model_path:
            return True

        if not os.path.exists(model_path):
            self._load_error = True
            return False

        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                model_path,
                providers=["CPUExecutionProvider"],
            )
            self._model_path = model_path
            self._load_error = False
            return True
        except Exception:
            self._session = None
            self._model_path = None
            self._load_error = True
            return False


def select_shogi_move(
    game_state,
    config: Optional[dict],
    should_stop: Optional[Callable[[], bool]] = None,
    yield_fn: Optional[Callable[[], None]] = None,
) -> Optional[dict]:
    cfg = config or {}
    engine = _normalize_engine(cfg)
    player = game_state.current_player

    if engine == "none":
        return None

    if engine == "rule_based":
        selected = RuleBasedShogiAI().select(
            game_state,
            player,
            cfg,
            should_stop=should_stop,
            yield_fn=yield_fn,
        )
    elif engine == "minimax":
        selected = MinimaxShogiAI().select(
            game_state,
            player,
            cfg,
            should_stop=should_stop,
            yield_fn=yield_fn,
        )
    elif engine == "mcts":
        selected = MCTSShogiAI().select(
            game_state,
            player,
            cfg,
            should_stop=should_stop,
            yield_fn=yield_fn,
        )
    elif engine in {"onnx", "ml"}:
        selected = MLShogiAI().select(
            game_state,
            player,
            cfg,
            should_stop=should_stop,
            yield_fn=yield_fn,
        )
    else:
        selected = RuleBasedShogiAI().select(
            game_state,
            player,
            cfg,
            should_stop=should_stop,
            yield_fn=yield_fn,
        )

    return selected.to_dict() if selected is not None else None


def _normalize_engine(config: dict) -> str:
    raw = str(config.get("engine") or config.get("algorithm") or "rule_based").lower()
    normalized = ENGINE_ALIAS.get(raw, raw)
    if normalized in {"none", "rule_based", "minimax", "mcts", "onnx", "ml"}:
        return normalized
    return "rule_based"


def _bounded_int(value, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _should_stop(should_stop: Optional[Callable[[], bool]]) -> bool:
    if should_stop is None:
        return False
    try:
        return bool(should_stop())
    except Exception:
        return True


def _yield_control(yield_fn: Optional[Callable[[], None]]) -> None:
    if yield_fn is None:
        return
    try:
        yield_fn()
    except Exception:
        return


def _seed_from_state(game_state, config: dict, suffix: str) -> int:
    key = game_state._position_key()
    cfg_key = f"{config.get('difficulty', 'medium')}:{config.get('engine') or config.get('algorithm') or ''}"
    digest = hashlib.sha256(f"{key}|{cfg_key}|{suffix}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _evaluate_position(game_state, root_player: int) -> float:
    own_sign = 1 if root_player == 1 else -1
    material = 0.0

    for row in game_state.board:
        for piece in row:
            if piece == 0:
                continue
            value = PIECE_VALUES.get(abs(piece), 1.0)
            material += value if piece * own_sign > 0 else -value

    for piece in HAND_TYPES:
        own_count = game_state.hands[root_player][piece]
        opp_count = game_state.hands[3 - root_player][piece]
        material += 0.85 * PIECE_VALUES.get(piece, 1.0) * (own_count - opp_count)

    own_mobility = len(
        game_state._generate_legal_moves(root_player, validate_pawn_drop_mate=True)
    )
    opp_mobility = len(
        game_state._generate_legal_moves(3 - root_player, validate_pawn_drop_mate=True)
    )
    material += 0.06 * (own_mobility - opp_mobility)

    if game_state.is_in_check(root_player):
        material -= 0.7
    if game_state.is_in_check(3 - root_player):
        material += 0.7

    return material
