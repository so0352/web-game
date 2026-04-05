from __future__ import annotations

from typing import List

from shogi_logic import (
    BISHOP,
    DRAGON,
    GOLD,
    HAND_TYPES,
    HORSE,
    KING,
    KNIGHT,
    LANCE,
    Move,
    PAWN,
    PROM_KNIGHT,
    PROM_LANCE,
    PROM_PAWN,
    PROM_SILVER,
    ROOK,
    SILVER,
)

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

FEATURE_DIM = 18


def extract_move_features(game_state, move: Move, player: int) -> List[float]:
    own_sign = 1 if player == 1 else -1
    before_eval = _material_eval(game_state, player)
    before_own_check = 1.0 if game_state.is_in_check(player) else 0.0

    captured_piece = game_state.board[move.to_row][move.to_col]
    capture_value = (
        PIECE_VALUES.get(abs(captured_piece), 0.0) if captured_piece != 0 else 0.0
    )

    from_row_norm = -1.0 if move.from_row is None else (move.from_row / 8.0)
    from_col_norm = -1.0 if move.from_col is None else (move.from_col / 8.0)
    to_row_norm = move.to_row / 8.0
    to_col_norm = move.to_col / 8.0

    moved_piece = (
        move.drop_piece
        if move.drop_piece is not None
        else abs(game_state.board[move.from_row][move.from_col])
    )
    moved_piece_norm = moved_piece / 14.0

    center_distance = abs(4 - move.to_row) + abs(4 - move.to_col)
    center_score = max(0.0, (8.0 - center_distance) / 8.0)

    own_hand_before = sum(game_state.hands[player].values())
    opp_hand_before = sum(game_state.hands[3 - player].values())

    state_backup = game_state._snapshot()
    game_state._apply_move(move, player)
    game_state.current_player = 3 - player

    after_eval = _material_eval(game_state, player)
    eval_delta = after_eval - before_eval

    own_mobility_after = len(
        game_state._generate_legal_moves(player, validate_pawn_drop_mate=True)
    )
    opp_mobility_after = len(
        game_state._generate_legal_moves(3 - player, validate_pawn_drop_mate=True)
    )
    own_check_after = 1.0 if game_state.is_in_check(player) else 0.0
    opp_check_after = 1.0 if game_state.is_in_check(3 - player) else 0.0

    own_hand_after = sum(game_state.hands[player].values())
    opp_hand_after = sum(game_state.hands[3 - player].values())

    game_state._restore_snapshot(state_backup)

    hand_delta = (own_hand_after - own_hand_before) - (opp_hand_after - opp_hand_before)

    return [
        1.0,
        1.0 if captured_piece != 0 else 0.0,
        capture_value / 12.0,
        1.0 if move.promote else 0.0,
        1.0 if move.drop_piece is not None else 0.0,
        from_row_norm,
        from_col_norm,
        to_row_norm,
        to_col_norm,
        center_score,
        before_own_check,
        own_check_after,
        opp_check_after,
        eval_delta / 20.0,
        own_mobility_after / 80.0,
        opp_mobility_after / 80.0,
        hand_delta / 8.0,
        moved_piece_norm * own_sign,
    ]


def _material_eval(game_state, root_player: int) -> float:
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

    return material
