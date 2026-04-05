import json
from enum import Enum
from typing import List, Tuple, Optional


class Player(Enum):
    BLACK = 1
    WHITE = 2
    EMPTY = 0


class GameState:
    def __init__(self):
        self.board = [[Player.EMPTY for _ in range(8)] for _ in range(8)]
        # 初期配置
        self.board[3][3] = Player.WHITE
        self.board[3][4] = Player.BLACK
        self.board[4][3] = Player.BLACK
        self.board[4][4] = Player.WHITE
        self.current_player = Player.BLACK
        self.game_over = False
        self.winner = None

    def get_valid_moves(self) -> List[Tuple[int, int]]:
        valid_moves = []
        opponent = Player.WHITE if self.current_player == Player.BLACK else Player.BLACK

        for row in range(8):
            for col in range(8):
                if self.board[row][col] == Player.EMPTY:
                    if self._is_valid_move(row, col, opponent):
                        valid_moves.append((row, col))
        return valid_moves

    def _is_valid_move(self, row: int, col: int, opponent: Player) -> bool:
        directions = [
            (-1, -1),
            (-1, 0),
            (-1, 1),
            (0, -1),
            (0, 1),
            (1, -1),
            (1, 0),
            (1, 1),
        ]

        for dx, dy in directions:
            if self._check_direction(row, col, dx, dy, opponent):
                return True
        return False

    def _check_direction(
        self, row: int, col: int, dx: int, dy: int, opponent: Player
    ) -> bool:
        x, y = row + dx, col + dy
        found_opponent = False

        while 0 <= x < 8 and 0 <= y < 8:
            if self.board[x][y] == opponent:
                found_opponent = True
            elif self.board[x][y] == self.current_player:
                return found_opponent
            else:
                break
            x, y = x + dx, y + dy
        return False

    def make_move(self, row: int, col: int) -> bool:
        if not self._is_valid_move(
            row,
            col,
            Player.WHITE if self.current_player == Player.BLACK else Player.BLACK,
        ):
            return False

        # 石を置く
        self.board[row][col] = self.current_player

        # ひっくり返す石を処理
        self._flip_stones(row, col)

        # プレイヤー交代
        next_player = (
            Player.WHITE if self.current_player == Player.BLACK else Player.BLACK
        )
        self.current_player = next_player

        # 次プレイヤーに合法手がなければパス処理
        if not self.get_valid_moves():
            previous_player = (
                Player.WHITE if next_player == Player.BLACK else Player.BLACK
            )
            self.current_player = previous_player

            # 両者とも合法手がなければ終局
            if not self.get_valid_moves():
                self.game_over = True
                self._determine_winner()

        return True

    def _flip_stones(self, row: int, col: int):
        directions = [
            (-1, -1),
            (-1, 0),
            (-1, 1),
            (0, -1),
            (0, 1),
            (1, -1),
            (1, 0),
            (1, 1),
        ]
        opponent = Player.WHITE if self.current_player == Player.BLACK else Player.BLACK

        for dx, dy in directions:
            if self._check_direction(row, col, dx, dy, opponent):
                x, y = row + dx, col + dy
                while self.board[x][y] == opponent:
                    self.board[x][y] = self.current_player
                    x, y = x + dx, y + dy

    def _determine_winner(self):
        black_count = sum(row.count(Player.BLACK) for row in self.board)
        white_count = sum(row.count(Player.WHITE) for row in self.board)

        if black_count > white_count:
            self.winner = Player.BLACK
        elif white_count > black_count:
            self.winner = Player.WHITE
        else:
            self.winner = None  # 引き分け

    def get_board_state(self) -> List[List[int]]:
        return [[cell.value for cell in row] for row in self.board]

    def get_game_info(self) -> dict:
        black_count = sum(row.count(Player.BLACK) for row in self.board)
        white_count = sum(row.count(Player.WHITE) for row in self.board)

        return {
            "board": self.get_board_state(),
            "current_player": self.current_player.value,
            "valid_moves": self.get_valid_moves(),
            "game_over": self.game_over,
            "winner": self.winner.value if self.winner else None,
            "black_count": black_count,
            "white_count": white_count,
        }
