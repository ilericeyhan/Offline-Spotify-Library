import os
import sys
import customtkinter as ctk

# --- Constants & Configuration ---
APP_NAME = "Offline Spotify Library"
APP_VERSION = "1.3.8"

# Standard cross-platform user data directory
USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME) if sys.platform == "darwin" else \
                os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)

if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(USER_DATA_DIR, "config.json")
HISTORY_FILE = os.path.join(USER_DATA_DIR, "history.json")
LOG_FILE = os.path.join(USER_DATA_DIR, "app.log")

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-library-read playlist-read-private playlist-read-collaborative"

# Set default theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Try importing spotipy
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
    from spotipy.exceptions import SpotifyException
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False
