from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

BOARD_SIZE = 9

PAWN = 1
LANCE = 2
KNIGHT = 3
SILVER = 4
GOLD = 5
BISHOP = 6
ROOK = 7
KING = 8

PROM_PAWN = 9
PROM_LANCE = 10
PROM_KNIGHT = 11
PROM_SILVER = 12
HORSE = 13
DRAGON = 14

PROMOTABLE = {PAWN, LANCE, KNIGHT, SILVER, BISHOP, ROOK}
HAND_TYPES = [PAWN, LANCE, KNIGHT, SILVER, GOLD, BISHOP, ROOK]
PIECE_LABELS = {
    PAWN: "P",
    LANCE: "L",
    KNIGHT: "N",
    SILVER: "S",
    GOLD: "G",
    BISHOP: "B",
    ROOK: "R",
}
LABEL_TO_PIECE = {v: k for k, v in PIECE_LABELS.items()}


@dataclass
class Move:
    to_row: int
    to_col: int
    from_row: Optional[int] = None
    from_col: Optional[int] = None
    drop_piece: Optional[int] = None
    promote: bool = False

    def to_dict(self) -> dict:
        payload = {
            "to": [self.to_row, self.to_col],
            "promote": self.promote,
        }
        if self.drop_piece is not None:
            payload["drop_piece"] = PIECE_LABELS[self.drop_piece]
        else:
            payload["from"] = [self.from_row, self.from_col]
        return payload


