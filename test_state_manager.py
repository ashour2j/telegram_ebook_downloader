import unittest
import tempfile
import json
from pathlib import Path
from state_manager import StateManager

class TestStateManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp_dir.name) / "test_state.json"
        self.manager = StateManager(self.state_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_state_empty(self):
        self.assertIsNone(self.manager.get_last_message_id("chat_1"))

    def test_update_and_save_state(self):
        self.manager.update_last_message_id("chat_1", 100)
        self.assertEqual(self.manager.get_last_message_id("chat_1"), 100)

        # Reload from disk
        reloaded = StateManager(self.state_file)
        self.assertEqual(reloaded.get_last_message_id("chat_1"), 100)

    def test_update_higher_id_only(self):
        self.manager.update_last_message_id("chat_1", 200)
        self.manager.update_last_message_id("chat_1", 150) # Should be ignored
        self.assertEqual(self.manager.get_last_message_id("chat_1"), 200)

if __name__ == "__main__":
    unittest.main()
