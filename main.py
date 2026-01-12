#!/usr/bin/env python3
import customtkinter as ctk
import logging
import json
import os
import subprocess
import threading
import time
from tkinter import filedialog, messagebox, simpledialog
import shutil
from datetime import datetime
from typing import List, Dict, Optional
import requests
from PIL import Image
from io import BytesIO

# Try importing spotipy
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False

# --- Constants & Configuration ---
APP_NAME = "Offline Spotify Library"
APP_VERSION = "1.2.1"
CONFIG_FILE = "config.json"
HISTORY_FILE = "history.json"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-library-read playlist-read-private playlist-read-collaborative"

# Set default theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ConfigManager:
    """
    Manages loading and saving of application configuration.
    """
    DEFAULT_CONFIG = {
        "cookie_file": "/Users/ceyhan.ileri/OneDrive/Desktop/music.youtube.com_cookies",
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


    def load_config(self) -> Dict:
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

    def add_entry(self, source: str, tracks_or_count, name: str = None):
        """Adds a new entry to the history. tracks_or_count can be a list of tracks or a total count."""
        if isinstance(tracks_or_count, list):
            tracks = tracks_or_count
            count = len(tracks_or_count)
        else:
            tracks = []
            count = int(tracks_or_count)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "name": name,
            "tracks": tracks,
            "count": count
        }
        self.history.append(entry)
        self.save_history()

    def save_history(self):
        """Saves history to JSON."""
        with open(HISTORY_FILE, 'w') as f:
            json.dump(self.history, f, indent=4)


class GroupSelectDialog(ctk.CTkToplevel):
    """Custom dialog with a dropdown to select a destination group."""
    def __init__(self, parent, title, text, options):
        super().__init__(parent)
        self.title(title)
        self.geometry("300x200")
        self.transient(parent)   # Set as transient to parent
        self.grab_set()          # Modal dialog
        
        self.result = None
        
        label = ctk.CTkLabel(self, text=text, font=("Arial", 12))
        label.pack(pady=(20, 10), padx=20)
        
        self.option_menu = ctk.CTkOptionMenu(self, values=options)
        self.option_menu.pack(pady=10, padx=20)
        self.option_menu.set(options[0] if options else "")
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        ctk.CTkButton(btn_frame, text="Move", width=80, command=self._on_ok).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=80, command=self._on_cancel).pack(side="left", padx=10)
        
        # Center the dialog
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"300x200+{x}+{y}")
        
    def _on_ok(self):
        self.result = self.option_menu.get()
        self.destroy()
        
    def _on_cancel(self):
        self.result = None
        self.destroy()

    def get_input(self):
        self.master.wait_window(self)
        return self.result



class PlaylistSelectionDialog(ctk.CTkToplevel):
    """
    Dialog to select playlists from a Spotify User.
    """
    def __init__(self, parent, client_id, client_secret, default_user=""):
        super().__init__(parent)
        self.title("Select Playlists")
        self.geometry("600x500")
        self.client_id = client_id
        self.client_secret = client_secret
        self.selected_playlists = []
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # User ID Input
        self.lbl_user = ctk.CTkLabel(self, text="Enter Spotify User ID / Profile URL:")
        self.lbl_user.grid(row=0, column=0, padx=20, pady=(20, 5))
        
        self.entry_user = ctk.CTkEntry(self, placeholder_text="e.g. spotify:user:username")
        self.entry_user.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        if default_user:
             self.entry_user.insert(0, default_user)
        
        self.btn_fetch = ctk.CTkButton(self, text="Fetch Playlists", command=self.fetch_playlists)
        self.btn_fetch.grid(row=1, column=1, padx=20, pady=5)

        # Playlist List
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="nsew")

        # Buttons
        self.btn_confirm = ctk.CTkButton(self, text="Add Selected", command=self.confirm_selection)
        self.btn_confirm.grid(row=3, column=0, columnspan=2, pady=20)
        
        self.checkboxes = []

    def fetch_playlists(self):
        user_input = self.entry_user.get().strip()
        if not user_input:
            messagebox.showerror("Error", "Please enter a user ID or URL.")
            return

        # Initialize Spotipy
        if not self.client_id or not self.client_secret:
            messagebox.showerror("Error", "Spotify Client ID and Secret are required in Settings to fetch playlists.")
            return

        try:
            auth_manager = SpotifyClientCredentials(client_id=self.client_id, client_secret=self.client_secret)
            sp = spotipy.Spotify(auth_manager=auth_manager)
            
            # Extract username if full URL is given
            if "open.spotify.com/user/" in user_input:
                user_id = user_input.split("user/")[1].split("?")[0]
            else:
                user_id = user_input

            results = sp.user_playlists(user_id)
            playlists = results['items']
            while results['next']:
                results = sp.next(results)
                playlists.extend(results['items'])

            self.populate_list(playlists)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch playlists: {e}")

    def populate_list(self, playlists):
        # Clear existing
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.checkboxes = []

        for pl in playlists:
            var = ctk.BooleanVar()
            chk = ctk.CTkCheckBox(self.scroll_frame, text=pl['name'], variable=var)
            chk.pack(anchor="w", padx=10, pady=5)
            self.checkboxes.append({"var": var, "data": pl})

    def confirm_selection(self):
        for item in self.checkboxes:
            if item["var"].get():
                self.selected_playlists.append({
                    "name": item["data"]["name"],
                    "url": item["data"]["external_urls"]["spotify"]
                })
        self.destroy()

