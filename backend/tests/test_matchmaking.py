import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import app, socketio  # noqa: E402
from handlers.matchmaking_handlers import reset_matchmaking_state  # noqa: E402
from game_store import ai_settings, client_games, game_clients, games  # noqa: E402


class TestMatchmaking(unittest.TestCase):
    def setUp(self):
        reset_matchmaking_state()
        games.clear()
        ai_settings.clear()
        client_games.clear()
        game_clients.clear()

    def test_pairing_and_role_assignment_othello(self):
        client1 = socketio.test_client(app)
        client2 = socketio.test_client(app)

        client1.emit(
            "start_matchmaking",
            {
                "player_name": "alice",
                "password": "pw-123",
                "game_type": "othello",
            },
        )
        received1 = client1.get_received()
        self.assertTrue(any(evt["name"] == "matchmaking_status" for evt in received1))

        client2.emit(
            "start_matchmaking",
            {
                "player_name": "bob",
                "password": "pw-123",
                "game_type": "othello",
            },
        )

        events1 = client1.get_received()
        events2 = client2.get_received()

        match1 = next(evt for evt in events1 if evt["name"] == "match_found")
        match2 = next(evt for evt in events2 if evt["name"] == "match_found")
        game_id = match1["args"][0]["game_id"]
        self.assertEqual(game_id, match2["args"][0]["game_id"])

        role_request = next(
            evt for evt in events1 if evt["name"] == "role_choice_required"
        )
        self.assertEqual(role_request["args"][0]["game_id"], game_id)

        client1.emit("choose_role_after_match", {"game_id": game_id, "role": "second"})

        post1 = client1.get_received()
        post2 = client2.get_received()

        role_assigned_1 = next(evt for evt in post1 if evt["name"] == "role_assigned")
        role_assigned_2 = next(evt for evt in post2 if evt["name"] == "role_assigned")

        self.assertEqual(role_assigned_1["args"][0]["your_seat"], "second")
        self.assertEqual(role_assigned_1["args"][0]["your_role"], "white")
        self.assertEqual(role_assigned_2["args"][0]["your_seat"], "first")
        self.assertEqual(role_assigned_2["args"][0]["your_role"], "black")

        self.assertTrue(any(evt["name"] == "game_state" for evt in post1))
        self.assertTrue(any(evt["name"] == "game_state" for evt in post2))

        client1.disconnect()
        client2.disconnect()


if __name__ == "__main__":
    unittest.main()
