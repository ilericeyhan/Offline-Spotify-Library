import re
import os
import sys
from datetime import datetime

def get_resource_path(relative_path: str) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # For development, use the directory containing main.py (root)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)

def normalize_spotify_url(url: str) -> str:
    """Strips query parameters and handles URI formats for Spotify URLs."""
    if not url: return ""
    # Standardize to URL format and strip noise
    url = url.strip().split('?')[0].split('&')[0].rstrip('/')
    if url.startswith('spotify:'):
        parts = url.split(':')
        if len(parts) >= 3:
            return f"https://open.spotify.com/{parts[1]}/{parts[2]}"
    return url

def get_safe_dirname(name: str) -> str:
    """Sanitizes a string for use as a directory name."""
    if not name: return "Untitled"
    
    # spotDL replacements (Smart quotes to straight)
    name = name.replace('’', "'").replace('“', '"').replace('”', '"')
    
    # Allow common characters found in playlist names to prevent mismatch
    keepcharacters = (' ', '.', '_', '-', '(', ')', '[', ']', '&', ',', '!', "'", '#', '+')
    return "".join(c for c in name if c.isalnum() or c in keepcharacters).strip()

def format_timestamp(iso_str: str) -> str:
    """Formats an ISO timestamp into a readable string."""
    if not iso_str: return "Never"
    try:
        # Check if it has a time component
        if "T" in iso_str:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        return iso_str
    except: return iso_str