class SpotDLApp(ctk.CTk):
    """
    Main GUI Application Class.
    """
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x750")
        
        # Initialize Managers
        self.config_manager = ConfigManager()
        self.history_manager = HistoryManager()
        
        # Setup Logging based on config
        self.setup_logging()

        # Layout Layout
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # TabView
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        # Add Tabs (Library Priority)
        self.tab_library = self.tabview.add("Library")
        self.tab_profile = self.tabview.add("My Profile")
        self.tab_downloader = self.tabview.add("Downloader")
        self.tab_history = self.tabview.add("History") 
        self.tab_settings = self.tabview.add("Settings")
        self.tab_logs = self.tabview.add("Logs")
        self.tab_about = self.tabview.add("About/FAQ")
        
        # Set Default Tab
        self.tabview.set("Library")

        # Global Activity Indicator
        self.lbl_active_task = ctk.CTkLabel(self, text="", font=("Arial", 10, "italic"), text_color="gray")
        self.lbl_active_task.grid(row=1, column=0, sticky="e", padx=25, pady=(0, 10))

        # Session Tracking
        self.session_new_downloads = []
        self.feed_expanded = True  # Tracks if the download feed is visible

        # Drag-and-drop reordering state
        self.drag_item_index = -1
        self.drag_start_y = 0

        # Initialize UI Components
        # Initialize UI Components
        self.setup_profile_tab()
        self.setup_downloader_tab()
        self.setup_library_tab()
        self.setup_history_tab()
        self.setup_settings_tab()
        self.setup_logs_tab()
        self.setup_about_tab()

        # Initial Load with delay to ensure mainloop is ready
        self.after(800, self._startup_tasks)

    def _startup_tasks(self):
        """Runs initial background scans once the UI is ready."""
        self.update_profile_display()
        self.refresh_library_ui()

    def setup_logging(self):
        """Configures the logging module."""
        level_str = self.config_manager.get("log_level")
        level = getattr(logging, level_str.upper(), logging.INFO)
        
        # Setup File Handler
        logging.basicConfig(
            filename="spotdl_debug.log",
            level=logging.DEBUG, # Always debug to file for now
            format='%(asctime)s - %(levelname)s - %(message)s',
            filemode='w'
        )

        # Setup File Handler (Append mode to keep logs)
        logging.basicConfig(
            filename="spotdl_debug.log",
            level=logging.DEBUG, 
            format='%(asctime)s - %(levelname)s - %(message)s',
            filemode='a'
        )


        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        logging.info("Application started.")

    def setup_profile_tab(self):
        """Builds the My Profile tab."""
        self.tab_profile.grid_columnconfigure(0, weight=1)
        self.tab_profile.grid_rowconfigure(3, weight=1) 
        
        # --- Top Section: Profile Header ---
        self.frm_profile_header = ctk.CTkFrame(self.tab_profile, fg_color="transparent")
        self.frm_profile_header.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        self.frm_profile_header.grid_columnconfigure(1, weight=1)

        # Profile Picture
        self.lbl_profile_pic = ctk.CTkLabel(self.frm_profile_header, text="", width=100)
        self.lbl_profile_pic.grid(row=0, column=0, rowspan=4, padx=(0, 20))
        
        # Name & Info
        self.lbl_profile_name = ctk.CTkLabel(self.frm_profile_header, text="Unknown User", font=("Arial", 22, "bold"), anchor="w")
        self.lbl_profile_name.grid(row=0, column=1, sticky="w")
        
        self.lbl_profile_followers = ctk.CTkLabel(self.frm_profile_header, text="Followers: -", text_color="gray", anchor="w")
        self.lbl_profile_followers.grid(row=1, column=1, sticky="w")

        # Buttons
        self.frm_profile_actions = ctk.CTkFrame(self.frm_profile_header, fg_color="transparent")
        self.frm_profile_actions.grid(row=2, column=1, sticky="w", pady=5)
        
        self.btn_link_profile = ctk.CTkButton(self.frm_profile_actions, text="Login with Spotify", command=self.link_profile_dialog, fg_color="green", height=28)
        self.btn_refresh_profile = ctk.CTkButton(self.frm_profile_actions, text="Refresh", command=self.update_profile_display, width=80, height=28)
        self.btn_logout_profile = ctk.CTkButton(self.frm_profile_actions, text="Logout", command=self.logout_spotify, fg_color="red", hover_color="darkred", width=80, height=28)
        
        # --- Separator ---
        ctk.CTkFrame(self.tab_profile, height=2, fg_color="gray30").grid(row=1, column=0, sticky="ew", padx=20, pady=5)

        # --- Bottom Section: Playlist Manager ---
        self.lbl_playlists_title = ctk.CTkLabel(self.tab_profile, text="My Playlists", font=("Arial", 16, "bold"), anchor="w")
        self.lbl_playlists_title.grid(row=2, column=0, sticky="nw", padx=20, pady=(10, 5))

        # Search Bar
        self.entry_search_playlist = ctk.CTkEntry(self.tab_profile, placeholder_text="Search playlists...")
        self.entry_search_playlist.grid(row=2, column=0, sticky="ne", padx=20, pady=(10, 5))
        self.entry_search_playlist.bind("<KeyRelease>", self.filter_playlists)
        
        # Playlist Tabs (Created vs Followed)
        self.tv_playlists = ctk.CTkTabview(self.tab_profile, height=250)
        self.tv_playlists.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 10))
        
        self.tab_created = self.tv_playlists.add("Created by Me")
        self.tab_followed = self.tv_playlists.add("Followed Playlists")
        
        # Scrollable Frames inside Tabs
        self.tab_created.grid_columnconfigure(0, weight=1)
        self.tab_created.grid_rowconfigure(0, weight=1)
        self.scroll_created = ctk.CTkScrollableFrame(self.tab_created)
        self.scroll_created.grid(row=0, column=0, sticky="nsew")
        
        self.tab_followed.grid_columnconfigure(0, weight=1)
        self.tab_followed.grid_rowconfigure(0, weight=1)
        self.scroll_followed = ctk.CTkScrollableFrame(self.tab_followed)
        self.scroll_followed.grid(row=0, column=0, sticky="nsew")
        
        # Status Label (Feedback)
        self.lbl_profile_status = ctk.CTkLabel(self.tab_profile, text="", text_color="orange", height=20, font=("Arial", 12))
        self.lbl_profile_status.grid(row=4, column=0, sticky="ew", padx=20, pady=(5, 0))

        # Action Buttons
        self.frm_playlist_actions = ctk.CTkFrame(self.tab_profile, fg_color="transparent")
        self.frm_playlist_actions.grid(row=5, column=0, sticky="ew", padx=20, pady=10)

        
        self.var_subfolders = ctk.BooleanVar(value=True)
        self.chk_subfolders = ctk.CTkCheckBox(self.frm_playlist_actions, text="Create Subfolders", variable=self.var_subfolders)
        self.chk_subfolders.pack(side="left")

        self.btn_dl_selected = ctk.CTkButton(self.frm_playlist_actions, text="Download selected and add to the library", command=self.download_selected_playlists, state="disabled")
        self.btn_dl_selected.pack(side="right")
        
        self.profile_checkboxes = [] 
        self.all_fetched_playlists = [] # Store all for filtering

    def update_profile_display(self):
        """Fetches and displays the user profile if keys and user ID are present."""
        if not SPOTIPY_AVAILABLE:
            self.lbl_profile_name.configure(text="Spotipy Library Missing")
            return

        client_id = self.config_manager.get("spotify_client_id")
        client_secret = self.config_manager.get("spotify_client_secret")
        
        # Check if we have credentials
        if not (client_id and client_secret):
            self.lbl_profile_name.configure(text="Not logged in")
            self.btn_link_profile.pack(side="left")
            self.btn_refresh_profile.pack_forget()
            self.btn_logout_profile.pack_forget()
            return
        else:
            self.btn_link_profile.pack_forget()
            self.btn_refresh_profile.pack(side="left", padx=5)
            self.btn_logout_profile.pack(side="left", padx=5)

        self.lbl_profile_name.configure(text="Loading...")
        
        # Run in thread
        threading.Thread(target=self._fetch_profile_thread, args=(client_id, client_secret), daemon=True).start()

    def logout_spotify(self):
        """Clears Spotify credentials and session data."""
        if messagebox.askyesno("Logout", "Are you sure you want to logout from Spotify?"):
            self.config_manager.set("spotify_client_id", "")
            self.config_manager.set("spotify_client_secret", "")
            
            # Remove spotipy cache files
            try:
                folder = os.getcwd()
                for f in os.listdir(folder):
                    if f.startswith(".cache"):
                         os.remove(os.path.join(folder, f))
            except Exception as e:
                self.log_message(f"Error clearing Spotify cache: {e}")

            # Reset Profile UI
            self.lbl_profile_pic.configure(image=None, text="")
            self.lbl_profile_name.configure(text="Not logged in")
            self.lbl_profile_followers.configure(text="Followers: -")
            
            # Clear playlist lists
            for widget in self.scroll_created.winfo_children(): widget.destroy()
            for widget in self.scroll_followed.winfo_children(): widget.destroy()
            self.profile_checkboxes = []
            
            self.update_profile_display()
            self.log_message("Logged out from Spotify successfully.")
            
            if messagebox.askyesno("Login", "Would you like to login with a different account now?"):
                self.link_profile_dialog()

    def link_profile_dialog(self):
        """Opens a dialog to catch API details, with smart credential detection."""
        saved_cid = self.config_manager.get("spotify_client_id")
        saved_secret = self.config_manager.get("spotify_client_secret")
        
        if saved_cid and saved_secret:
            choice = messagebox.askyesnocancel("Spotify Login", 
                "Found saved Spotify API credentials in your settings.\n\n"
                "Would you like to use these existing credentials to login?\n\n"
                "Yes = Use Saved\nNo = Enter Manually\nCancel = Abort Login"
            )
            if choice is None: return # Abort
            if choice is True: # Use Saved
                # Skip dialog and go straight to profile update
                self.update_profile_display()
                return

        # Manual Entry Dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Login to Spotify")
        dialog.geometry("500x420")
        dialog.attributes("-topmost", True)
        
        ctk.CTkLabel(dialog, text="Spotify Authorization", font=("Arial", 16, "bold")).pack(pady=10)
        ctk.CTkLabel(dialog, text="To access private playlists, you need to authorize this app.").pack(pady=(0, 5))
        ctk.CTkLabel(dialog, text=f"Redirect URI: {REDIRECT_URI}", text_color="gray", font=("Arial", 10)).pack()
        
        ctk.CTkLabel(dialog, text="Client ID:").pack(anchor="w", padx=20, pady=(10,0))
        entry_cid = ctk.CTkEntry(dialog)
        entry_cid.insert(0, saved_cid or "")
        entry_cid.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(dialog, text="Client Secret:").pack(anchor="w", padx=20, pady=(10,0))
        entry_secret = ctk.CTkEntry(dialog, show="*")
        entry_secret.insert(0, saved_secret or "")
        entry_secret.pack(fill="x", padx=20, pady=5)
        
        def start_auth():
            cid = entry_cid.get().strip()
            secret = entry_secret.get().strip()
            if not cid or not secret:
                messagebox.showerror("Error", "Client ID and Secret are required.")
                return

            self.config_manager.set("spotify_client_id", cid)
            self.config_manager.set("spotify_client_secret", secret)
            
            messagebox.showinfo("Authorization", "1. Your browser will open to login to Spotify.\n"
                                               "2. After login, return here.\n\n"
                                               "Note: Large libraries take time. Please wait for the 'Ready' status.")
            
            try:
                # Trigger auth flow
                sp_oauth = SpotifyOAuth(client_id=cid, client_secret=secret, redirect_uri=REDIRECT_URI, scope=SCOPES)
            except: pass

            self.update_profile_display()
            dialog.destroy()
            
        ctk.CTkButton(dialog, text="Save & Login", command=start_auth, fg_color="green", hover_color="darkgreen").pack(pady=20)

    def _fetch_profile_thread(self, cid, secret):
        self.set_active_task("Login with Spotify")
        self.after(0, lambda: self.lbl_profile_status.configure(text="Authenticating with Spotify...", text_color="orange"))
        try:
            # Try OAuth first
            auth_manager = SpotifyOAuth(client_id=cid, client_secret=secret, redirect_uri=REDIRECT_URI, scope=SCOPES)
            sp = spotipy.Spotify(auth_manager=auth_manager)
            
            # Fetch Current User (Authenticated)
            try:
                self.log_message("Requesting Spotify profile information...")
                user = sp.current_user()
                if not user:
                    raise Exception("Failed to retrieve user profile.")
            except Exception as e:
                # Fallback to generic user if token fails or not authorized yet
                self.log_message(f"Spotify profile fetch failed: {e}")
                self.after(0, lambda: self.lbl_profile_name.configure(text="Login Required"))
                self.after(0, lambda: self.lbl_profile_status.configure(text="Login failed or cancelled", text_color="red"))
                return

            display_name = user.get("display_name", "Unknown")
            self.last_spotify_user_id = user['id'] # Store for re-sorting later
            followers = user.get("followers", {}).get("total", 0)
            images = user.get("images", [])
            
            image_payload = None
            if images:
                try:
                    img_url = images[0]["url"]
                    response = requests.get(img_url)
                    img_data = BytesIO(response.content)
                    pil_image = Image.open(img_data)
                    
                    # Crop to square
                    min_dim = min(pil_image.size)
                    left = (pil_image.size[0] - min_dim) / 2
                    top = (pil_image.size[1] - min_dim) / 2
                    right = (pil_image.size[0] + min_dim) / 2
                    bottom = (pil_image.size[1] + min_dim) / 2
                    pil_image = pil_image.crop((left, top, right, bottom))
                    
                    pil_image = pil_image.resize((100, 100), Image.Resampling.LANCZOS)
                    # DO NOT create ctk.CTkImage here (background thread). 
                    # Instead, pass the pil_image to the main thread.
                    image_payload = pil_image
                except Exception:
                    image_payload = None
            else:
                image_payload = None

            # 2. Fetch User Playlists
            playlists = []

            # A. Add Liked Songs
            try:
                saved = sp.current_user_saved_tracks(limit=1)
                total_saved = saved['total']
                if total_saved > 0:
                    playlists.append({
                        "name": "Liked Songs",
                        "tracks": {"total": total_saved},
                        "external_urls": {"spotify": "https://open.spotify.com/collection/tracks"},
                        "id": "saved_tracks"
                    })
            except Exception:
                pass

            # B. Add Normal Playlists
            self.after(0, lambda: self.lbl_profile_status.configure(text="Fetching playlists...", text_color="orange"))
            self.log_message("Fetching your playlists from Spotify...")
            try:
                results = sp.current_user_playlists(limit=50)
                if results and 'items' in results:
                    playlists.extend(results['items'])
                    while results['next']:
                        results = sp.next(results)
                        if results and 'items' in results:
                            playlists.extend(results['items'])
                        else:
                            break
                self.log_message(f"Found {len(playlists)} playlists on Spotify.")
            except Exception as e:
                self.log_message(f"Error fetching playlists: {e}")

            self.all_fetched_playlists = playlists 
            
            # Sort by Usage (Smart Sorting)
            usage = self.config_manager.get("playlist_usage") or {}
            
            def sort_key(p):
                if p['id'] == 'saved_tracks':
                    return (0, 0, "")
                return (1, -usage.get(p['id'], 0), p['name'].lower())
            
            self.all_fetched_playlists.sort(key=sort_key)
            
            # Split into Created/Followed
            # Note: SpotiPy's user['id'] returns the current user ID
            current_user_id = user['id']
            # Split Playlists
            created = []
            followed = []
            self.set_active_task("Splitting Playlists")
            
            for p in self.all_fetched_playlists:
                # "Liked Songs" has a dummy owner/id, treat as created
                if p['id'] == 'saved_tracks':
                     created.append(p)
                     continue
                     
                owner_id = str(p['owner']['id'])
                if owner_id == str(current_user_id):
                    created.append(p)
                else:
                    followed.append(p)

            # Update UI
            try:
                self.after(0, lambda: self._update_profile_ui(display_name, followers, image_payload, created, followed))
            except RuntimeError:
                pass # Main thread not ready or shutting down
            
        except Exception as e:
            try:
                self.after(0, lambda: self.lbl_profile_name.configure(text=f"Error: {str(e)}"))
            except RuntimeError:
                pass

    def filter_playlists(self, event=None):
        """Filters the playlist list based on search text."""
        query = self.entry_search_playlist.get().lower()
        
        # We need to re-split since filter applies to raw list
        # We can't easily re-split without knowing user ID again, 
        # so let's store the split lists in self or re-derive ownership check if possible.
        # Actually simplest is to just filter the 'all' list and re-split locally.
        # But we don't have user_id here easily without fetching or clean approach.
        # Better: store 'created' and 'followed' as instance vars in update_ui?
        # Let's assume we filter what's currently stored? No.
        
        # Let's rely on cached 'self.profile_created_list' and 'self.profile_followed_list'
        # which we will set in _update_profile_ui.
        
        # Only if initialized
        if not hasattr(self, 'cached_created') or not hasattr(self, 'cached_followed'):
             return

        filtered_created = [p for p in self.cached_created if query in p['name'].lower()]
        filtered_followed = [p for p in self.cached_followed if query in p['name'].lower()]
        
        self._populate_list_generic(self.scroll_created, filtered_created)
        self._populate_list_generic(self.scroll_followed, filtered_followed)

    def _update_profile_ui(self, name, followers, image_payload, created, followed):
        # Update Header
        self.lbl_profile_name.configure(text=name)
        self.lbl_profile_followers.configure(text=f"{followers:,} followers")
        
        # Safe Image Config (Must happen in Main Thread)
        try:
            if image_payload:
                # Create CTkImage from PIL payload in the main thread
                ctk_img = ctk.CTkImage(light_image=image_payload, dark_image=image_payload, size=(100, 100))
                self.lbl_profile_pic.configure(image=ctk_img, text="")
            else:
                self.lbl_profile_pic.configure(image=None, text="[No Image]")
        except Exception as e:
            self.log_message(f"Error updating profile image: {e}")
            self.lbl_profile_pic.configure(image=None, text="[Error]")

        # Cache for searching
        self.cached_created = created
        self.cached_followed = followed

        # Clear and Reset Checkboxes
        self.profile_checkboxes = [] 

        # Populate
        self._populate_list_generic(self.scroll_created, created)
        self._populate_list_generic(self.scroll_followed, followed)
        
        # Trigger Library Discovery (Deep Scan) now that self.all_fetched_playlists is ready
        self.refresh_library_ui()

    def refresh_profile_lists(self):
        """Re-sorts cached playlists based on latest usage and refreshes UI."""
        if not hasattr(self, 'all_fetched_playlists'):
            return
            
        usage = self.config_manager.get("playlist_usage") or {}
        
        # Key: (Priority (0 for Saved, 1 for others), Usage Count (desc via negation), Name (asc))
        def sort_key(p):
            if p['id'] == 'saved_tracks':
                return (0, 0, "")
            # Negate usage to sort descending, Name is ascending
            return (1, -usage.get(p['id'], 0), p['name'].lower())
            
        self.all_fetched_playlists.sort(key=sort_key)
        
        # Split again
        cid = self.config_manager.get("spotify_user_id") # We should store this during auth
        # Fallback if id not stored: just use whatever we have in cache
        
        current_user_id = getattr(self, 'last_spotify_user_id', None)
        
        created = []
        followed = []
        for p in self.all_fetched_playlists:
            if p['id'] == 'saved_tracks':
                created.append(p)
                continue
            if current_user_id and p['owner']['id'] == current_user_id:
                created.append(p)
            else:
                followed.append(p)
        
        # Update cache for searching too
        self.cached_created = created
        self.cached_followed = followed
        
        # Populate
        self.after(0, lambda: self._populate_list_generic(self.scroll_created, created))
        self.after(0, lambda: self._populate_list_generic(self.scroll_followed, followed))

    def _populate_list_generic(self, scroll_frame, playlists):
        # Clear existing in this specific frame
        for widget in scroll_frame.winfo_children():
            widget.destroy()

        if not playlists:
             ctk.CTkLabel(scroll_frame, text="No playlists found.").pack(pady=10)
             return

        check_queue = [] # List of (playlist_data, status_label, checkbox_widget)

        def render_batch(start_idx):
            end_idx = min(start_idx + 10, len(playlists))
            for i in range(start_idx, end_idx):
                pl = playlists[i]
                try:
                    row = ctk.CTkFrame(scroll_frame)
                    row.pack(fill="x", pady=2)
                    
                    # Extract info safely
                    pl_name = pl.get('name') or "Untitled Playlist"
                    tracks_info = pl.get('tracks', {})
                    track_count = tracks_info.get('total', 0) if isinstance(tracks_info, dict) else 0
                    
                    # Render initial state
                    var = ctk.BooleanVar()
                    chk = ctk.CTkCheckBox(row, text=pl_name, variable=var, font=("Arial", 12))
                    chk.pack(side="left", padx=10, pady=5)
                    
                    lbl_status = ctk.CTkLabel(row, text="", font=("Arial", 10, "italic"))
                    lbl_status.pack(side="left")
                    
                    ctk.CTkLabel(row, text=f"{track_count} tracks", text_color="gray").pack(side="right", padx=10)
                    
                    # Append to GLOBAL checkboxes list so "Download Selected" finds them
                    self.profile_checkboxes.append({"var": var, "data": pl})
                    
                    # Add to background check queue
                    check_queue.append((pl, lbl_status, chk))
                    
                except Exception as e:
                    self.log_message(f"Skipping playlist rendering due to error: {e}")
                    continue
            
            if end_idx < len(playlists):
                self.after(10, lambda: render_batch(end_idx))
            else:
                # Finished rendering, start background status checker
                if check_queue:
                    threading.Thread(target=self._async_status_worker, args=(check_queue,), daemon=True).start()
                self.lbl_profile_status.configure(text="Ready", text_color="gray")

        # Start batch rendering
        if playlists:
            render_batch(0)
        else:
            self.lbl_profile_status.configure(text="Ready", text_color="gray")

    def _async_status_worker(self, queue):
        """Processes sync status checks in the background and updates UI."""
        self.set_active_task("Checking Profile Sync Status")
        
        # Build lookup map from library to handle imported/custom paths
        library = self.config_manager.get("library") or []
        lib_map = {self._normalize_spotify_url(item.get('url')): item for item in self._flatten_library(library) if item.get('url')}
        
        total = len(queue)
        for i, (pl, lbl, chk) in enumerate(queue):
            try:
                # Correctly handle Spotify object structure
                url = self._normalize_spotify_url(pl.get('external_urls', {}).get('spotify') or pl.get('url'))
                pl_name = pl.get('name') or "Untitled Playlist"
                tracks_info = pl.get('tracks', {})
                track_count = tracks_info.get('total', 0) if isinstance(tracks_info, dict) else 0
                
                # Check if this URL is in the library with potentially custom paths/metadata
                lib_item = lib_map.get(url)
                l_path = lib_item.get('local_path') if lib_item else pl.get('local_path')
                e_files = lib_item.get('expected_files') if lib_item else pl.get('expected_files')

                status_text, status_color, _ = self.get_playlist_sync_status(pl_name, track_count, l_path, e_files)
                
                is_synced = status_text.startswith("Synced")
                is_partial = status_text.startswith("Partial")
                text_color = "gray" if is_synced else None
                
                def _update(s_text=status_text, s_color=status_color, t_color=text_color, l=lbl, c=chk):
                    try:
                        if is_synced or is_partial:
                            l.configure(text=f"[{s_text}]", text_color=s_color)
                        if t_color:
                            c.configure(text_color=t_color)
                    except: pass # Widget might be destroyed if user switched tabs
                
                self.after(0, _update)
                
                # Periodically update status label with progress
                if i % 10 == 0:
                    self.after(0, lambda idx=i+1: self.lbl_profile_status.configure(text=f"Checking sync: {idx}/{total}..."))
                
            except Exception:
                continue

        self.set_active_task(None)
        self.after(0, lambda: self.lbl_profile_status.configure(text="Ready", text_color="gray"))

    def download_selected_playlists(self):
        selected = []
        full_synced = []
        partial_confirmed = []
        
        # Build lookup map to respect imported paths during download logic
        library = self.config_manager.get("library") or []
        lib_map = {self._normalize_spotify_url(item.get('url')): item for item in self._flatten_library(library) if item.get('url')}

        for item in self.profile_checkboxes:
            if item["var"].get():
                pl = item["data"]
                url = self._normalize_spotify_url(pl.get('url'))
                track_count = pl['tracks']['total']
                
                lib_item = lib_map.get(url)
                l_path = lib_item.get('local_path') if lib_item else None
                e_files = lib_item.get('expected_files') if lib_item else None
                
                status_text, _ = self.get_playlist_sync_status(pl['name'], track_count, l_path, e_files)
                
                if status_text.startswith("Synced"):
                    full_synced.append(pl['name'])
                elif status_text.startswith("Partial"):
                    if messagebox.askyesno("Partial Sync", f"'{pl['name']}' is partially synced ({status_text.split()[-1]}).\n\nWould you like to resume and download missing tracks?"):
                        selected.append(pl)
                        partial_confirmed.append(pl['name'])
                else:
                    selected.append(pl)

        if not selected:
            if full_synced:
                messagebox.showinfo("Skipped", f"Selected playlists are already fully synced:\n- " + "\n- ".join(full_synced))
            else:
                messagebox.showinfo("Select Playlists", "Please select at least one playlist to download.")
            return

        # Streamlined Confirmation:
        # Only prompt if there are ANY 'New' playlists OR if the list doesn't match confirmed partials
        total_selected = len(selected)
        total_confirmed = len(partial_confirmed)
        
        needs_final_confirm = (total_selected > total_confirmed) # True if there are New playlists
        
        if needs_final_confirm:
            msg = f"Download {total_selected} playlists?"
            if full_synced:
                msg += f"\n\n(Skipping {len(full_synced)} already synced playlists)"
                
            if not messagebox.askyesno("Confirm Download", msg):
                return

        # Prepare Queue with Pre-validated Paths
        download_queue = [] # List of {"data": pl, "cwd": path}
        base_path = self.config_manager.get("output_path")
        
        for pl in selected:
            name = pl['name']
            url = self._normalize_spotify_url(pl.get('url'))
            pl_id = pl.get('id', name)
            
            # Check usage
            usage = self.config_manager.get("playlist_usage") or {}
            usage[pl_id] = usage.get(pl_id, 0) + 1
            self.config_manager.set("playlist_usage", usage)
            
            target_cwd = None
            
            # 1. First priority: Use custom path if already in library
            lib_item = lib_map.get(url)
            if lib_item and lib_item.get('local_path') and os.path.exists(lib_item['local_path']):
                target_cwd = lib_item['local_path']
                self.log_message(f"Using existing library path for '{name}': {target_cwd}")
            else:
                # 2. Second priority: Subfolder logic
                use_subfolders = self.var_subfolders.get()
                if use_subfolders:
                    safe_name = self.get_safe_dirname(name).strip()
                    if not safe_name: safe_name = "Untitled_Playlist"
                    
                    while True:
                        full_path = os.path.join(base_path, safe_name)
                        try:
                            os.makedirs(full_path, exist_ok=True)
                            target_cwd = full_path
                            break 
                        except OSError as e:
                            safe_name = simpledialog.askstring("Error", f"Could not create folder '{safe_name}': {e}\nPlease enter a different name:", parent=self)
                            if not safe_name:
                                target_cwd = None
                                break
                else:
                    # 3. Third priority: Root output path
                    target_cwd = base_path

            download_queue.append({"data": pl, "cwd": target_cwd})

        self.btn_dl_selected.configure(state="disabled", text="Starting...")
        
        # Run batch download in thread
        threading.Thread(target=self.run_batch_profile_download, args=(download_queue,), daemon=True).start()

    def get_safe_dirname(self, name):
        """Removes invalid characters for folder names."""
        if not name:
            return "Untitled Playlist"
        invalid = '<>:"/\\|?*'
        for char in invalid:
            name = name.replace(char, '')
        return name.strip() or "Untitled Playlist"

    def _normalize_spotify_url(self, url):
        """Standardizes Spotify URLs by stripping query parameters and trailing slashes."""
        if not url: return ""
        # Strip query params like ?si=...
        url = url.split('?')[0]
        # Strip trailing slash
        url = url.rstrip('/')
        return url.strip()

    def get_playlist_sync_status(self, name, total_tracks, local_path=None, expected_files=None):
        """
        Returns (status_text, color, extras_count)
        If expected_files (cached list) is provided, it uses name-matching for 100% accuracy.
        """
        if local_path and os.path.exists(local_path):
            full_path = local_path
        else:
            safe_name = self.get_safe_dirname(name)
            base_path = self.config_manager.get("output_path")
            full_path = os.path.join(base_path, safe_name)
        
        if not os.path.exists(full_path):
            return "New", "gray", 0
            
        # Scan local folder
        try:
            files = [f for f in os.listdir(full_path) if os.path.isfile(os.path.join(full_path, f))]
            music_extensions = ('.mp3', '.flac', '.m4a', '.opus', '.ogg', '.wav')
            music_files = [f for f in files if f.lower().endswith(music_extensions)]
            count = len(music_files)
        except Exception:
            count = 0
            music_files = []
            
        if count == 0:
            return "New", "gray", 0
            
        if expected_files:
            # Smart Matching Logic
            expected_set = set(f.lower() for f in expected_files)
            synced_count = 0
            extras_list = []
            
            for f in music_files:
                base = os.path.splitext(f)[0].lower()
                if base in expected_set:
                    synced_count += 1
                else:
                    extras_list.append(f)
            
            # Non-music extras (excluding system/metadata)
            non_music_extras = []
            for f in files:
                if f.lower().endswith(music_extensions): continue
                if f.startswith('.') or f.lower() in ('desktop.ini', 'thumbs.db', 'playlist.json') or f.endswith('.spotdl-cache'):
                    continue
                non_music_extras.append(f)
                
            extras_count = len(extras_list) + len(non_music_extras)
            
            if synced_count >= len(expected_set):
                return "Synced", "green", extras_count
            else:
                return f"Partial ({synced_count}/{len(expected_set)})", "orange", extras_count
        else:
            # Fallback to simple math if no cache available
            extras = max(0, count - total_tracks)
            if count >= total_tracks:
                return "Synced", "green", extras
            else:
                return f"Partial ({count}/{total_tracks})", "orange", extras

    def run_batch_profile_download(self, download_queue):
        self.log_message("Starting Batch Download from Profile...")
        total = len(download_queue)
        successful_downloads = 0
        total_tracks = 0
        
        for i, item in enumerate(download_queue):
            pl = item["data"]
            target_cwd = item["cwd"]
            
            name = pl['name']
            url = pl['external_urls']['spotify']
            pl_id = pl.get('id', name) 
            
            # Increment Usage Stat
            self.config_manager.increment_playlist_usage(pl_id)
            
            self.log_message(f"[{i+1}/{total}] Processing: {name}")
            self.lbl_profile_status.configure(text=f"Processing [{i+1}/{total}]: {name}...")
            
            if target_cwd:
                 self.log_message(f"  -> Saving to: {os.path.basename(target_cwd)}")
            
            # Callback to update status with track name
            def update_status(track):
                self.lbl_profile_status.configure(text=f"[{i+1}/{total}] {name}: Downloading '{track}'...")

            success, count = self.download_synchronously(url, cwd=target_cwd, status_callback=update_status)
            if success:
                successful_downloads += 1
                total_tracks += count
        
        self.after(0, lambda: self._on_batch_complete(successful_downloads, total, total_tracks))

    def _on_batch_complete(self, success_count, total_count, track_count):
        self.btn_dl_selected.configure(state="normal", text="Download selected and add to the library")
        self.lbl_profile_status.configure(text=f"Done. Processed {total_count} playlists.", text_color="green")
        msg = f"Processed {total_count} playlists.\nSuccessfully downloaded {success_count}/{total_count}.\nTotal tracks: {track_count}"
        
        if success_count < total_count:
            msg += "\n\nSome downloads failed. Check Logs for details."
            
        if messagebox.askyesno("Batch Complete", f"{msg}\n\nOpen output directory?"):
            self.open_file_explorer()
            
        # Refresh the list order to show most recently used on top
        self.refresh_profile_lists()

    def open_file_explorer(self, path=None):
        if path is None:
            path = self.config_manager.get("output_path")
        
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        
        try:
            if os.name == 'nt': # Windows
                os.startfile(path)
            elif os.uname().sysname == 'Darwin': # macOS
                subprocess.Popen(['open', path])
            else: # Linux
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            self.log_message(f"Error opening directory: {e}")

    def setup_downloader_tab(self):
        """Builds the main Downloader tab UI."""
        self.tab_downloader.grid_columnconfigure(0, weight=1)
        
        # Header
        lbl_title = ctk.CTkLabel(self.tab_downloader, text="Quick Download", font=("Arial", 20, "bold"))
        lbl_title.grid(row=0, column=0, pady=(10, 20))

        # URL Input
        self.entry_url = ctk.CTkEntry(self.tab_downloader, placeholder_text="Enter Spotify Track or Playlist URL")
        self.entry_url.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        # Options Frame (Format Selection)
        frm_opts = ctk.CTkFrame(self.tab_downloader, fg_color="transparent")
        frm_opts.grid(row=2, column=0, pady=5)
        
        ctk.CTkLabel(frm_opts, text="Format:").pack(side="left", padx=5)
        self.opt_format = ctk.CTkOptionMenu(frm_opts, values=["mp3", "flac", "m4a", "opus", "ogg", "wav"], width=100)
        self.opt_format.set("mp3") # Default
        self.opt_format.pack(side="left", padx=5)

        # Download Button
        self.btn_download = ctk.CTkButton(self.tab_downloader, text="Download", command=self.start_download)
        self.btn_download.grid(row=3, column=0, padx=20, pady=10)

        # Progress / Status
        self.lbl_status = ctk.CTkLabel(self.tab_downloader, text="Ready", text_color="gray")
        self.lbl_status.grid(row=4, column=0, pady=10)

    def setup_library_tab(self):
        """Builds the Library tab for syncing playlists."""
        self.tab_library.grid_columnconfigure(0, weight=1)
        self.tab_library.grid_rowconfigure(1, weight=1)

        # Header Row
        frm_header = ctk.CTkFrame(self.tab_library, fg_color="transparent")
        frm_header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        ctk.CTkLabel(frm_header, text="Sync Library", font=("Arial", 18, "bold")).pack(side="left")
        ctk.CTkButton(frm_header, text="Refresh Status", command=self.refresh_library_metadata, fg_color="gray").pack(side="right", padx=5)
        ctk.CTkButton(frm_header, text="Import Folder", command=self.import_existing_folder, fg_color="#3a3a3a").pack(side="right", padx=5)
        ctk.CTkButton(frm_header, text="Add from My Profile", command=self.open_playlist_selector).pack(side="right", padx=5)
        ctk.CTkButton(frm_header, text="Add URL Manually", command=self.add_manual_url).pack(side="right", padx=5)
        ctk.CTkButton(frm_header, text="New Group", command=self.add_new_group, fg_color="#3a3a3a").pack(side="right", padx=5)

        # List of Playlists
        self.library_frame = ctk.CTkScrollableFrame(self.tab_library)
        self.library_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        # Sync Button
        self.btn_sync = ctk.CTkButton(self.tab_library, text="Sync All", command=self.sync_all, fg_color="green", hover_color="darkgreen")
        self.btn_sync.grid(row=2, column=0, pady=10)

    def refresh_library_ui(self):
        """Reloads the library list with sync status, folder icons, and grouping support."""
        for widget in self.library_frame.winfo_children():
            widget.destroy()
            
        library = self.config_manager.get("library") or []
        
        # 1. Background Logic: Sync URLs from history/disk if missing (discovery always adds to root)
        history = self.history_manager.load_history() or []
        library_urls = self._get_all_library_urls(library)
        ignored_urls = set(self._normalize_spotify_url(u) for u in (self.config_manager.get("ignored_library_urls") or []))
        
        discovered_count = 0
        for entry in history:
            url = self._normalize_spotify_url(entry.get('source', ''))
            if '/playlist/' in url and url not in library_urls and url not in ignored_urls:
                library.append({"url": url, "name": entry.get('name') or "Downloaded Playlist", "type": "playlist"})
                library_urls.add(url)
                discovered_count += 1
        
        if discovered_count > 0:
            self.config_manager.set("library", library)
            self.log_message(f"Added {discovered_count} new playlists from history to library.")

        if hasattr(self, '_discovery_running') and self._discovery_running:
            pass # Already scanning
        else:
            threading.Thread(target=self._background_discovery_task, daemon=True).start()

        # 3. Render Library recursively

        if not library:
            notice_frame = ctk.CTkFrame(self.library_frame, fg_color="transparent")
            notice_frame.pack(expand=True, fill="both", pady=40)
            
            ctk.CTkLabel(notice_frame, text="Your Sync Library is Empty", font=("Arial", 18, "bold")).pack(pady=(0, 10))
            
            msg = ("This is where your tracked playlists live.\n\n"
                   "💡 Quick Start:\n"
                   "1. Go to the 'My Profile' tab\n"
                   "2. Login with your Spotify account\n"
                   "3. Select your playlists and click 'Download selected and add to the library'\n"
                   "4. They will appear here and stay in sync!")
            
            ctk.CTkLabel(notice_frame, text=msg, font=("Arial", 12), justify="center").pack(pady=10)
            
            ctk.CTkButton(notice_frame, text="Take me to My Profile", command=lambda: self.tabview.set("My Profile"), 
                         fg_color="#1DB954", hover_color="#189d44").pack(pady=20)
            return

        # 4. Render Library recursively
        self._render_library_items(self.library_frame, library)

    def _get_all_library_urls(self, items):
        """Recursively collects all normalized URLs from the library structure."""
        urls = set()
        for item in items:
            if item.get("type", "playlist") == "playlist":
                url = self._normalize_spotify_url(item.get("url", ""))
                if url: urls.add(url)
            elif item.get("type") == "group":
                urls.update(self._get_all_library_urls(item.get("items", [])))
        return urls

    def _render_library_items(self, parent, items, level=0):
        """Recursively renders library items (playlists and groups)."""
        # If this is a fresh top-level render, clear the status queue
        if level == 0:
            self._lib_status_queue = []

        self._render_library_items_recursive(parent, items, level)

        if level == 0 and self._lib_status_queue:
            threading.Thread(target=self._async_lib_status_worker, daemon=True).start()

    def _async_lib_status_worker(self):
        """Processes library sync status checks in the background."""
        self.set_active_task("Checking Library Sync Status")
        queue = list(self._lib_status_queue)
        for item, lbl, container in queue:
            try:
                raw_name = item.get("name", "Unknown")
                target_count = item.get('total_tracks') or 0
                status_text, status_color, extras = self.get_playlist_sync_status(
                    raw_name, target_count, item.get('local_path'), item.get('expected_files')
                )
                
                def _update_ui(st=status_text, sc=status_color, ex=extras, l=lbl, c=container, it=item):
                    try:
                        l.configure(text=f"[{st}]", text_color=sc)
                        if ex > 0:
                            p_path = self._get_item_path(it)
                            btn_ex = ctk.CTkLabel(c, text=f"(+{ex} extras)", text_color="orange", font=("Arial", 10, "italic"), cursor="hand2")
                            btn_ex.bind("<Button-1>", lambda e, p=p_path, n=raw_name, u=item.get('url'): self.view_extras(p, n, u))
                            btn_ex.pack(side="left", padx=2)
                    except: pass
                
                self.after(0, _update_ui)
                time.sleep(0.01) # Small breathe to avoid slamming main thread
            except Exception: continue
        self.set_active_task(None)

    def _background_discovery_task(self):
        """Discovers playlists on disk in the background."""
        self.set_active_task("Scanning Disk for Playlists")
        self._discovery_running = True
        try:
            library = self.config_manager.get("library") or []
            library_urls = self._get_all_library_urls(library)
            output_base = self.config_manager.get("output_path")
            
            if not os.path.exists(output_base) or not hasattr(self, 'all_fetched_playlists') or not self.all_fetched_playlists:
                return

            discovered_disk_count = 0
            existing_folders = [d for d in os.listdir(output_base) if os.path.isdir(os.path.join(output_base, d))]
            
            for pl in self.all_fetched_playlists:
                url = self._normalize_spotify_url(pl.get('external_urls', {}).get('spotify'))
                if not url or url in library_urls: continue
                safe_name = self.get_safe_dirname(pl['name'])
                if safe_name in existing_folders:
                    library.append({"url": url, "name": pl['name'], "total_tracks": pl['tracks']['total'], "type": "playlist"})
                    library_urls.add(url)
                    discovered_disk_count += 1
                    
                    # Log to History (Normalized)
                    self.history_manager.add_entry(url, pl['tracks']['total'], name=f"[DISCOVERED] {pl['name']}")
            
            if discovered_disk_count > 0:
                self.config_manager.set("library", library)
                self.log_message(f"Discovered {discovered_disk_count} folders on disk.")
                self.after(0, self.refresh_library_ui)
        except Exception as e:
            self.log_message(f"Discovery task failed: {e}")
        finally:
            self._discovery_running = False
            self.set_active_task(None)

    def _render_library_items_recursive(self, parent, items, level=0):
        """Internal recursive renderer."""
        for i, item in enumerate(items):
            item_type = item.get("type", "playlist")
            
            if item_type == "group":
                # Render Group Header
                group_frame = ctk.CTkFrame(parent, fg_color="#2b2b2b" if level == 0 else "transparent")
                group_frame.pack(fill="x", padx=(level * 20 + 5, 5), pady=2)
                
                exp_char = "▼" if item.get("expanded", True) else "▶"
                btn_toggle = ctk.CTkButton(group_frame, text=exp_char, width=20, height=20, fg_color="transparent",
                                          hover_color="#333333", command=lambda it=item: self._toggle_group(it))
                btn_toggle.pack(side="left", padx=5)
                
                lbl_group = ctk.CTkLabel(group_frame, text=item.get("name", "New Group"), font=("Arial", 14, "bold"), text_color="#1DB954")
                lbl_group.pack(side="left", padx=5)

                # Action Buttons for Group
                ctk.CTkButton(group_frame, text="✖", width=20, height=20, fg_color="transparent", 
                              hover_color="red", command=lambda it=item: self._remove_group(it)).pack(side="right", padx=5)
                
                ctk.CTkButton(group_frame, text="✎", width=20, height=20, fg_color="transparent", 
                              hover_color="#3a3a3a", command=lambda it=item: self._rename_group(it)).pack(side="right", padx=5)

                if item.get("expanded", True):
                    child_items = item.get("items", [])
                    if not child_items:
                        ctk.CTkLabel(parent, text="  (Empty Group)", font=("Arial", 10, "italic"), text_color="gray").pack(fill="x", padx=(level * 20 + 40, 0))
                    else:
                        self._render_library_items(parent, child_items, level + 1)
                
            else:
                # Render Playlist Card
                card = ctk.CTkFrame(parent)
                card.pack(fill="x", padx=(level * 20 + 5, 5), pady=2)
                
                # Drag handle (Simplified for now - only moves within current list)
                handle = ctk.CTkLabel(card, text="⠿", font=("Arial", 16), cursor="fleur", text_color="gray")
                handle.pack(side="left", padx=(10, 5))
                handle.bind("<Button-1>", lambda e, it_list=items, idx=i: self._on_drag_start(e, it_list, idx))
                handle.bind("<B1-Motion>", self._on_drag_motion)
                handle.bind("<ButtonRelease-1>", self._on_drag_stop)

                raw_name = item.get("name", "Unknown")
                lbl_name = ctk.CTkLabel(card, text=raw_name, font=("Arial", 11, "bold"))
                lbl_name.pack(side="left", padx=5)

                # Sync Status (Placeholder initially)
                target_count = item.get('total_tracks') or 0
                lbl_status = ctk.CTkLabel(card, text="[Checking...]", font=("Arial", 10, "bold"), text_color="gray")
                lbl_status.pack(side="left", padx=5)
                
                # Container for extras label
                extras_container = ctk.CTkFrame(card, fg_color="transparent")
                extras_container.pack(side="left")

                self._lib_status_queue.append((item, lbl_status, extras_container))

                # Right side buttons
                ctk.CTkButton(card, text="Remove", width=55, height=24, fg_color="red", hover_color="darkred",
                              command=lambda it_list=items, idx=i: self._remove_item_from_list(it_list, idx)).pack(side="right", padx=5)
                
                btn_sync_item = ctk.CTkButton(card, text="Sync", width=55, height=24, fg_color="green", hover_color="darkgreen")
                btn_sync_item.configure(command=lambda u=item.get('url'), n=item.get('name'), b=btn_sync_item, lp=item.get('local_path'): 
                                             self.sync_individual(u, n, b, lp))
                btn_sync_item.pack(side="right", padx=5)
                
                playlist_path = self._get_item_path(item)
                btn_folder = ctk.CTkButton(card, text="📂", width=25, height=24, fg_color="transparent", hover_color="#333333",
                                          command=lambda p=playlist_path: self.open_file_explorer(p))
                btn_folder.pack(side="right", padx=5)

                # Move to Group Button
                btn_move = ctk.CTkButton(card, text="➔📁", width=25, height=24, fg_color="transparent", hover_color="#333333",
                                        command=lambda it=item, it_list=items: self._show_move_to_group_dialog(it, it_list))
                btn_move.pack(side="right", padx=2)

    def _get_item_path(self, item):
        """Helper to get local path for a playlist item."""
        if item.get('local_path') and os.path.exists(item['local_path']):
            return item['local_path']
        output_base = self.config_manager.get("output_path")
        safe_name = self.get_safe_dirname(item.get('name', 'Unknown'))
        return os.path.join(output_base, safe_name)

    def add_new_group(self):
        """Adds a new empty group to the library."""
        name = simpledialog.askstring("New Group", "Enter Group Name:")
        if name:
            library = self.config_manager.get("library") or []
            library.append({"type": "group", "name": name, "expanded": True, "items": []})
            self.config_manager.set("library", library)
            self.refresh_library_ui()

    def _toggle_group(self, group_item):
        group_item["expanded"] = not group_item.get("expanded", True)
        self.config_manager.set("library", self.config_manager.get("library"))
        self.refresh_library_ui()

    def _rename_group(self, group_item):
        new_name = simpledialog.askstring("Rename Group", "New Name:", initialvalue=group_item["name"])
        if new_name:
            group_item["name"] = new_name
            self.config_manager.set("library", self.config_manager.get("library"))
            self.refresh_library_ui()

    def _remove_group(self, group_item):
        if not messagebox.askyesno("Delete Group", f"Delete '{group_item['name']}'? Playlists will be moved out."):
            return
        library = self.config_manager.get("library")
        def _rem(items):
            for i, it in enumerate(items):
                if it is group_item:
                    children = it.get("items", [])
                    del items[i]
                    for child in reversed(children): items.insert(i, child)
                    return True
                if it.get("type") == "group" and _rem(it.get("items", [])): return True
            return False
        _rem(library)
        self.config_manager.set("library", library)
        self.refresh_library_ui()

    def _remove_item_from_list(self, parent_list, index):
        item = parent_list[index]
        if messagebox.askyesno("Remove", f"Remove '{item['name']}'?"):
            url = item.get("url")
            path = self._get_item_path(item)
            if os.path.exists(path) and messagebox.askyesno("Delete Files", "Delete local files too?"):
                try: shutil.rmtree(path)
                except: pass
            if url:
                ignored = self.config_manager.get("ignored_library_urls") or []
                if url not in ignored:
                    ignored.append(url)
                    self.config_manager.set("ignored_library_urls", ignored)
            del parent_list[index]
            self.config_manager.set("library", self.config_manager.get("library"))
            self.refresh_library_ui()

    def _show_move_to_group_dialog(self, item, source_list):
        library = self.config_manager.get("library")
        groups = []
        def _col(items, p=""):
            for it in items:
                if it.get("type") == "group" and it is not item:
                    groups.append((p + it["name"], it))
                    _col(it.get("items", []), p + it["name"] + " > ")
        _col(library)
        names = ["Root"] + [g[0] for g in groups]
        
        dialog = GroupSelectDialog(self, title="Move to Group", text="Choose destination group:", options=names)
        target = dialog.get_input()
        
        if target:
            source_list.remove(item)
            if target == "Root": library.append(item)
            else:
                g = next((x[1] for x in groups if x[0] == target), None)
                if g: g.setdefault("items", []).append(item)
            self.config_manager.set("library", library)
            self.refresh_library_ui()

    def _flatten_library(self, items=None):
        """Returns a flat list of all playlist items from the hierarchical library."""
        if items is None: items = self.config_manager.get("library") or []
        flat = []
        for it in items:
            if it.get("type", "playlist") == "playlist": flat.append(it)
            elif it.get("type") == "group": flat.extend(self._flatten_library(it.get("items", [])))
        return flat

    def refresh_library_metadata(self):
        """Re-fetches track counts and names from Spotify for all library items recursively."""
        if not SPOTIPY_AVAILABLE: return
        cid = self.config_manager.get("spotify_client_id")
        secret = self.config_manager.get("spotify_client_secret")
        if not cid or not secret: return

        def work():
            self.set_active_task("Refreshing Library Metadata")
            self.log_message("Refreshing Library metadata recursively...")
            library = self.config_manager.get("library") or []
            auth_manager = SpotifyClientCredentials(client_id=cid, client_secret=secret)
            sp = spotipy.Spotify(auth_manager=auth_manager)
            
            def _refresh_recursive(items):
                count = 0
                for item in items:
                    if item.get("type", "playlist") == "playlist":
                        url = item.get('url', '')
                        try:
                            # Throttling to prevent 429 Rate Limit
                            time.sleep(0.5)
                            
                            if 'playlist' in url:
                                data = sp.playlist(url, fields="name,tracks.total")
                                item['name'] = data.get('name', item['name'])
                                item['total_tracks'] = data['tracks']['total']
                            elif 'album' in url:
                                data = sp.album(url)
                                item['name'] = data.get('name', item['name'])
                                item['total_tracks'] = data['tracks']['total']
                            
                            # Pass shared sp client to avoid redundant auth
                            item['expected_files'] = self._get_expected_filenames(url, sp=sp)
                            count += 1
                        except Exception as e:
                            self.log_message(f"Error refreshing metadata for {url}: {e}")
                    elif item.get("type") == "group":
                        count += _refresh_recursive(item.get("items", []))
                return count

            updated = _refresh_recursive(library)
            self.config_manager.set("library", library)
            self.set_active_task(None)
            self.after(0, self.refresh_library_ui) 
            self.after(0, lambda: messagebox.showinfo("Refresh Complete", f"Updated {updated} items."))

        threading.Thread(target=work, daemon=True).start()

    def _get_expected_filenames(self, spotify_url, sp=None):
        """Helper to fetch tracklist and return list of sanitized {artist} - {title} basenames."""
        if not SPOTIPY_AVAILABLE or not spotify_url:
            return []
            
        try:
            if not sp:
                cid = self.config_manager.get("spotify_client_id")
                secret = self.config_manager.get("spotify_client_secret")
                auth_manager = SpotifyClientCredentials(client_id=cid, client_secret=secret)
                sp = spotipy.Spotify(auth_manager=auth_manager)
            
            tracks = []
            if 'playlist' in spotify_url:
                results = sp.playlist_items(spotify_url, fields="items(track(name,artists(name))),next")
                tracks.extend(results['items'])
                while results['next']:
                    results = sp.next(results)
                    tracks.extend(results['items'])
            elif 'album' in spotify_url:
                results = sp.album_tracks(spotify_url)
                tracks = [{"track": t} for t in results['items']]
                while results['next']:
                    results = sp.next(results)
                    tracks.extend([{"track": t} for t in results['items']])

            expected = []
            for item in tracks:
                t = item.get('track')
                if not t: continue
                artist = t['artists'][0]['name']
                title = t['name']
                raw_base = f"{artist} - {title}"
                for char in '<>:"/\\|?*':
                    raw_base = raw_base.replace(char, '_')
                expected.append(raw_base.lower())
            return expected
        except Exception as e:
            self.log_message(f"Error fetching expected filenames: {e}")
            return []

    def _on_drag_start(self, event, item_list, index):
        """Initializes drag-and-drop reordering within a specific list (root or group)."""
        self.drag_item_list = item_list
        self.drag_item_index = index
        self.drag_start_y = event.y_root
        self.bind("<B1-Motion>", self._on_drag_motion)

    def _on_drag_motion(self, event):
        """Handles mouse movement during drag to trigger swaps."""
        if self.drag_item_index == -1 or not hasattr(self, 'drag_item_list'): return
        
        delta_y = event.y_root - self.drag_start_y
        threshold = 55 
        
        if abs(delta_y) > threshold:
            direction = 1 if delta_y > 0 else -1
            new_index = self.drag_item_index + direction
            
            if 0 <= new_index < len(self.drag_item_list):
                # Swap
                self.drag_item_list[self.drag_item_index], self.drag_item_list[new_index] = \
                    self.drag_item_list[new_index], self.drag_item_list[self.drag_item_index]
                
                # Update state
                self.drag_item_index = new_index
                self.drag_start_y = event.y_root
                
                # Save and Refresh
                self.config_manager.set("library", self.config_manager.get("library"))
                self.refresh_library_ui()

    def _on_drag_stop(self, event):
        """Cleans up after drag-and-drop."""
        self.drag_item_index = -1
        if hasattr(self, 'drag_item_list'): del self.drag_item_list
        self.unbind("<B1-Motion>")

    def add_manual_url(self):
        url = simpledialog.askstring("Add URL", "Enter Spotify Playlist URL:")
        if url:
            name = simpledialog.askstring("Name", "Enter a name for this playlist:") or "Untitled Playlist"
            library = self.config_manager.get("library")
            library.append({"url": self._normalize_spotify_url(url), "name": name})
            self.config_manager.set("library", library)
            
            # Add to History
            self.history_manager.add_entry(url, 0, name=f"[MANUAL] {name}")
            
            self.refresh_library_ui()

    def view_extras(self, folder_path, playlist_name, spotify_url=None):
        """Shows only files in the folder that are NOT part of the Spotify playlist."""
        if not os.path.exists(folder_path):
            messagebox.showwarning("Not Found", "Folder no longer exists.")
            return

        # Try to find the library item to use cached expected_files
        cached_expected = None
        flat_library = self._flatten_library()
        for item in flat_library:
            if item.get('url') == spotify_url:
                cached_expected = item.get('expected_files')
                break

        def work():
            self.log_message(f"Analyzing extras for: {playlist_name}...")
            
            local_files = []
            try:
                local_files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", f"Could not list files: {e}"))
                return

            expected_basenames = set()
            if cached_expected:
                expected_basenames = set(f.lower() for f in cached_expected)
            elif spotify_url and SPOTIPY_AVAILABLE:
                # Fallback to fetching if not cached
                expected_basenames = set(self._get_expected_filenames(spotify_url))

            # Filter logic
            extras = []
            music_extensions = ('.mp3', '.flac', '.m4a', '.opus', '.ogg', '.wav')
            
            for f in local_files:
                # 1. Skip system files
                if f.startswith('.') or f.lower() in ('desktop.ini', 'thumbs.db', 'playlist.json'):
                    continue
                
                # 2. Skip spotdl specific metadata
                if f.endswith('.spotdl-cache'):
                    continue
                
                # 3. If it's music, check if it's in expected list
                if f.lower().endswith(music_extensions):
                    # Strip extension and check
                    base = os.path.splitext(f)[0].lower()
                    if base in expected_basenames:
                        continue
                
                extras.append(f)

            # Show results in main thread
            self.after(0, lambda: self._show_extras_window(playlist_name, sorted(extras)))

        threading.Thread(target=work, daemon=True).start()

    def _show_extras_window(self, playlist_name, extras):
        win = ctk.CTkToplevel(self)
        win.title(f"Extra Files: {playlist_name}")
        win.geometry("500x450")
        win.attributes("-topmost", True)
        
        ctk.CTkLabel(win, text=f"Unrecognized Files in: {playlist_name}", font=("Arial", 16, "bold")).pack(pady=10)
        
        if not extras:
            ctk.CTkLabel(win, text="No extra files found! (Only official tracks/metadata present)").pack(pady=40)
        else:
            ctk.CTkLabel(win, text=f"Found {len(extras)} unrecognized files:", font=("Arial", 12)).pack()
            
            txt = ctk.CTkTextbox(win, width=460, height=300)
            txt.pack(pady=10, padx=10)
            
            for f in extras:
                txt.insert("end", f + "\n")
            txt.configure(state="disabled")
        
        ctk.CTkButton(win, text="Close", command=win.destroy).pack(pady=10)

    def import_existing_folder(self):
        """Allows importing an existing folder and linking it to a Spotify URL."""
        if not SPOTIPY_AVAILABLE:
            messagebox.showwarning("Spotify API", "Spotify API is not available.")
            return

        folder = filedialog.askdirectory(title="Select Existing Playlist Folder", initialdir=self.config_manager.get("output_path"))
        if not folder: return

        url = simpledialog.askstring("Spotify URL", "Paste the Spotify Playlist URL for this folder:")
        if not url: return
        url = self._normalize_spotify_url(url)

        cid = self.config_manager.get("spotify_client_id")
        secret = self.config_manager.get("spotify_client_secret")
        
        def do_import():
            self.set_active_task("Importing Folder")
            self.log_message(f"Fetching metadata for {url}...")
            try:
                auth_manager = SpotifyClientCredentials(client_id=cid, client_secret=secret)
                sp = spotipy.Spotify(auth_manager=auth_manager)
                
                if 'playlist' in url:
                    data = sp.playlist(url, fields="name,tracks.total")
                elif 'album' in url:
                    data = sp.album(url)
                else:
                    self.after(0, lambda: messagebox.showerror("Invalid URL", "Please provide a valid Spotify Playlist or Album URL."))
                    return

                pl_name = data.get('name', 'Unknown')
                track_count = data['tracks']['total']
                
                # Ask Choice in Main Thread
                result = []
                def get_choice():
                    choice = messagebox.askyesnocancel("Merge Option", 
                        f"Folder: {os.path.basename(folder)}\nPlaylist: {pl_name}\n\n"
                        "Would you like to MOVE this folder into your default Output Path for better management?\n\n"
                        "Yes = Move to Output Path\nNo = Keep in existing location\nCancel = Abort Import"
                    )
                    result.append(choice)
                
                self.after(0, get_choice)
                while not result: time.sleep(0.1)
                choice = result[0]
                
                if choice is None: return # Cancelled
                
                local_path = folder
                if choice is True: # Move
                    output_base = self.config_manager.get("output_path")
                    safe_name = self.get_safe_dirname(pl_name)
                    dest = os.path.join(output_base, safe_name)
                    
                    if os.path.exists(dest):
                        # Ask Confirmation in Main Thread
                        res2 = []
                        self.after(0, lambda: res2.append(messagebox.askyesno("Confirm Merge", f"Target folder '{safe_name}' already exists in Output Path. Merge contents?")))
                        while not res2: time.sleep(0.1)
                        if not res2[0]: return

                        for f in os.listdir(folder):
                            shutil.move(os.path.join(folder, f), os.path.join(dest, f))
                    else:
                        shutil.move(folder, dest)
                    local_path = None # It will now follow default output_path logic
                    self.log_message(f"Moved external folder to: {dest}")
                else:
                    self.log_message(f"Linked external folder at: {local_path}")

                # Add to Library
                library = self.config_manager.get("library") or []
                new_item = {
                    "url": url,
                    "name": pl_name,
                    "total_tracks": track_count
                }
                if local_path:
                    new_item["local_path"] = local_path
                    
                library.append(new_item)
                self.config_manager.set("library", library)
                
                # Add to History
                self.history_manager.add_entry(url, track_count, name=f"[IMPORTED] {pl_name}")
                
                self.after(0, self.refresh_library_ui)
                self.set_active_task(None)
                self.after(0, lambda: messagebox.showinfo("Import Success", f"Successfully linked '{pl_name}' to the library."))

            except Exception as e:
                self.log_message(f"Import failed: {e}")
                self.after(0, lambda e=e: messagebox.showerror("Import Error", f"Failed to import folder: {e}"))

        threading.Thread(target=do_import, daemon=True).start()

    def open_playlist_selector(self):
        if not SPOTIPY_AVAILABLE:
            messagebox.showwarning("Missing Dependency", "Spotipy is not installed or configured.")
            return

        dialog = PlaylistSelectionDialog(self, 
                                         self.config_manager.get("spotify_client_id"),
                                         self.config_manager.get("spotify_client_secret"),
                                         self.config_manager.get("spotify_user_id"))
        self.wait_window(dialog)
        
        if dialog.selected_playlists:
            library = self.config_manager.get("library")
            library.extend(dialog.selected_playlists)
            self.config_manager.set("library", library)
            self.refresh_library_ui()

    def sync_all(self):
        library = self.config_manager.get("library")
        if not library:
            messagebox.showinfo("Info", "Nothing to sync.")
            return
        
        self.btn_sync.configure(state="disabled", text="Syncing...")
        threading.Thread(target=self.run_batch_sync, args=(library,), daemon=True).start()

    def sync_individual(self, url, name, button=None, local_path=None):
        """Syncs a single playlist/album from the library."""
        if not url: return
        
        if button:
            button.configure(state="disabled", text="Syncing...", fg_color="gray")
            
        self.log_message(f"Starting individual sync for: {name} (SpotDL will skip existing files)")
        threading.Thread(target=self.run_individual_sync, args=(url, name, button, local_path), daemon=True).start()

    def run_individual_sync(self, url, name, button=None, local_path=None):
        self.set_active_task(f"Syncing {name}")
        self.log_message(f"Checking for updates: {name}")
        
        # Determine target directory
        if local_path and os.path.exists(local_path):
            target_cwd = local_path
        else:
            base_path = self.config_manager.get("output_path")
            safe_name = self.get_safe_dirname(name)
            target_cwd = os.path.join(base_path, safe_name)
        
        if not os.path.exists(target_cwd):
            try: os.makedirs(target_cwd, exist_ok=True)
            except: pass

        success, tracks = self.download_synchronously(url, cwd=target_cwd)
        
        # Final UI update
        self.set_active_task(None)
        self.after(0, self.refresh_library_ui)
        self.set_active_task(None)
        
        if success:
            count = len(tracks)
            self.log_message(f"Successfully synced {name} ({count} tracks).")
            
            # Populate Download Feed
            for track in tracks:
                self.log_download(track)
            
            # Format track list for popup
            if count > 0:
                display_tracks = tracks[:10]
                tracks_str = "\n- ".join(display_tracks)
                if count > 10:
                    tracks_str += f"\n... and {count - 10} more"
                msg = f"Finished syncing '{name}'.\n\nNewly Synced Songs:\n- {tracks_str}"
            else:
                msg = f"Finished syncing '{name}'.\n(All tracks were already up to date)"
                
            self.after(0, lambda: messagebox.showinfo("Sync Complete", msg))
        else:
            self.log_message(f"Failed to sync {name}. Check logs.")
            if button:
                self.after(0, lambda: button.configure(state="normal", text="Sync", fg_color="green"))

    def run_batch_sync(self, library):
        self.set_active_task("Batch Syncing")
        self.log_message("Starting Batch Sync...")
        # Flatten the library for batch sync processing
        flat_library = self._flatten_library(library)
        total = len(flat_library)
        base_path = self.config_manager.get("output_path")
        all_new_tracks = []
        
        for i, item in enumerate(flat_library):
            name = item.get('name', 'Unknown')
            self.set_active_task(f"Batch Sync [{i+1}/{total}]: {name}")
            self.log_message(f"[{i+1}/{total}] Syncing: {name}")
            
            # Subfolder Logic
            if item.get('local_path') and os.path.exists(item['local_path']):
                target_cwd = item['local_path']
            else:
                safe_name = self.get_safe_dirname(name)
                target_cwd = os.path.join(base_path, safe_name)
                
            if not os.path.exists(target_cwd):
                os.makedirs(target_cwd, exist_ok=True)
                
            success, tracks = self.download_synchronously(item['url'], cwd=target_cwd)
            if success:
                all_new_tracks.extend(tracks)
                for track in tracks:
                    self.log_download(track)
        
        self.after(0, lambda: self.btn_sync.configure(state="normal", text="Sync All"))
        self.after(0, self.refresh_library_ui)
        
        count = len(all_new_tracks)
        if count > 0:
            display_tracks = all_new_tracks[:15] # Show a bit more for batch
            tracks_str = "\n- ".join(display_tracks)
            if count > 15:
                tracks_str += f"\n... and {count - 15} more"
            msg = f"Batch sync complete!\n\nTotal New Songs: {count}\n- {tracks_str}"
        else:
            msg = "Batch sync complete! No new tracks were added."
            
        self.set_active_task(None)
        self.after(0, lambda: messagebox.showinfo("Batch Sync Complete", msg))



    def download_synchronously(self, url, cwd=None, status_callback=None, max_retries=3):
        """Helper to run download and wait for it (used in batch)."""
        cookie_file = self.config_manager.get("cookie_file")
        
        # Ensure paths are absolute because we change cwd
        if cookie_file:
            cookie_file = os.path.abspath(cookie_file)
            if not os.path.exists(cookie_file):
                self.log_message(f"WARNING: Cookie file not found at: {cookie_file}")
        
        output_path = os.path.abspath(self.config_manager.get("output_path"))

        # Use provided cwd or default to output_path
        working_dir = cwd if cwd else output_path
        
        self.log_message(f"Download CWD: {working_dir}")
        if not os.path.exists(working_dir):
             self.log_message(f"ERROR: Working directory does not exist! {working_dir}")
             return False, 0

        # Use unified command helper (normalize URL here too)
        normalized_url = self._normalize_spotify_url(url)
        cmd = self._get_spotdl_command(normalized_url, fmt="flac") # Sync defaults to high quality flac
        
        for attempt in range(1, max_retries + 1):
            try:
                self.log_message(f"--- Attempt {attempt}/{max_retries} ---")
                self.log_message(f"EXECUTING COMMAND: {' '.join(cmd)}")
                
                process = subprocess.Popen(
                    cmd,
                    cwd=working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
                
                downloaded_tracks = []
                process_output = [] # Capture full output for debugging
                
                playlist_name = None
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.log_message(line)
                        process_output.append(line)
                        
                        # Try to detect playlist/track name from output
                        if 'Processing' in line and not playlist_name:
                            if 'playlist' in line.lower() or 'album' in line.lower():
                                try:
                                    playlist_name = line.split('Processing ')[1].split('...')[0].strip()
                                except: pass
                        
                        if 'Downloaded "' in line:
                             try:
                                track_name = line.split('Downloaded "')[1].split('"')[0]
                                downloaded_tracks.append(track_name)
                                if status_callback:
                                    self.after(0, lambda t=track_name: status_callback(t))
                             except IndexError:
                                pass
                        elif 'Downloading' in line and status_callback:
                             # Try to catch "Downloading URL" or similar generic start
                             self.after(0, lambda: status_callback("Initializing..."))
    
                process.wait()
                if downloaded_tracks:
                     # Detect name from library or source if possible
                     name = None
                     library = self.config_manager.get("library") or []
                     for item in library:
                         if item['url'] == url:
                             name = item.get('name')
                             break
                     
                     self.history_manager.add_entry(url, downloaded_tracks, name=name)
                     self.after(0, self.refresh_history_ui)
                     return True, downloaded_tracks
                
                # Check return code
                if process.returncode == 0:
                    self.log_message("Download process finished (No new tracks detected or parsing failed).") 
                    return True, []
                else:
                    self.log_message(f"Attempt {attempt} failed with code {process.returncode}")
                    if attempt < max_retries:
                        self.log_message("Retrying in 3 seconds...")
                        time.sleep(3)
                        continue
                     
            except Exception as e:
                self.log_message(f"Error syncing {url}: {e}")
                if attempt < max_retries:
                    self.log_message("Retrying in 3 seconds...")
                    time.sleep(3)
                    continue

        # If we reach here, all retries failed
        self.log_message("All retry attempts failed.")
        
        # Show debug info to user
        tail = "\n".join(process_output[-10:]) if 'process_output' in locals() and process_output else "No output captured."
        self.after(0, lambda: messagebox.showwarning("Download Failed", f"Failed after {max_retries} attempts.\n\nLast Log Lines:\n{tail}"))

        return False, []


    def setup_history_tab(self):
        """Builds the History tab."""
        self.tab_history.grid_columnconfigure(0, weight=1)
        self.tab_history.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(self.tab_history, text="Download History", font=("Arial", 18, "bold")).grid(row=0, column=0, pady=10)
        
        # Scrollable Frame for history items
        self.history_frame = ctk.CTkScrollableFrame(self.tab_history)
        self.history_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkButton(self.tab_history, text="Refresh", command=self.refresh_history_ui).grid(row=2, column=0, pady=10)
        
        self.refresh_history_ui()

    def resolve_name_from_url(self, url):
        """Attempts to find a human-readable name for a Spotify URL."""
        if not url or not url.startswith('http'):
            return None
            
        # 1. Check current library
        library = self.config_manager.get("library") or []
        for item in library:
            if item.get('url') == url:
                return item.get('name')

        # 2. Extract from URL as fallback if API fails
        parts = url.split('/')
        if 'playlist' in url:
            id_part = parts[-1].split('?')[0]
            fallback = f"Playlist: {id_part[:8]}..."
        elif 'track' in url:
            id_part = parts[-1].split('?')[0]
            fallback = f"Track: {id_part[:8]}..."
        else:
            fallback = url[:30] + "..."

        # 3. Use Spotify API if available
        if SPOTIPY_AVAILABLE:
            try:
                cid = self.config_manager.get("spotify_client_id")
                secret = self.config_manager.get("spotify_client_secret")
                if cid and secret:
                    import spotipy
                    from spotipy.oauth2 import SpotifyClientCredentials
                    auth_manager = SpotifyClientCredentials(client_id=cid, client_secret=secret)
                    sp = spotipy.Spotify(auth_manager=auth_manager)
                    
                    if 'playlist' in url:
                        data = sp.playlist(url, fields="name")
                        return data.get('name')
                    elif 'track' in url:
                        data = sp.track(url)
                        return f"{data['artists'][0]['name']} - {data['name']}"
                    elif 'album' in url:
                        data = sp.album(url)
                        return data.get('name')
            except Exception as e:
                self.log_message(f"API Name Lookup failed for {url}: {e}")
        
        return fallback

    def refresh_history_ui(self):
        """Reloads history items into the scrollable frame with expandable track lists."""
        for widget in self.history_frame.winfo_children():
            widget.destroy()
            
        history = self.history_manager.load_history()
        if not history:
            ctk.CTkLabel(self.history_frame, text="No history found.").pack(pady=20)
            return

        # Sort history by newest first (create a copy)
        history_items = history[::-1]
        history_updated = False

        for i, entry in enumerate(history_items):
            # ... UI creation ...
            card = ctk.CTkFrame(self.history_frame)
            card.pack(fill="x", padx=5, pady=5)
            
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=10, pady=5)
            
            ts = datetime.fromisoformat(entry['timestamp']).strftime("%m-%d %H:%M")
            
            # Resolve name
            entry_name = entry.get('name')
            source_url = entry.get('source', 'Unknown')
            
            if not entry_name or entry_name == "Downloaded Playlist":
                resolved = self.resolve_name_from_url(source_url)
                if resolved and resolved != source_url:
                    entry_name = resolved
                    # Persist it back to history so we don't API call every time
                    # We need to find the correct index in the original 'history' list
                    orig_idx = len(history) - 1 - i
                    history[orig_idx]['name'] = resolved
                    history_updated = True
            
            display_name = entry_name if entry_name else source_url
            if len(display_name) > 60:
                display_name = display_name[:57] + "..."
                
            lbl_info = ctk.CTkLabel(top_row, text=f"{ts} - {display_name}", 
                                    font=("Arial", 12, "bold"), anchor="w")
            lbl_info.pack(side="left", fill="x", expand=True)

            count = entry.get('count', 0)
            lbl_count = ctk.CTkLabel(top_row, text=f"{count} tracks", text_color="gray")
            lbl_count.pack(side="right", padx=10)

            # Details Frame (Initially Hidden)
            details_frame = ctk.CTkFrame(card, fg_color="transparent")
            
            def toggle_details(frame=details_frame, btn=None):
                if frame.winfo_ismapped():
                    frame.pack_forget()
                    if btn: btn.configure(text="▼ Details")
                else:
                    frame.pack(fill="x", padx=10, pady=(0, 10))
                    if btn: btn.configure(text="▲ Hide")

            btn_toggle = ctk.CTkButton(top_row, text="▼ Details", width=70, height=24,
                                       command=lambda f=details_frame: toggle_details(f))
            btn_toggle.configure(command=lambda f=details_frame, b=btn_toggle: toggle_details(f, b))
            btn_toggle.pack(side="right")

            # Track List in Details
            if entry.get('tracks'):
                tracks_text = "\n".join(entry['tracks'])
                txt_tracks = ctk.CTkTextbox(details_frame, height=100, font=("Courier", 11))
                txt_tracks.insert("1.0", tracks_text)
                txt_tracks.configure(state="disabled") # Read-only
                txt_tracks.pack(fill="x", pady=5)
            else:
                ctk.CTkLabel(details_frame, text="No track details recorded.", text_color="gray").pack()
            
        if history_updated:
            self.history_manager.save_history()

    def setup_settings_tab(self):
        """Builds the Settings tab."""
        self.tab_settings.grid_columnconfigure(1, weight=1)
        
        # Cookie File
        ctk.CTkLabel(self.tab_settings, text="Cookie File:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.entry_cookie = ctk.CTkEntry(self.tab_settings)
        self.entry_cookie.insert(0, self.config_manager.get("cookie_file"))
        self.entry_cookie.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(self.tab_settings, text="Browse", width=80, command=self.browse_cookie).grid(row=0, column=2, padx=10)

        # Output Path
        ctk.CTkLabel(self.tab_settings, text="Output Path:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.entry_output = ctk.CTkEntry(self.tab_settings)
        self.entry_output.insert(0, self.config_manager.get("output_path"))
        self.entry_output.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(self.tab_settings, text="Browse", width=80, command=self.browse_output).grid(row=1, column=2, padx=10)
        
        # API Keys
        ctk.CTkLabel(self.tab_settings, text="Spotify Client ID:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.entry_client_id = ctk.CTkEntry(self.tab_settings)
        self.entry_client_id.insert(0, self.config_manager.get("spotify_client_id"))
        self.entry_client_id.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(self.tab_settings, text="Spotify Client Secret:").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.entry_secret = ctk.CTkEntry(self.tab_settings, show="*")
        self.entry_secret.insert(0, self.config_manager.get("spotify_client_secret"))
        self.entry_secret.grid(row=3, column=1, padx=10, pady=10, sticky="ew")

        # Spotify User
        ctk.CTkLabel(self.tab_settings, text="Default User ID:").grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.entry_user_id = ctk.CTkEntry(self.tab_settings, placeholder_text="For profile display & default fetch")
        self.entry_user_id.insert(0, self.config_manager.get("spotify_user_id"))
        self.entry_user_id.grid(row=4, column=1, padx=10, pady=10, sticky="ew")

        # Log Level
        ctk.CTkLabel(self.tab_settings, text="Log Level:").grid(row=5, column=0, padx=10, pady=10, sticky="w")
        self.combo_log = ctk.CTkComboBox(self.tab_settings, values=["DEBUG", "INFO", "WARNING", "ERROR"])
        self.combo_log.set(self.config_manager.get("log_level"))
        self.combo_log.grid(row=5, column=1, padx=10, pady=10, sticky="w")
        
        # Save Button
        ctk.CTkButton(self.tab_settings, text="Save Settings", command=self.save_settings).grid(row=10, column=0, columnspan=3, pady=(20, 10))
        
        # Restore Defaults
        ctk.CTkButton(self.tab_settings, text="Restore Defaults", command=self.confirm_restore_defaults, fg_color="red", hover_color="darkred").grid(row=11, column=0, columnspan=3, pady=10)


    def setup_about_tab(self):
        """Builds the About/FAQ tab with detailed guidance."""
        self.tab_about.grid_columnconfigure(0, weight=1)
        self.tab_about.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self.tab_about)
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        scroll.grid_columnconfigure(0, weight=1)

        def add_section(title, content):
            ctk.CTkLabel(scroll, text=title, font=("Arial", 18, "bold"), text_color="#1DB954", anchor="w").pack(fill="x", pady=(20, 5), padx=10)
            ctk.CTkLabel(scroll, text=content, font=("Arial", 12), justify="left", anchor="w").pack(fill="x", pady=(0, 10), padx=20)

        # 1. Introduction
        intro = ("SpotDL GUI is a powerful tool designed to help you manage and download your Spotify playlists or albums "
                 "for offline use. It provides a clean, organized interface for your music library with advanced sync features.")
        add_section("1. Introduction", intro)

        # 2. Getting Started
        started = ("💡 Quick Start:\n"
                   "- Go to 'Settings' and set your 'Output Path'.\n"
                   "- Go to 'My Profile' and click 'Login with Spotify'.\n"
                   "- Once logged in, fetch your playlists and add them to the Sync Library.\n\n"
                   "Prerequisites:\n"
                   "- FFmpeg must be installed on your system.")
        add_section("2. Getting Started", started)

        # 3. Security & Privacy
        security = ("⚖️ Why do I need API Keys?\n"
                    "- Direct Privacy: By using your own Client ID, the app talks directly to Spotify. No third-party servers ever touch your data.\n"
                    "- Secure Login: Your actual login happens via official Spotify OAuth in your browser. The app only stores a local, encrypted-style token.\n"
                    "- Full Control: You are the developer of your own 'app' instance, ensuring total transparency.")
        add_section("3. Security & Privacy", security)

        # 4. Key Features
        features = ("🌟 Playlist Grouping:\n"
                    "Create folders in the Library tab to categorize your music. Click '➔📁' to move an item into a group.\n\n"
                    "⠿ Reordering:\n"
                    "Hold and drag the '⠿' handle to sort your library. The order is remembered automatically.\n\n"
                    "🔄 Smart Sync:\n"
                    "Click 'Sync All' to only download songs that are NEW on Spotify. It won't re-download existing tracks.")
        add_section("4. Key Features", features)

        # 5. Tab Overviews
        tabs = ("• Library: Track and sync your core collection.\n"
                "• Downloader: Quickly grab any single Spotify URL.\n"
                "• My Profile: Browse and manage your own Spotify data.\n"
                "• History: Review past session logs and added tracks.\n"
                "• Settings: Customize paths and API credentials.\n"
                "• Logs: View technical output and real-time download status.")
        add_section("5. Tab Overviews", tabs)

        # 6. FAQ
        faq = ("Q: Why aren't names refreshing?\n"
               "A: Check your Spotify API keys in Settings. Then hit 'Refresh Status'.\n\n"
               "Q: Where is my music saved?\n"
               "A: In the 'Output Path' folder set in Settings.\n\n"
               "Q: Sync is failing or stuck?\n"
               "A: Check the Logs tab. Often a spotdl update (pip install -U spotdl) fixes common issues.\n\n"
               "Q: How to move items out of groups?\n"
               "A: Click '➔📁' and select 'Root'.")
        add_section("6. FAQ / Troubleshooting", faq)

        ctk.CTkLabel(scroll, text=f"Version {APP_VERSION} | Created for music enthusiasts 🚀🎶", font=("Arial", 10, "italic"), text_color="gray").pack(pady=30)


    def setup_logs_tab(self):
        """Builds the Logs tab with an expandable Download Feed."""
        self.tab_logs.grid_columnconfigure(0, weight=1)
        self.tab_logs.grid_rowconfigure(1, weight=1)  # Debug logs get the most space
        
        # Header for Download Feed
        self.feed_header = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        self.feed_header.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        
        ctk.CTkLabel(self.feed_header, text="✨ New Downloads Feed", font=("Arial", 14, "bold")).pack(side="left")
        
        self.btn_toggle_feed = ctk.CTkButton(self.feed_header, text="Collapse", width=80, height=24,
                                            command=self.toggle_download_feed)
        self.btn_toggle_feed.pack(side="right")

        # Scrollable Frame for the Feed
        self.download_feed_frame = ctk.CTkScrollableFrame(self.tab_logs, height=150, label_text="Session History")
        self.download_feed_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        
        # Divider/Label for Technical Logs
        ctk.CTkLabel(self.tab_logs, text="Technical Debug Logs", font=("Arial", 10, "italic"), text_color="gray").grid(row=2, column=0, padx=10, pady=(5, 0), sticky="w")

        # Technical Debug Logs
        self.txt_logs = ctk.CTkTextbox(self.tab_logs)
        self.txt_logs.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.tab_logs.grid_rowconfigure(3, weight=2) # Debug logs are larger

    def toggle_download_feed(self):
        """Toggles the visibility of the download feed."""
        if self.feed_expanded:
            self.download_feed_frame.grid_forget()
            self.btn_toggle_feed.configure(text="Expand")
            self.feed_expanded = False
        else:
            self.download_feed_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
            self.btn_toggle_feed.configure(text="Collapse")
            self.feed_expanded = True

    def log_download(self, track_name):
        """Adds a track to the session download feed."""
        self.session_new_downloads.append(track_name)
        
        def _update_feed():
            # Create a small label for each track in the feed
            ts = datetime.now().strftime('%H:%M:%S')
            lbl = ctk.CTkLabel(self.download_feed_frame, text=f"[{ts}] {track_name}", 
                               font=("Arial", 11), anchor="w", justify="left")
            lbl.pack(fill="x", padx=5, pady=2)
            # Auto-scroll not easily supported in CTkScrollableFrame via code, but we pack at bottom
        
        self.after(0, _update_feed)

    def browse_cookie(self):
        filename = filedialog.askopenfilename(title="Select Cookie File")
        if filename:
            self.entry_cookie.delete(0, "end")
            self.entry_cookie.insert(0, filename)
            self.config_manager.set("cookie_file", filename) # Auto-save


    def browse_output(self):
        directory = filedialog.askdirectory(title="Select Output Folder")
        if directory:
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, directory)
            self.config_manager.set("output_path", directory) # Auto-save


    def save_settings(self):
        """Persists settings to disk."""
        self.config_manager.set("cookie_file", self.entry_cookie.get())
        self.config_manager.set("output_path", self.entry_output.get())
        self.config_manager.set("spotify_client_id", self.entry_client_id.get())
        self.config_manager.set("spotify_client_secret", self.entry_secret.get())
        self.config_manager.set("spotify_user_id", self.entry_user_id.get())
        self.config_manager.set("log_level", self.combo_log.get())
        messagebox.showinfo("Settings", "Settings saved successfully!")
        self.setup_logging() # Re-configure logging
        self.update_profile_display() # Refresh profile

    def confirm_restore_defaults(self):
        if messagebox.askyesno("Restore Defaults", "Are you sure you want to reset all settings?\nThis will clear API keys, paths, and logout of Spotify."):
            self.config_manager.reset_defaults()
            
            # Remove spotipy cache files (tokens)
            try:
                folder = os.getcwd()
                for f in os.listdir(folder):
                    if f.startswith(".cache"):
                         os.remove(os.path.join(folder, f))
            except Exception as e:
                print(f"Error clearing cache: {e}")
            
            # Refresh UI
            self.entry_cookie.delete(0, "end")
            self.entry_cookie.insert(0, self.config_manager.get("cookie_file"))
            
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, self.config_manager.get("output_path"))
            
            self.entry_client_id.delete(0, "end")
            self.entry_secret.delete(0, "end")
            self.entry_user_id.delete(0, "end")
            
            self.combo_log.set("INFO")
            
            self.setup_logging()
            self.update_profile_display()
            self.refresh_library_ui()
            
            messagebox.showinfo("Reset", "Application settings restored to defaults.")


    def log_message(self, message: str):
        """Appends message to the Log tab in a thread-safe way and writes to file."""
        # File logging
        logging.info(message)
        
        # GUI logging
        def _log():
             self.txt_logs.insert("end", f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
             self.txt_logs.see("end")
        self.after(0, _log)



    def start_download(self):
        """Initiates the download process."""
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a URL first.")
            return

        fmt = self.opt_format.get()
        self.btn_download.configure(state="disabled", text="Downloading...")
        self.lbl_status.configure(text="Starting download process...", text_color="orange")
        self.log_message(f"Starting download for: {url}")
        
        # Run in background thread
        threading.Thread(target=self.run_spotdl, args=(url, fmt), daemon=True).start()

    def _get_spotdl_command(self, url, fmt="mp3"):
        """Constructs the spotDL command with all necessary flags and credentials."""
        cookie_file = self.config_manager.get("cookie_file")
        cid = self.config_manager.get("spotify_client_id")
        secret = self.config_manager.get("spotify_client_secret")
        
        # Absolute path for cookie file
        if cookie_file:
            cookie_file = os.path.abspath(cookie_file)

        cmd = [
            "spotdl",
            "--cookie-file", cookie_file,
            "--bitrate", "disable",
            "--format", fmt,
            "--output", "{artists} - {title}.{output-ext}"
        ]

        if cid and secret:
            cmd.extend(["--client-id", cid, "--client-secret", secret])

        cmd.extend(["download", self._normalize_spotify_url(url)])
        return cmd

    def run_spotdl(self, url: str, fmt: str = "mp3"):
        """Executes the spotDL command using subprocess."""
        output_path = self.config_manager.get("output_path")
        cmd = self._get_spotdl_command(url, fmt)
        
        try:
            self.log_message(f"EXECUTING COMMAND: {' '.join(cmd)}")
            
            # Start process
            process = subprocess.Popen(
                cmd,
                cwd=output_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            downloaded_tracks = []
            
            # Read output in real-time
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.log_message(line)
                    # Simple parsing logic - can be improved
                    if 'Downloaded "' in line:
                        # Extract track name if possible
                        try:
                            # spotDL usually outputs: Downloaded "Artist - Title"
                            track_name = line.split('Downloaded "')[1].split('"')[0]
                            downloaded_tracks.append(track_name)
                        except IndexError:
                            pass

            process.wait()
            
            if process.returncode == 0:
                if downloaded_tracks:
                    # Detect name from what we parsed in output
                    name = playlist_name if playlist_name else None
                    self.history_manager.add_entry(url, downloaded_tracks, name=name)
                    self.after(0, self.refresh_history_ui)
                    self.after(0, lambda: self.on_download_success(url, downloaded_tracks))
                else:
                    self.after(0, lambda: self.on_download_error("No tracks were downloaded."))
            else:
                self.after(0, lambda: self.on_download_error("Process exited with error code."))

        except FileNotFoundError:
             self.after(0, lambda: self.on_download_error("spotDL command not found. Please ensure it is installed and in PATH."))
        except Exception as e:
             self.after(0, lambda: self.on_download_error(str(e)))

    def on_download_success(self, url, tracks):
        self.set_active_task(None)
        # Update Feed
        for t in tracks:
            self.log_download(t)
            
        self.btn_download.configure(state="normal", text="Download")
        self.lbl_status.configure(text="Download Completed!", text_color="green")
        self.log_message("Download finished successfully.")
        
        # Update History
        if tracks:
            self.history_manager.add_entry(url, tracks)
            self.after(0, self.refresh_history_ui)
            messagebox.showinfo("Success", f"Downloaded {len(tracks)} tracks successfully!")
        else:
             self.log_message("No new tracks were downloaded.")
             messagebox.showinfo("Done", "Process finished. No new tracks downloaded.")

    def on_download_error(self, error_msg):
        self.set_active_task(None)
        self.btn_download.configure(state="normal", text="Download")
        self.lbl_status.configure(text="Error occurred", text_color="red")
        self.log_message(f"Error: {error_msg}")
        messagebox.showerror("Download Error", error_msg)

    def set_active_task(self, text):
        """Updates the global activity indicator safely."""
        def _update():
            try:
                if text:
                    self.lbl_active_task.configure(text=f"⚙ {text}...")
                else:
                    self.lbl_active_task.configure(text="")
            except: pass # Widget might be gone

        try:
            self.after(0, _update)
        except (RuntimeError, Exception):
            # Fallback if after() fails due to main thread not being in loop
            pass

if __name__ == "__main__":
    app = SpotDLApp()
    app.mainloop()
