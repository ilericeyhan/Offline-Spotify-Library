import json
import os
from datetime import datetime
from typing import List, Dict
from app.core.constants import HISTORY_FILE

class HistoryManager:
    """
    Manages persistent history of downloaded tracks/playlists.
    """
    def __init__(self):
        self.history = self.load_history()

    def load_history(self) -> List[Dict]:
        """Loads download history from JSON."""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def add_entry(self, source: str, tracks_or_count, name: str = None, error: str = None):
        """Adds a new entry to the history. tracks_or_count can be a list of tracks or a total count."""
        if isinstance(tracks_or_count, list):
            tracks = tracks_or_count
            count = len(tracks_or_count)
        else:
            tracks = []
            count = int(tracks_or_count)

        from datetime import timezone
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "source": source,
            "name": name,
            "tracks": tracks,
            "count": count
        }
        if error:
            entry["error"] = error
            
        self.history.append(entry)
        self.save_history()
        return entry

    def set_last_entry_interrupted(self, is_interrupted: bool, error: str = None):
        """Updates the 'interrupted' flag and optional error message of the most recent entry."""
        if self.history:
            self.history[-1]['interrupted'] = is_interrupted
            if error:
                self.history[-1]['error'] = error
            self.save_history()

    def save_history(self):
        """Saves history to JSON."""
        with open(HISTORY_FILE, 'w') as f:
            json.dump(self.history, f, indent=4)

    def clear_history(self):
        """Wipes all download history."""
        self.history = []
        self.save_history()
