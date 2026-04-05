from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import List, Tuple

import numpy as np

from shogi_ai import select_shogi_move
from shogi_logic import Move, ShogiGameState
from shogi_ml_features import FEATURE_DIM, extract_move_features


@dataclass
class TrainingConfig:
    games: int = 30
    max_plies: int = 80
    teacher_depth: int = 2
    learning_rate: float = 0.08
    epochs: int = 14
    l2: float = 1e-4
    seed: int = 7


def _same_move(a: Move, b_dict: dict) -> bool:
    if (
        a.to_row != b_dict.get("to", [None, None])[0]
        or a.to_col != b_dict.get("to", [None, None])[1]
    ):
        return False
    if bool(a.promote) != bool(b_dict.get("promote", False)):
        return False

    if a.drop_piece is not None:
        return b_dict.get("drop_piece") is not None

    from_sq = b_dict.get("from")
    if not isinstance(from_sq, list) or len(from_sq) != 2:
        return False
    return a.from_row == from_sq[0] and a.from_col == from_sq[1]


def _collect_dataset(cfg: TrainingConfig) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(cfg.seed)
    features: List[List[float]] = []
    labels: List[float] = []

    teacher_cfg = {
        "engine": "minimax",
        "difficulty": "medium",
        "minmax_depth": cfg.teacher_depth,
    }

    for _ in range(cfg.games):
        state = ShogiGameState()

        for _ in range(cfg.max_plies):
            if state.game_over:
                break

            legal_moves = state.get_valid_moves()
            if not legal_moves:
                break

            teacher_move_payload = select_shogi_move(state, teacher_cfg)
            if teacher_move_payload is None:
                break

            for move in legal_moves:
                features.append(
                    extract_move_features(state, move, state.current_player)
                )
                labels.append(1.0 if _same_move(move, teacher_move_payload) else 0.0)

            # Mix teacher and exploration moves for broader position coverage.
            if rng.random() < 0.82:
                selected_payload = teacher_move_payload
            else:
                selected_payload = rng.choice(legal_moves).to_dict()

            if not state.make_move(selected_payload):
                break

    x = np.asarray(features, dtype=np.float32)
    y = np.asarray(labels, dtype=np.float32)
    return x, y


def _train_logistic(
    x: np.ndarray, y: np.ndarray, cfg: TrainingConfig
) -> Tuple[np.ndarray, float]:
    if x.size == 0 or y.size == 0:
        raise ValueError("dataset is empty; increase games/max_plies")
    if x.shape[1] != FEATURE_DIM:
        raise ValueError(f"unexpected feature dim: {x.shape[1]} != {FEATURE_DIM}")

    rng = np.random.default_rng(cfg.seed)
    w = rng.normal(0.0, 0.05, size=(x.shape[1],)).astype(np.float32)
    b = np.float32(0.0)

    pos_count = float(np.sum(y == 1.0))
    neg_count = float(np.sum(y == 0.0))
    pos_weight = neg_count / max(1.0, pos_count)

    for _ in range(cfg.epochs):
        logits = x @ w + b
        probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -16.0, 16.0)))

        # Weighted BCE derivative.
        error = probs - y
        sample_weight = np.where(y > 0.5, pos_weight, 1.0).astype(np.float32)
        error = error * sample_weight

        grad_w = (x.T @ error) / x.shape[0] + cfg.l2 * w
        grad_b = np.mean(error)

        w = w - cfg.learning_rate * grad_w
        b = np.float32(b - cfg.learning_rate * grad_b)

    return w.astype(np.float32), float(b)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train lightweight shogi policy model."
    )
    parser.add_argument("--games", type=int, default=30)
    parser.add_argument("--max-plies", type=int, default=80)
    parser.add_argument("--teacher-depth", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=14)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--l2", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join("backend", "models", "shogi_policy_weights.npz"),
    )
    parser.add_argument(
        "--meta",
        type=str,
        default=os.path.join("backend", "models", "shogi_policy_meta.json"),
    )
    args = parser.parse_args()

    cfg = TrainingConfig(
        games=max(1, args.games),
        max_plies=max(8, args.max_plies),
        teacher_depth=max(1, min(4, args.teacher_depth)),
        learning_rate=max(1e-4, args.learning_rate),
        epochs=max(1, args.epochs),
        l2=max(0.0, args.l2),
        seed=args.seed,
    )

    x, y = _collect_dataset(cfg)
    w, b = _train_logistic(x, y, cfg)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    np.savez(
        args.output, weights=w, bias=np.float32(b), feature_dim=np.int32(FEATURE_DIM)
    )

    meta = {
        "training": asdict(cfg),
        "dataset": {
            "samples": int(x.shape[0]),
            "feature_dim": int(x.shape[1]),
            "positive_ratio": float(np.mean(y)),
        },
    }

    os.makedirs(os.path.dirname(args.meta), exist_ok=True)
    with open(args.meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=True, indent=2)

    print(f"saved weights: {args.output}")
    print(f"saved metadata: {args.meta}")


if __name__ == "__main__":
    main()
