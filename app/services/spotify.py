import time
from app.core.constants import SPOTIPY_AVAILABLE, SPOTIFY_CACHE_FILE
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

    def get_auth_manager(self):
        """Returns the auth manager if client id/secret are set."""
        client_id = self.config.get("spotify_client_id")
        client_secret = self.config.get("spotify_client_secret")
        if not client_id or not client_secret:
            return None
        
        return SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8888/callback",
            scope="user-library-read playlist-read-private playlist-read-collaborative",
            open_browser=False,
            cache_path=SPOTIFY_CACHE_FILE
        )

    def has_cached_token(self):
        """Checks if a valid cached token exists without prompting."""
        auth_manager = self.get_auth_manager()
        if not auth_manager: return False
        try:
            token = auth_manager.get_cached_token()
            return token is not None
        except:
            return False

    def initialize_client(self):
        """Initializes the Spotify client using config credentials."""
        if not SPOTIPY_AVAILABLE:
            self.logger.error("Spotipy not installed.")
            return False

        auth_manager = self.get_auth_manager()
        if not auth_manager:
            return False

        try:
            self.logger.info(f"Initializing SpotifyOAuth with cache: {SPOTIFY_CACHE_FILE}")
            
            # Diagnostic: check if we have a token
            token_info = auth_manager.get_cached_token()
            if token_info:
                self.logger.info(f"Successfully loaded cached Spotify token.")
            else:
                self.logger.warning(f"No cached Spotify token found.")

            self.sp = spotipy.Spotify(auth_manager=auth_manager)
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
