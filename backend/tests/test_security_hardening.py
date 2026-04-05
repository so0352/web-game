import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import app, socketio  # noqa: E402
from game_store import ai_settings, client_games, game_clients, games  # noqa: E402
from handlers.matchmaking_handlers import (  # noqa: E402
    MATCH_SESSIONS,
    WAITING_QUEUES,
    reset_matchmaking_state,
)


class TestSecurityHardening(unittest.TestCase):
    def setUp(self):
        reset_matchmaking_state()
        games.clear()
        ai_settings.clear()
        client_games.clear()
        game_clients.clear()

    def test_matchmaking_does_not_store_plaintext_password(self):
        client1 = socketio.test_client(app)

        plaintext_password = "pw-123"
        client1.emit(
            "start_matchmaking",
            {
                "player_name": "alice",
                "password": plaintext_password,
                "game_type": "othello",
            },
        )

        self.assertEqual(len(WAITING_QUEUES), 1)
        queue_key = next(iter(WAITING_QUEUES.keys()))
        self.assertNotEqual(queue_key[1], plaintext_password)

        queue_entry = next(iter(WAITING_QUEUES.values()))[0]
        self.assertNotIn("password", queue_entry)
        self.assertNotEqual(queue_entry["password_fingerprint"], plaintext_password)

        client2 = socketio.test_client(app)
        client2.emit(
            "start_matchmaking",
            {
                "player_name": "bob",
                "password": plaintext_password,
                "game_type": "othello",
            },
        )

        self.assertEqual(len(MATCH_SESSIONS), 1)
        session = next(iter(MATCH_SESSIONS.values()))
        self.assertNotIn("password", session)
        self.assertIn("password_hash", session)
        self.assertNotEqual(session["password_hash"], plaintext_password)

        client1.disconnect()
        client2.disconnect()

    def test_reset_game_rejects_non_owner_singleplayer(self):
        owner = socketio.test_client(app)
        attacker = socketio.test_client(app)

        game_id = "sec-reset-test"
        owner.emit(
            "create_game",
            {"game_id": game_id, "game_type": "othello", "mode": "singleplayer"},
        )
        owner.get_received()

        attacker.emit("reset_game", {"game_id": game_id, "game_type": "othello"})
        attacker_events = attacker.get_received()

        error_event = next(evt for evt in attacker_events if evt["name"] == "error")
        self.assertIn(
            "このゲームをリセットする権限がありません", error_event["args"][0]["message"]
        )

        owner.disconnect()
        attacker.disconnect()


if __name__ == "__main__":
    unittest.main()
