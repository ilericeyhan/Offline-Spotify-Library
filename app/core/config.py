import json
import os
import sys
from app.core.constants import CONFIG_FILE

class ConfigManager:
    """
    Manages loading and saving of application configuration.
    """
    DEFAULT_CONFIG = {
        "cookie_file": "",
        "output_path": os.path.join(os.path.expanduser("~"), "Music", "SpotDL"),
        "spotify_client_id": "",
        "spotify_client_secret": "",
        "spotify_user_id": "",
        "spotdl_path": "",
        "log_level": "INFO",
        "language": "en",
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
                    data = {**self.DEFAULT_CONFIG, **loaded}
                    cid_state = "SET" if data.get("spotify_client_id") else "EMPTY"
                    print(f"ConfigManager: Load success from {CONFIG_FILE}. CID: {cid_state}")
                    return data
            except Exception as e:
                print(f"ConfigManager: Error loading config file: {e}")
                return self.DEFAULT_CONFIG
        print(f"ConfigManager: Config file {CONFIG_FILE} not found. Using defaults.")
        return self.DEFAULT_CONFIG

    class SafeJSONEncoder(json.JSONEncoder):
        """Custom encoder to skip non-serializable objects."""
        def default(self, obj):
            try:
                return super().default(obj)
            except TypeError:
                return None # Skip or return str(obj) if you want to see what it was

    def save_config(self, bypass_safety=False):
        """Saves current config to JSON file atomically, stripping non-serializable objects."""
        import traceback
        temp_file = CONFIG_FILE + ".tmp"
        
        cid_mem = self.config.get("spotify_client_id")
        print(f"DEBUG: save_config(bypass={bypass_safety}) | CID in memory: {'SET' if cid_mem else 'EMPTY'}")
        
        # Log who is calling this
        stack = "".join(traceback.format_stack()[-5:])
        print(f"DEBUG: save_config caller stack:\n{stack}")

        try:
            # First, filter standard ephemeral keys (starting with _)
            def clean_ephemeral(obj):
                if isinstance(obj, dict):
                    return {k: clean_ephemeral(v) for k, v in obj.items() if not k.startswith('_')}
                elif isinstance(obj, list):
                    return [clean_ephemeral(i) for i in obj]
                return obj

            # Safety: Protect against wholesale config loss (corruption during load)
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, 'r') as f:
                        disk_data = json.load(f)
                        is_memory_empty = not self.config.get("spotify_client_id") and not self.config.get("library")
                        is_disk_populated = bool(disk_data.get("spotify_client_id")) or bool(disk_data.get("library"))
                        
                        # Extra hard safety: If memory is empty but disk had CID/Secret, NEVER overwrite unless bypass_safety is true
                        if not self.config.get("spotify_client_id") and disk_data.get("spotify_client_id") and not bypass_safety:
                            print("CRITICAL: Disk has CID but memory doesn't. Failsafe RESTORING from disk.")
                            self.config["spotify_client_id"] = disk_data["spotify_client_id"]
                            self.config["spotify_client_secret"] = disk_data.get("spotify_client_secret", "")

                        if not bypass_safety and is_memory_empty and is_disk_populated:
                            print("ConfigManager: Safety restoration triggered. Memory was empty but disk had data.")
                            self.config.update(disk_data)
                except Exception as e:
                    print(f"ConfigManager Safety Error: {e}")

            cid_to_write = self.config.get("spotify_client_id")
            print(f"ConfigManager: Writing to disk (bypass={bypass_safety}). CID to write: {'SET' if cid_to_write else 'EMPTY'}")
            clean_data = clean_ephemeral(self.config)
            
            # Diagnostic: Trace what's being written
            json_str = json.dumps(clean_data, indent=4, cls=self.SafeJSONEncoder)
            print(f"ConfigManager: JSON Preview (200 chars): {json_str[:200]}...")
            
            with open(temp_file, 'w') as f:
                f.write(json_str)
            
            # Atomic swap
            os.replace(temp_file, CONFIG_FILE)
            print("ConfigManager: Disk write complete.")
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            print(f"Error saving config: {e}")

    def get(self, key: str):
        return self.config.get(key, self.DEFAULT_CONFIG.get(key))
    
    def set(self, key: str, value, bypass_safety=False, force_logout=False):
        # Master Wipe Lockdown
        if key in ["spotify_client_id", "spotify_client_secret"]:
            is_empty = not str(value).strip()
            if is_empty and not force_logout:
                import traceback
                stack = "".join(traceback.format_stack()[-3:])
                print(f"!!! CRITICAL WIPE BLOCKED !!! Refusing to clear {key} without force_logout=True.\nCaller:\n{stack}")
                return
            
            print(f"ConfigManager: set({key}) = {'SET' if not is_empty else 'EMPTY'} (force={force_logout})")

        self.config[key] = value
        self.save_config(bypass_safety=bypass_safety)

    def update_config(self, updates: dict, bypass_safety=False, force_logout=False):
        """Updates multiple keys at once."""
        for k, v in updates.items():
            if k in ["spotify_client_id", "spotify_client_secret"]:
                is_empty = not str(v).strip()
                if is_empty and not force_logout:
                    print(f"!!! CRITICAL update_config WIPE BLOCKED !!! Skipping {k}")
                    continue
            self.config[k] = v
            
        self.save_config(bypass_safety=bypass_safety)

    def reset_defaults(self):
        """Resets config to defaults and saves."""
        print("ConfigManager: Resetting to defaults.")
        self.config = self.DEFAULT_CONFIG.copy()
        self.save_config(bypass_safety=True)
