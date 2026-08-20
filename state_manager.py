import json
from pathlib import Path
from typing import Dict, Optional

class StateManager:
    """
    Manages persistent library download state to enable fast incremental updates.
    Tracks the highest processed message ID per Telegram group/channel.
    """
    def __init__(self, state_file_path: Path):
        self.state_file_path = state_file_path
        self.state: Dict[str, int] = self._load_state()

    def _load_state(self) -> Dict[str, int]:
        """Loads state dictionary from JSON file."""
        if self.state_file_path.exists():
            try:
                with open(self.state_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_state(self):
        """Saves current state dictionary to JSON file."""
        try:
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            pass

    def get_last_message_id(self, chat_key: str) -> Optional[int]:
        """Gets highest message ID processed so far for a chat."""
        return self.state.get(str(chat_key))

    def update_last_message_id(self, chat_key: str, message_id: int):
        """Updates highest message ID for a chat if message_id is newer."""
        current_last = self.state.get(str(chat_key), 0)
        if message_id > current_last:
            self.state[str(chat_key)] = message_id
            self.save_state()
