import os
import customtkinter as ctk

# --- Constants & Configuration ---
APP_NAME = "Offline Spotify Library"
APP_VERSION = "1.3.0"
CONFIG_FILE = "config.json"
HISTORY_FILE = "history.json"
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