class ShogiGameState:
    def __init__(self):
        self.board = self._create_initial_board()
        self.current_player = 1  # 1: 先手, 2: 後手
        self.hands = {
            1: {piece: 0 for piece in HAND_TYPES},
            2: {piece: 0 for piece in HAND_TYPES},
        }
        self.game_over = False
        self.winner = None
        self.result = None
        self.last_move = None
        self._history: List[Tuple[str, int]] = []
        self._position_counts: Dict[str, int] = {}
        self._record_position(checking_player=0)

    def _create_initial_board(self) -> List[List[int]]:
        board = [[0 for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

        board[0] = [
            -LANCE,
            -KNIGHT,
            -SILVER,
            -GOLD,
            -KING,
            -GOLD,
            -SILVER,
            -KNIGHT,
            -LANCE,
        ]
        board[1][1] = -ROOK
        board[1][7] = -BISHOP
        board[2] = [-PAWN for _ in range(BOARD_SIZE)]

        board[6] = [PAWN for _ in range(BOARD_SIZE)]
        board[7][1] = BISHOP
        board[7][7] = ROOK
        board[8] = [LANCE, KNIGHT, SILVER, GOLD, KING, GOLD, SILVER, KNIGHT, LANCE]
        return board

    def reset(self):
        self.__init__()

    def get_game_info(self) -> dict:
        in_check = self.is_in_check(self.current_player)
        valid_moves = [move.to_dict() for move in self.get_valid_moves()]
        return {
            "game_type": "shogi",
            # Use a snapshot so payload does not keep a stale reference while
            # legal move generation temporarily swaps internal board objects.
            "board": deepcopy(self.board),
            "current_player": self.current_player,
            "valid_moves": valid_moves,
            "hands": {
                "black": self._serialize_hand(1),
                "white": self._serialize_hand(2),
            },
            "game_over": self.game_over,
            "winner": self.winner,
            "result": self.result,
            "in_check": in_check,
            "last_move": deepcopy(self.last_move),
        }

    def _serialize_hand(self, player: int) -> Dict[str, int]:
        return {
            PIECE_LABELS[piece]: count for piece, count in self.hands[player].items()
        }

    def get_valid_moves(self) -> List[Move]:
        if self.game_over:
            return []
        return self._generate_legal_moves(
            self.current_player, validate_pawn_drop_mate=True
        )

    def make_move(self, move_payload: dict) -> bool:
        if self.game_over:
            return False

        move = self._parse_move(move_payload)
        if move is None:
            return False

        legal_moves = self._generate_legal_moves(
            self.current_player, validate_pawn_drop_mate=True
        )
        matched = next(
            (
                candidate
                for candidate in legal_moves
                if self._same_move(candidate, move)
            ),
            None,
        )
        if matched is None:
            return False

        self._apply_move(matched, self.current_player)
        self.last_move = matched.to_dict()

        checking_player = (
            self.current_player if self.is_in_check(3 - self.current_player) else 0
        )

        self.current_player = 3 - self.current_player
        self._record_position(checking_player=checking_player)

        self._evaluate_terminal_state()
        return True

    def _parse_move(self, payload: dict) -> Optional[Move]:
        if not isinstance(payload, dict):
            return None

        to = payload.get("to")
        if not self._valid_square_payload(to):
            return None
        to_row, to_col = to

        promote = bool(payload.get("promote", False))
        drop_piece_label = payload.get("drop_piece")
        from_sq = payload.get("from")

        if drop_piece_label is not None:
            if drop_piece_label not in LABEL_TO_PIECE:
                return None
            return Move(
                to_row=to_row,
                to_col=to_col,
                drop_piece=LABEL_TO_PIECE[drop_piece_label],
                promote=False,
            )

        if not self._valid_square_payload(from_sq):
            return None
        from_row, from_col = from_sq
        return Move(
            from_row=from_row,
            from_col=from_col,
            to_row=to_row,
            to_col=to_col,
            promote=promote,
        )

    def _valid_square_payload(self, sq) -> bool:
        if not isinstance(sq, list) or len(sq) != 2:
            return False
        row, col = sq
        return (
            isinstance(row, int)
            and isinstance(col, int)
            and 0 <= row < BOARD_SIZE
            and 0 <= col < BOARD_SIZE
        )

    def _same_move(self, a: Move, b: Move) -> bool:
        return (
            a.from_row == b.from_row
            and a.from_col == b.from_col
            and a.to_row == b.to_row
            and a.to_col == b.to_col
            and a.drop_piece == b.drop_piece
            and a.promote == b.promote
        )

    def _generate_legal_moves(
        self, player: int, validate_pawn_drop_mate: bool
    ) -> List[Move]:
        pseudo = self._generate_pseudo_moves(player)
        legal: List[Move] = []
        for move in pseudo:
            state_backup = self._snapshot()
            self._apply_move(move, player)
            if not self.is_in_check(player):
                if move.drop_piece == PAWN and validate_pawn_drop_mate:
                    if self._is_illegal_pawn_drop_mate(player):
                        self._restore_snapshot(state_backup)
                        continue
                legal.append(move)
            self._restore_snapshot(state_backup)
        return legal

    def _generate_pseudo_moves(self, player: int) -> List[Move]:
        moves: List[Move] = []
        sign = 1 if player == 1 else -1

        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = self.board[row][col]
                if piece == 0 or piece * sign <= 0:
                    continue
                moves.extend(self._piece_moves(row, col, piece, player))

        moves.extend(self._drop_moves(player))
        return moves

    def _piece_moves(
        self, row: int, col: int, piece_value: int, player: int
    ) -> List[Move]:
        base_piece = self._base_piece(abs(piece_value))
        promoted_piece = abs(piece_value) != base_piece
        sign = 1 if player == 1 else -1

        vectors, sliding = self._movement_vectors(abs(piece_value), player)
        candidates: List[Move] = []

        for d_row, d_col in vectors:
            cur_row, cur_col = row + d_row, col + d_col
            while 0 <= cur_row < BOARD_SIZE and 0 <= cur_col < BOARD_SIZE:
                target = self.board[cur_row][cur_col]
                if target * sign > 0:
                    break

                promote_mandatory = self._is_promotion_mandatory(
                    base_piece, player, cur_row
                )
                can_promote = (
                    not promoted_piece
                    and base_piece in PROMOTABLE
                    and (
                        self._is_in_promotion_zone(player, row)
                        or self._is_in_promotion_zone(player, cur_row)
                    )
                )

                if promote_mandatory:
                    candidates.append(
                        Move(
                            from_row=row,
                            from_col=col,
                            to_row=cur_row,
                            to_col=cur_col,
                            promote=True,
                        )
                    )
                else:
                    candidates.append(
                        Move(
                            from_row=row,
                            from_col=col,
                            to_row=cur_row,
                            to_col=cur_col,
                            promote=False,
                        )
                    )
                    if can_promote:
                        candidates.append(
                            Move(
                                from_row=row,
                                from_col=col,
                                to_row=cur_row,
                                to_col=cur_col,
                                promote=True,
                            )
                        )

                if target != 0 or not sliding:
                    break
                cur_row += d_row
                cur_col += d_col

        for d_row, d_col in self._extra_king_like_moves(abs(piece_value), player):
            cur_row, cur_col = row + d_row, col + d_col
            if not (0 <= cur_row < BOARD_SIZE and 0 <= cur_col < BOARD_SIZE):
                continue

            target = self.board[cur_row][cur_col]
            if target * sign > 0:
                continue

            candidates.append(
                Move(
                    from_row=row,
                    from_col=col,
                    to_row=cur_row,
                    to_col=cur_col,
                    promote=False,
                )
            )

        return candidates

    def _drop_moves(self, player: int) -> List[Move]:
        candidates: List[Move] = []
        hand = self.hands[player]

        for piece, count in hand.items():
            if count <= 0:
                continue
            for row in range(BOARD_SIZE):
                for col in range(BOARD_SIZE):
                    if self.board[row][col] != 0:
                        continue
                    if not self._is_legal_drop_square(piece, player, row, col):
                        continue
                    candidates.append(
                        Move(to_row=row, to_col=col, drop_piece=piece, promote=False)
                    )

        return candidates

    def _is_legal_drop_square(
        self, piece: int, player: int, row: int, col: int
    ) -> bool:
        if piece == PAWN:
            if not self._can_exist_on_row(piece, player, row):
                return False
            # 二歩
            sign = 1 if player == 1 else -1
            for r in range(BOARD_SIZE):
                sq = self.board[r][col]
                if sq == sign * PAWN:
                    return False
        elif piece in (LANCE, KNIGHT):
            if not self._can_exist_on_row(piece, player, row):
                return False
        return True

    def _is_illegal_pawn_drop_mate(self, player: int) -> bool:
        opponent = 3 - player
        if not self.is_in_check(opponent):
            return False
        replies = self._generate_legal_moves(opponent, validate_pawn_drop_mate=False)
        return len(replies) == 0

    def _apply_move(self, move: Move, player: int):
        sign = 1 if player == 1 else -1
        if move.drop_piece is not None:
            self.hands[player][move.drop_piece] -= 1
            self.board[move.to_row][move.to_col] = sign * move.drop_piece
            return

        moving_piece = self.board[move.from_row][move.from_col]
        captured_piece = self.board[move.to_row][move.to_col]

        if captured_piece != 0:
            captured_base = self._base_piece(abs(captured_piece))
            if captured_base != KING:
                self.hands[player][captured_base] += 1

        self.board[move.from_row][move.from_col] = 0

        if move.promote:
            promoted = self._promote_piece(abs(moving_piece))
            moving_piece = (1 if moving_piece > 0 else -1) * promoted

        self.board[move.to_row][move.to_col] = moving_piece

    def _snapshot(self):
        return (
            deepcopy(self.board),
            deepcopy(self.hands),
            self.current_player,
            self.game_over,
            self.winner,
            self.result,
            deepcopy(self.last_move),
            list(self._history),
            dict(self._position_counts),
        )

    def _restore_snapshot(self, snap):
        (
            self.board,
            self.hands,
            self.current_player,
            self.game_over,
            self.winner,
            self.result,
            self.last_move,
            self._history,
            self._position_counts,
        ) = snap

    def _movement_vectors(self, piece: int, player: int):
        forward = -1 if player == 1 else 1
        backward = 1 if player == 1 else -1

        if piece == PAWN:
            return [(forward, 0)], False
        if piece == LANCE:
            return [(forward, 0)], True
        if piece == KNIGHT:
            return [(2 * forward, -1), (2 * forward, 1)], False
        if piece == SILVER:
            return [
                (forward, -1),
                (forward, 0),
                (forward, 1),
                (backward, -1),
                (backward, 1),
            ], False
        if piece in (GOLD, PROM_PAWN, PROM_LANCE, PROM_KNIGHT, PROM_SILVER):
            return [
                (forward, -1),
                (forward, 0),
                (forward, 1),
                (0, -1),
                (0, 1),
                (backward, 0),
            ], False
        if piece == BISHOP:
            return [(-1, -1), (-1, 1), (1, -1), (1, 1)], True
        if piece == ROOK:
            return [(-1, 0), (1, 0), (0, -1), (0, 1)], True
        if piece == HORSE:
            return [(-1, -1), (-1, 1), (1, -1), (1, 1)], True
        if piece == DRAGON:
            return [(-1, 0), (1, 0), (0, -1), (0, 1)], True
        if piece == KING:
            return [
                (-1, -1),
                (-1, 0),
                (-1, 1),
                (0, -1),
                (0, 1),
                (1, -1),
                (1, 0),
                (1, 1),
            ], False
        return [], False

    def _extra_king_like_moves(self, piece: int, player: int):
        if piece == HORSE:
            return [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if piece == DRAGON:
            return [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        return []

    def is_in_check(self, player: int) -> bool:
        king_pos = self._find_king(player)
        if king_pos is None:
            return True

        king_row, king_col = king_pos
        opponent = 3 - player
        sign = 1 if opponent == 1 else -1

        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = self.board[row][col]
                if piece == 0 or piece * sign <= 0:
                    continue
                if self._can_attack(row, col, piece, king_row, king_col, opponent):
                    return True
        return False

    def _can_attack(
        self,
        row: int,
        col: int,
        piece_value: int,
        target_row: int,
        target_col: int,
        owner_player: int,
    ) -> bool:
        piece = abs(piece_value)
        vectors, sliding = self._movement_vectors(piece, owner_player)

        for d_row, d_col in vectors:
            cur_row, cur_col = row + d_row, col + d_col
            while 0 <= cur_row < BOARD_SIZE and 0 <= cur_col < BOARD_SIZE:
                if cur_row == target_row and cur_col == target_col:
                    return True
                if self.board[cur_row][cur_col] != 0 or not sliding:
                    break
                cur_row += d_row
                cur_col += d_col

        for d_row, d_col in self._extra_king_like_moves(piece, owner_player):
            cur_row, cur_col = row + d_row, col + d_col
            if 0 <= cur_row < BOARD_SIZE and 0 <= cur_col < BOARD_SIZE:
                if cur_row == target_row and cur_col == target_col:
                    return True

        return False

    def _find_king(self, player: int) -> Optional[Tuple[int, int]]:
        target = KING if player == 1 else -KING
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if self.board[row][col] == target:
                    return row, col
        return None

    def _record_position(self, checking_player: int):
        key = self._position_key()
        self._position_counts[key] = self._position_counts.get(key, 0) + 1
        self._history.append((key, checking_player))

    def _position_key(self) -> str:
        board_key = "/".join(",".join(str(cell) for cell in row) for row in self.board)
        hand_key = []
        for player in (1, 2):
            hand_key.append(
                ",".join(f"{piece}:{self.hands[player][piece]}" for piece in HAND_TYPES)
            )
        return f"{board_key}|{self.current_player}|{';'.join(hand_key)}"

    def _evaluate_terminal_state(self):
        if self._handle_repetition():
            return
        if self._handle_jishogi():
            return

        legal_moves = self._generate_legal_moves(
            self.current_player, validate_pawn_drop_mate=True
        )
        if legal_moves:
            return

        self.game_over = True
        if self.is_in_check(self.current_player):
            self.winner = 3 - self.current_player
            self.result = "checkmate"
        else:
            self.winner = None
            self.result = "stalemate"

    def _handle_repetition(self) -> bool:
        key = self._position_key()
        if self._position_counts.get(key, 0) < 4:
            return False

        same_positions = [
            idx for idx, item in enumerate(self._history) if item[0] == key
        ]
        if len(same_positions) < 4:
            return False

        last_four = same_positions[-4:]
        checkers = [self._history[idx][1] for idx in last_four]
        non_zero = [c for c in checkers if c != 0]

        self.game_over = True
        if len(non_zero) == 4 and len(set(non_zero)) == 1:
            self.winner = 3 - non_zero[0]
            self.result = "perpetual_check"
        else:
            self.winner = None
            self.result = "sennichite"
        return True

    def _handle_jishogi(self) -> bool:
        black_king = self._find_king(1)
        white_king = self._find_king(2)
        if black_king is None or white_king is None:
            return False

        if black_king[0] > 2 or white_king[0] < 6:
            return False

        black_points = self._impasse_points(1)
        white_points = self._impasse_points(2)

        if black_points >= 24 and white_points >= 24:
            self.game_over = True
            self.winner = None
            self.result = "jishogi"
            return True

        if black_points < 24 or white_points < 24:
            self.game_over = True
            self.winner = 2 if black_points < white_points else 1
            self.result = "jishogi"
            return True

        return False

    def _impasse_points(self, player: int) -> int:
        sign = 1 if player == 1 else -1
        points = 0

        for row in self.board:
            for piece in row:
                if piece * sign <= 0:
                    continue
                base = self._base_piece(abs(piece))
                if base == KING:
                    continue
                points += 5 if base in (ROOK, BISHOP) else 1

        for piece, count in self.hands[player].items():
            points += count * (5 if piece in (ROOK, BISHOP) else 1)

        return points

    def _is_promotion_mandatory(self, piece: int, player: int, to_row: int) -> bool:
        if piece in (PAWN, LANCE):
            return not self._can_exist_on_row(piece, player, to_row)
        if piece == KNIGHT:
            return not self._can_exist_on_row(piece, player, to_row)
        return False

    def _can_exist_on_row(self, piece: int, player: int, row: int) -> bool:
        if player == 1:
            if piece in (PAWN, LANCE):
                return row > 0
            if piece == KNIGHT:
                return row > 1
        else:
            if piece in (PAWN, LANCE):
                return row < 8
            if piece == KNIGHT:
                return row < 7
        return True

    def _is_in_promotion_zone(self, player: int, row: int) -> bool:
        return row <= 2 if player == 1 else row >= 6

    def _promote_piece(self, piece: int) -> int:
        if piece == PAWN:
            return PROM_PAWN
        if piece == LANCE:
            return PROM_LANCE
        if piece == KNIGHT:
            return PROM_KNIGHT
        if piece == SILVER:
            return PROM_SILVER
        if piece == BISHOP:
            return HORSE
        if piece == ROOK:
            return DRAGON
        return piece

    def _base_piece(self, piece: int) -> int:
        if piece == PROM_PAWN:
            return PAWN
        if piece == PROM_LANCE:
            return LANCE
        if piece == PROM_KNIGHT:
            return KNIGHT
        if piece == PROM_SILVER:
            return SILVER
        if piece == HORSE:
            return BISHOP
        if piece == DRAGON:
            return ROOK
        return piece
