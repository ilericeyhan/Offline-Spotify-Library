import json
import os
from app.core.constants import CONFIG_FILE

class ConfigManager:
    """
    Manages loading and saving of application configuration.
    """
    DEFAULT_CONFIG = {
        "cookie_file": "",
        "output_path": os.getcwd(),
        "spotify_client_id": "",
        "spotify_client_secret": "",
        "spotify_user_id": "",
        "spotdl_path": "",
        "log_level": "INFO",
        "library": [],  # List of dicts: {"url": "...", "name": "...", "type": "playlist/user"}
        "ignored_library_urls": [], # URLs that should not be auto-added from history
        "playlist_usage": {} # Dict: {"playlist_id_or_name": count}
    }

    def __init__(self):
        self.config = self.load_config()

    def increment_playlist_usage(self, playlist_id):
        """Increments the usage count for a playlist."""
        usage = self.config.get("playlist_usage", {})
        count = usage.get(playlist_id, 0)
        usage[playlist_id] = count + 1
        self.set("playlist_usage", usage)


    def load_config(self):
        """Loads config from JSON file or returns defaults."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    return {**self.DEFAULT_CONFIG, **loaded}
            except Exception as e:
                print(f"Error loading config: {e}")
                return self.DEFAULT_CONFIG
        return self.DEFAULT_CONFIG

    def save_config(self):
        """Saves current config to JSON file."""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key: str):
        return self.config.get(key, self.DEFAULT_CONFIG.get(key))
    
    def set(self, key: str, value):
        self.config[key] = value
        self.save_config()

    def reset_defaults(self):
        """Resets config to defaults and saves."""
        self.config = self.DEFAULT_CONFIG.copy()
        self.save_config()
