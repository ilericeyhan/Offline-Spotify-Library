import subprocess
import time
import re
import os
from app.core.config import ConfigManager
from app.core.history import HistoryManager
from app.services.logger import LogService

class DownloaderService:
    def __init__(self, config: ConfigManager, history: HistoryManager, logger: LogService):
        self.config = config
        self.history = history
        self.logger = logger
        self.active_process = None

    def download(self, url, playlist_name=None, status_callback=None, **kwargs):
        cwd = kwargs.get('cwd')
        
        print(f"DEBUG: DownloaderService.download called with url={url}, cwd={cwd}")
        """
        Synchronously runs spotdl download for a given URL.
        Returns (success: bool, downloaded_tracks: list)
        blocks until finished.
        """
        spotdl_path = self.config.get("spotdl_path")
        output_path = self.config.get("output_path")
        cookie_file = self.config.get("cookie_file")
        
        if not spotdl_path:
            # Fallback to system path
            spotdl_path = "spotdl"

        # Construct Command
        cmd = [spotdl_path, url, "--output", "{artists} - {title}.{output-ext}", "--overwrite", "skip"]
        
        # Add cookie file if provided
        if cookie_file and os.path.exists(cookie_file):
             cmd.extend(["--cookie-file", cookie_file])

        # Prepare working directory
        if not cwd:
            cwd = output_path
            
        if not os.path.exists(cwd):
            try:
                os.makedirs(cwd)
            except: pass

        self.logger.info(f"Starting download for: {url}")
        
        max_retries = 6
        downloaded_tracks = []
        failed_tracks = []
        process_output = []

        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"Attempt {attempt}/{max_retries}...")
                
                # Use subprocess.Popen to read output in real-time
                 # IMPORTANT: encoding='utf-8', errors='replace' for stability
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=cwd,
                    bufsize=1,
                    encoding='utf-8',
                    errors='replace'
                )
                self.active_process = process

                if status_callback:
                    status_callback(f"Starting attempt {attempt}...")

                rate_limit_detected = False
                has_provider_errors = False
                
                # Real-time output reading
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.logger.log(line)
                        process_output.append(line)
                        
                        # Provider Error Detection (Phase 104)
                        if "AudioProviderError" in line or "LookupError" in line or "YT-DLP download error" in line:
                            has_provider_errors = True
                            
                            # Phase 108: Extract failed track name if possible
                            # Log format often: "AudioProviderError: ... - https://..." or "LookupError: ...: Artist - Title"
                            try:
                                if "LookupError" in line and "song:" in line:
                                    failed_name = line.split("song:")[1].strip()
                                    if failed_name not in failed_tracks: failed_tracks.append(failed_name)
                                elif "AudioProviderError" in line and "http" not in line:
                                     # Sometimes it's hard to get name from provider error without context, 
                                     # but we catch what we can.
                                     pass
                            except: pass
                        
                        # Rate Limit Detection
                        trig = line.lower()
                         # Refined: Only trigger for 429/Rate Limit related to Spotify
                        if ("429" in line or "rate/request limit" in trig or "max retries reached" in trig or "responseerror" in trig) and "spotify" in trig:
                            rate_limit_detected = True
                        
                        # Extreme Limit Detection
                        if "retry will occur after:" in trig:
                            try:
                                match = re.search(r"after:\s*(\d+)", trig)
                                if match:
                                    seconds = int(match.group(1))
                                    if seconds > 600:
                                        self.logger.error(f"CRITICAL: Extreme subprocess rate limit ({seconds}s). Aborting.")
                                        process.terminate()
                                        
                                        # Force History Entry (Phase 76)
                                        self.history.add_entry(url, downloaded_tracks, name=playlist_name)
                                        # (Interrupted status will be set by the UI caller)
                                        
                                        raise Exception("EXTREME_RATE_LIMIT_ABORT")
                            except Exception as e:
                                if str(e) == "EXTREME_RATE_LIMIT_ABORT": raise e
                                pass

                        # Track Detection
                        if 'Downloaded "' in line:
                             try:
                                track_name = line.split('Downloaded "')[1].split('"')[0]
                                if track_name not in downloaded_tracks:
                                    downloaded_tracks.append(track_name)
                                    if status_callback:
                                        status_callback(f"Downloaded: {track_name}")
                             except: pass

                process.wait()
                self.active_process = None
                
                if downloaded_tracks:
                     # Success (or partial success)
                     name = playlist_name
                     # Try to resolve name from config if missing (skipped here for simplicity, caller should provide)
                     
                     self.history.add_entry(url, downloaded_tracks, name=name)
                     
                     return (process.returncode == 0 and not has_provider_errors), downloaded_tracks, failed_tracks, False, None

                if process.returncode == 0:
                    if has_provider_errors:
                        self.logger.warning("Download finished with provider errors (No new tracks).")
                        self.history.add_entry(url, [], name=playlist_name)
                        self.history.save_history()
                        return False, [], failed_tracks, False, "Provider errors occurred (LookupError/AudioProviderError)"
                        
                    self.logger.info("Download finished (No new tracks).")
                    return True, [], [], False, None
                
                # Failure Handling
                self.logger.info(f"Attempt {attempt} failed code {process.returncode}")
                if attempt < max_retries:
                    if rate_limit_detected:
                        wait_time = min(300, 60 * attempt)
                        self.logger.info(f"Rate limited. Cooling down {wait_time}s...")
                        if status_callback: status_callback(f"Rate limited. Waiting {wait_time}s...")
                    else:
                        wait_time = 3
                    time.sleep(wait_time)
                
            except Exception as e:
                is_extreme = str(e) == "EXTREME_RATE_LIMIT_ABORT"
                if is_extreme:
                    if status_callback: status_callback("Aborted: Extreme Rate Limit")
                    error_msg = f"Extreme subprocess rate limit ({seconds}s). Aborted." if "seconds" in locals() else "Extreme rate limit aborted."
                    return False, downloaded_tracks, failed_tracks, True, error_msg
                
                self.logger.error(f"Error syncing {url}: {e}")
                if attempt < max_retries:
                    time.sleep(5)
                else:
                    return False, downloaded_tracks, failed_tracks, True, str(e)

        # All retries failed
        self.logger.error("All retry attempts failed.")
        
        # Force History Entry (Phase 78)
        self.history.add_entry(url, [], name=playlist_name)
        # (Interrupted status will be set by the UI caller)

        return False, [], failed_tracks, True, "All retry attempts failed."

    def terminate(self):
        """Kills the active process if any."""
        if self.active_process:
            self.active_process.terminate()
