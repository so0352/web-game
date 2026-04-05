import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from shogi_logic import ShogiGameState


class TestShogiLogic(unittest.TestCase):
    def test_initial_payload_shape(self):
        state = ShogiGameState()
        info = state.get_game_info()

        self.assertEqual(info["game_type"], "shogi")
        self.assertEqual(len(info["board"]), 9)
        self.assertEqual(len(info["board"][0]), 9)
        self.assertEqual(info["current_player"], 1)
        self.assertIn("black", info["hands"])
        self.assertIn("white", info["hands"])

    def test_basic_pawn_move(self):
        state = ShogiGameState()
        moved = state.make_move({"from": [6, 4], "to": [5, 4], "promote": False})

        self.assertTrue(moved)
        self.assertEqual(state.board[6][4], 0)
        self.assertEqual(state.board[5][4], 1)
        self.assertEqual(state.current_player, 2)

    def test_invalid_move_returns_false(self):
        state = ShogiGameState()
        moved = state.make_move({"from": [4, 4], "to": [3, 4], "promote": False})
        self.assertFalse(moved)


if __name__ == "__main__":
    unittest.main()
