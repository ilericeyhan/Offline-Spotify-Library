import time
from app.core.constants import SPOTIPY_AVAILABLE
from app.core.config import ConfigManager
from app.services.logger import LogService

if SPOTIPY_AVAILABLE:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
    from spotipy.exceptions import SpotifyException

class SpotifyService:
    def __init__(self, config: ConfigManager, logger: LogService):
        self.config = config
        self.logger = logger
        self.sp = None
        self.status_callback = None

    def set_status_callback(self, callback):
        """Sets a callback(str) -> None for status updates."""
        self.status_callback = callback

    def update_status(self, message):
        if self.status_callback:
            self.status_callback(message)

    def initialize_client(self):
        """Initializes the Spotify client using config credentials."""
        if not SPOTIPY_AVAILABLE:
            self.logger.error("Spotipy not installed.")
            return False

        client_id = self.config.get("spotify_client_id")
        client_secret = self.config.get("spotify_client_secret")

        if not client_id or not client_secret:
            return False

        try:
            # Simple credentials flow for public data
            # For user library, we might need OAuth (handled elsewhere or here?)
            # The original app used SpotifyOAuth for user library.
            
            # Replicating original logic: 
            # It seems main.py used SpotifyOAuth for almost everything if user logged in.
            
            self.sp = spotipy.Spotify(
                auth_manager=SpotifyOAuth(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri="http://127.0.0.1:8888/callback",
                    scope="user-library-read playlist-read-private playlist-read-collaborative",
                    open_browser=True,
                    cache_path=".cache"
                )
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Spotify: {e}")
            return False

    def safe_call(self, func, *args, **kwargs):
        """Wraps Spotify API calls with rate limit handling."""
        if not self.sp:
            return None

        retries = 0
        max_retries = 3

        while retries <= max_retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Check for 429
                is_rate_limit = False
                wait_time = 0
                
                if hasattr(e, 'http_status') and e.http_status == 429:
                    is_rate_limit = True
                    retry_after = int(e.headers.get("Retry-After", 1))
                    wait_time = retry_after + 1
                
                if is_rate_limit:
                    if wait_time > 600:
                         self.logger.error(f"EXTREME API Rate Limit: {wait_time}s. Aborting.")
                         self.update_status(None)
                         raise Exception(f"Extreme Rate Limit: {wait_time}s")
                    
                    self.logger.info(f"Rate limited. Waiting {wait_time}s...")
                    self.update_status(f"Rate Limited: Waiting {wait_time}s")
                    time.sleep(wait_time)
                    retries += 1
                    
                    if retries > max_retries:
                         self.update_status(None)
                         raise e
                else:
                    raise e
        return None
    def get_playlist_tracks_with_dates(self, playlist_id):
        """Fetches list of (track_name, added_at_iso_string) for a playlist."""
        if not self.sp:
            return []

        tracks = []
        try:
            results = self.safe_call(self.sp.playlist_items, playlist_id, fields="items(added_at,track(name,artists(name))),next")
            while results:
                for item in results['items']:
                    if item.get('track'):
                        name = item['track']['name']
                        artists = ", ".join([a['name'] for a in item['track']['artists']])
                        full_name = f"{artists} - {name}"
                        added_at = item.get('added_at')
                        tracks.append((full_name, added_at))
                
                if results.get('next'):
                    results = self.safe_call(self.sp.next, results)
                else:
                    results = None
        except Exception as e:
            self.logger.error(f"Error fetching tracks with dates: {e}")
            
        return tracks
