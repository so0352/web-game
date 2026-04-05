import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import app, socketio  # noqa: E402
from game_store import ai_settings, client_games, game_clients, games  # noqa: E402
from handlers.matchmaking_handlers import reset_matchmaking_state  # noqa: E402


class TestShogiEngineScope(unittest.TestCase):
    def setUp(self):
        reset_matchmaking_state()
        games.clear()
        ai_settings.clear()
        client_games.clear()
        game_clients.clear()

    def test_set_ai_browser_scope_does_not_start_server_ai_turns(self):
        client = socketio.test_client(app)
        game_id = "shogi-browser-set-ai"

        client.emit(
            "create_game",
            {"game_id": game_id, "game_type": "shogi", "mode": "singleplayer"},
        )
        client.get_received()

        with patch("handlers.ai_handlers.run_shogi_ai_turns") as run_mock:
            client.emit(
                "set_ai",
                {
                    "game_id": game_id,
                    "color": "white",
                    "algorithm": "rule_based",
                    "engine": "rule_based",
                    "difficulty": "medium",
                    "engine_scope": "browser",
                },
            )
            client.get_received()

        self.assertEqual(run_mock.call_count, 0)
        self.assertEqual(ai_settings[game_id]["engine_scope"], "browser")
        client.disconnect()

    def test_make_move_browser_scope_does_not_start_server_ai_turns(self):
        client = socketio.test_client(app)
        game_id = "shogi-browser-move"

        client.emit(
            "create_game",
            {"game_id": game_id, "game_type": "shogi", "mode": "singleplayer"},
        )
        client.get_received()

        client.emit(
            "set_ai",
            {
                "game_id": game_id,
                "color": "black",
                "algorithm": "none",
                "engine": "none",
                "difficulty": "medium",
                "engine_scope": "browser",
            },
        )
        client.get_received()

        shogi_state = games[game_id]["state"]
        legal_move = shogi_state.get_valid_moves()[0].to_dict()

        with patch("handlers.move_handlers.run_shogi_ai_turns") as run_mock:
            client.emit("make_move", {"game_id": game_id, "move": legal_move})
            client.get_received()

        self.assertEqual(run_mock.call_count, 0)
        client.disconnect()


if __name__ == "__main__":
    unittest.main()
