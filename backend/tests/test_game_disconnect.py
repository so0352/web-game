import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from game_store import (  # noqa: E402
    ai_runtime_state,
    ai_settings,
    client_games,
    game_clients,
    games,
    register_client_game,
    unregister_client_game,
    ensure_ai_settings,
    set_game_entry,
)
from shogi_logic import ShogiGameState  # noqa: E402


class TestDisconnectCleanup(unittest.TestCase):
    def setUp(self):
        games.clear()
        ai_settings.clear()
        client_games.clear()
        game_clients.clear()
        ai_runtime_state.clear()

    def test_unregister_client_game_removes_orphaned_game(self):
        game_id = "game-test"
        set_game_entry(game_id, "shogi", ShogiGameState())
        ensure_ai_settings(game_id)
        register_client_game("sid-1", game_id)

        self.assertIn(game_id, games)
        self.assertIn(game_id, ai_settings)

        unregister_client_game("sid-1")

        self.assertNotIn(game_id, games)
        self.assertNotIn(game_id, ai_settings)
        self.assertNotIn(game_id, game_clients)


if __name__ == "__main__":
    unittest.main()
