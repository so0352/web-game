import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import app, socketio  # noqa: E402
from handlers.matchmaking_handlers import reset_matchmaking_state  # noqa: E402
from game_store import ai_settings, client_games, game_clients, games  # noqa: E402


class TestMultiplayerModeGuard(unittest.TestCase):
    def setUp(self):
        reset_matchmaking_state()
        games.clear()
        ai_settings.clear()
        client_games.clear()
        game_clients.clear()

    def _create_matched_clients(self, game_type):
        client1 = socketio.test_client(app)
        client2 = socketio.test_client(app)

        client1.emit(
            "start_matchmaking",
            {"player_name": "alice", "password": "pw-123", "game_type": game_type},
        )
        client1.get_received()

        client2.emit(
            "start_matchmaking",
            {"player_name": "bob", "password": "pw-123", "game_type": game_type},
        )

        events1 = client1.get_received()
        events2 = client2.get_received()
        game_id = next(evt for evt in events1 if evt["name"] == "match_found")["args"][
            0
        ]["game_id"]

        self.assertTrue(any(evt["name"] == "match_found" for evt in events2))

        # creator(client1) chooses second so guest(client2) is first
        client1.emit("choose_role_after_match", {"game_id": game_id, "role": "second"})
        client1.get_received()
        client2.get_received()

        return client1, client2, game_id

    def test_multiplayer_blocks_set_ai_othello(self):
        client1, client2, game_id = self._create_matched_clients("othello")

        client1.emit(
            "set_ai",
            {
                "game_id": game_id,
                "color": "black",
                "algorithm": "minmax",
                "difficulty": "medium",
                "depth": 3,
            },
        )

        events = client1.get_received()
        error_event = next(evt for evt in events if evt["name"] == "error")
        self.assertIn(
            "マルチプレイではAI設定は利用できません", error_event["args"][0]["message"]
        )

        client1.disconnect()
        client2.disconnect()

    def test_multiplayer_turn_guard_othello(self):
        client1, client2, game_id = self._create_matched_clients("othello")

        # client1 is second(white) here and cannot play first move
        client1.emit("make_move", {"game_id": game_id, "row": 2, "col": 3})

        events = client1.get_received()
        error_event = next(evt for evt in events if evt["name"] == "error")
        self.assertIn(
            "現在あなたのターンではありません", error_event["args"][0]["message"]
        )

        client1.disconnect()
        client2.disconnect()

    def test_multiplayer_blocks_set_ai_shogi(self):
        client1, client2, game_id = self._create_matched_clients("shogi")

        client1.emit(
            "set_ai",
            {
                "game_id": game_id,
                "color": "black",
                "algorithm": "rule_based",
                "engine": "rule_based",
                "difficulty": "medium",
            },
        )

        events = client1.get_received()
        error_event = next(evt for evt in events if evt["name"] == "error")
        self.assertIn(
            "マルチプレイではAI設定は利用できません", error_event["args"][0]["message"]
        )

        client1.disconnect()
        client2.disconnect()


if __name__ == "__main__":
    unittest.main()
