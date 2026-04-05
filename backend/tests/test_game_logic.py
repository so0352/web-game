import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from game_logic import GameState, Player


class TestGameLogic(unittest.TestCase):
    def test_initial_setup(self):
        state = GameState()
        info = state.get_game_info()

        self.assertEqual(info["black_count"], 2)
        self.assertEqual(info["white_count"], 2)
        self.assertEqual(info["current_player"], Player.BLACK.value)
        self.assertFalse(info["game_over"])

    def test_make_move_flips_stone(self):
        state = GameState()
        moved = state.make_move(2, 3)

        self.assertTrue(moved)
        self.assertEqual(state.board[2][3], Player.BLACK)
        self.assertEqual(state.board[3][3], Player.BLACK)
        self.assertEqual(state.current_player, Player.WHITE)

    def test_invalid_move_returns_false(self):
        state = GameState()
        self.assertFalse(state.make_move(0, 0))


if __name__ == "__main__":
    unittest.main()
