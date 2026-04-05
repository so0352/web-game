import unittest
from unittest.mock import patch

from game_store import (
    ai_runtime_state,
    ai_settings,
    ensure_ai_settings,
    games,
    set_game_entry,
)  # noqa: E402
from handlers.shogi_ai_support import (
    run_shogi_ai_turns,
    start_shogi_ai_turns_if_needed,
)  # noqa: E402
from shogi_ai import select_shogi_move  # noqa: E402
from shogi_logic import ShogiGameState  # noqa: E402


class TestShogiAI(unittest.TestCase):
    class FakeSocketIO:
        def __init__(self):
            self.started_tasks = []
            self.emitted = []

        def start_background_task(self, func, *args):
            self.started_tasks.append((func, args))
            return None

        def emit(self, event, payload, room=None):
            self.emitted.append((event, payload, room))

        def sleep(self, _seconds):
            return None

    def setUp(self):
        games.clear()
        ai_settings.clear()
        ai_runtime_state.clear()

    def _assert_move_is_legal(self, state, move_payload):
        legal_moves = [move.to_dict() for move in state.get_valid_moves()]
        self.assertIn(move_payload, legal_moves)

    def test_rule_based_returns_legal_move(self):
        state = ShogiGameState()
        move = select_shogi_move(
            state,
            {
                "engine": "rule_based",
                "difficulty": "medium",
            },
        )
        self.assertIsNotNone(move)
        self._assert_move_is_legal(state, move)

    def test_start_shogi_ai_turns_if_needed_starts_for_shogi_ai_game(self):
        game_id = "game-test"
        set_game_entry(game_id, "shogi", ShogiGameState())
        settings = ensure_ai_settings(game_id)
        settings["black_ai"] = {"engine": "rule_based", "game_type": "shogi"}

        socketio = self.FakeSocketIO()

        started = start_shogi_ai_turns_if_needed(socketio, game_id, max_turns=3)

        self.assertTrue(started)
        self.assertEqual(len(socketio.started_tasks), 1)

    def test_ai_thinking_is_emitted_to_room_and_sid(self):
        game_id = "game-test"
        sid = "sid-123"
        state = ShogiGameState()
        set_game_entry(game_id, "shogi", state)
        settings = ensure_ai_settings(game_id)
        settings["black_ai"] = {"engine": "rule_based", "game_type": "shogi"}

        socketio = self.FakeSocketIO()

        def pick_first_legal_move(game, _config, **_kwargs):
            return game.get_valid_moves()[0].to_dict()

        with patch(
            "handlers.shogi_ai_support.select_shogi_move",
            side_effect=pick_first_legal_move,
        ):
            started = run_shogi_ai_turns(socketio, game_id, max_turns=1, sid=sid)
            self.assertTrue(started)

            task, args = socketio.started_tasks[0]
            task(*args)

        thinking_events = [
            (event, payload, room)
            for event, payload, room in socketio.emitted
            if event == "ai_thinking"
        ]

        self.assertGreaterEqual(len(thinking_events), 4)
        self.assertEqual(thinking_events[0][1]["active"], True)
        self.assertEqual(thinking_events[0][2], game_id)
        self.assertEqual(thinking_events[1][1]["active"], True)
        self.assertEqual(thinking_events[1][2], sid)
        self.assertEqual(thinking_events[2][1]["active"], False)
        self.assertEqual(thinking_events[2][2], game_id)
        self.assertEqual(thinking_events[3][1]["active"], False)
        self.assertEqual(thinking_events[3][2], sid)

    def test_minimax_is_deterministic_on_same_state(self):
        config = {
            "engine": "minimax",
            "difficulty": "medium",
            "minmax_depth": 2,
        }

        state_a = ShogiGameState()
        state_b = ShogiGameState()
        move_a = select_shogi_move(state_a, config)
        move_b = select_shogi_move(state_b, config)

        self.assertEqual(move_a, move_b)
        self._assert_move_is_legal(state_a, move_a)

    def test_mcts_returns_legal_move(self):
        state = ShogiGameState()
        move = select_shogi_move(
            state,
            {
                "engine": "mcts",
                "difficulty": "easy",
                "mcts_iterations": 40,
            },
        )
        self.assertIsNotNone(move)
        self._assert_move_is_legal(state, move)

    def test_onnx_fallback_returns_legal_move(self):
        state = ShogiGameState()
        move = select_shogi_move(
            state,
            {
                "engine": "onnx",
                "difficulty": "easy",
            },
        )
        self.assertIsNotNone(move)
        self._assert_move_is_legal(state, move)

    def test_ml_engine_returns_legal_move_when_model_unavailable(self):
        state = ShogiGameState()
        move = select_shogi_move(
            state,
            {
                "engine": "ml",
                "difficulty": "medium",
            },
        )
        self.assertIsNotNone(move)
        self._assert_move_is_legal(state, move)

    def test_select_shogi_move_stops_when_cancelled(self):
        state = ShogiGameState()
        move = select_shogi_move(
            state,
            {
                "engine": "mcts",
                "difficulty": "medium",
                "mcts_iterations": 120,
            },
            should_stop=lambda: True,
        )
        self.assertIsNone(move)

    def test_ai_turn_task_schedules_follow_up_when_ai_turn_remains(self):
        game_id = "game-test"
        state = ShogiGameState()
        set_game_entry(game_id, "shogi", state)
        settings = ensure_ai_settings(game_id)
        settings["black_ai"] = {"engine": "rule_based", "game_type": "shogi"}
        settings["white_ai"] = {"engine": "rule_based", "game_type": "shogi"}

        socketio = self.FakeSocketIO()

        def pick_first_legal_move(game, _config, **_kwargs):
            return game.get_valid_moves()[0].to_dict()

        with patch(
            "handlers.shogi_ai_support.select_shogi_move",
            side_effect=pick_first_legal_move,
        ):
            started = run_shogi_ai_turns(socketio, game_id, max_turns=1, sid="sid-1")
            self.assertTrue(started)
            self.assertEqual(len(socketio.started_tasks), 1)

            task, args = socketio.started_tasks[0]
            task(*args)

        self.assertEqual(len(socketio.started_tasks), 2)
        self.assertEqual(game_id in games, True)
        self.assertIsNotNone(ai_runtime_state.get(game_id))


if __name__ == "__main__":
    unittest.main()
