import customtkinter as ctk
import logging
import json
import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

class ToolTip:
    """A simple ToolTip class for widgets."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hide_tooltip()

    def schedule(self):
        self.id = self.widget.after(500, self.show_tooltip)

    def unschedule(self):
        id_val = getattr(self, "id", None)
        if id_val:
            self.widget.after_cancel(id_val)

    def show_tooltip(self, event=None):
        if self.tooltip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        # Use a frame for border
        frame = tk.Frame(tw, background="#333", padx=1, pady=1)
        frame.pack()
        
        # Determine colors based on appearance mode
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg = "#2B2B2B" if is_dark else "#F9F9F9"
        fg = "#FFFFFF" if is_dark else "#000000"
        
        label = tk.Label(frame, text=self.text, justify='left',
                       background=bg, foreground=fg,
                       relief='flat', borderwidth=0,
                       padx=8, pady=4,
                       font=("Arial", 10))
        label.pack()

    def hide_tooltip(self, event=None):
        tw = self.tooltip_window
        self.tooltip_window = None
        if tw:
            tw.destroy()
import shutil
from datetime import datetime
from typing import List, Dict, Optional
import requests
from PIL import Image, ImageTk
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import re

from app.core.constants import APP_NAME, APP_VERSION, SPOTIPY_AVAILABLE, REDIRECT_URI, SCOPES
from app.core.config import ConfigManager
from app.core.history import HistoryManager
from app.services.logger import LogService
from app.services.spotify import SpotifyService
from app.services.downloader import DownloaderService
from app.utils import normalize_spotify_url, get_safe_dirname, format_timestamp
from app.ui.dialogs.group_select import GroupSelectDialog
from app.ui.dialogs.playlist_select import PlaylistSelectionDialog

# Try importing spotipy for direct usage in UI thread helpers
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
    from spotipy.exceptions import SpotifyException
except ImportError:
    pass

class SpotDLApp(ctk.CTk):
    """
    Main GUI Application Class.
    """
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x750")
        
        # Set App Icon
        try:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
            if os.path.exists(icon_path):
                img = Image.open(icon_path)
                # Keep a reference to prevent garbage collection
                self.icon_photo = ImageTk.PhotoImage(img)
                self.wm_iconphoto(False, self.icon_photo)
        except Exception as e:
            print(f"Failed to load icon: {e}")
        
        # Initialize Managers & Services
        self.config_manager = ConfigManager()
        self.history_manager = HistoryManager()
        
        # Setup Services
        self.logger = LogService(log_file="spotdl_debug.log")
        self.logger.set_gui_callback(self.log_message)
        
        self.spotify_service = SpotifyService(self.config_manager, self.logger)
        self.spotify_service.set_status_callback(self.set_active_task)
        self.spotify_service.initialize_client()
        
        self.downloader = DownloaderService(self.config_manager, self.history_manager, self.logger)

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
        self.lbl_lib_refresh_status.pack(side="left", padx=20)
        self._recover_interrupted_syncs()
        self.update_profile_display()
        self.refresh_library_ui()

    def log_message(self, message):
        """Logs a message to the Logs tab text area."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            full_msg = f"{timestamp} - {message}\n"
            self.txt_logs.configure(state="normal")
            self.txt_logs.insert("end", full_msg)
            self.txt_logs.see("end")
            self.txt_logs.configure(state="disabled")
        except:
             pass

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
                user = self.spotify_service.safe_call(sp.current_user)
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
                saved = self.spotify_service.safe_call(sp.current_user_saved_tracks, limit=1)
                if saved:
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
                results = self.spotify_service.safe_call(sp.current_user_playlists, limit=50)
                if results and 'items' in results:
                    playlists.extend(results['items'])
                    while results['next']:
                        results = self.spotify_service.safe_call(sp.next, results)
                        if results and 'items' in results:
                            playlists.extend(results['items'])
                        else:
                            break
                self.log_message(f"Found {len(playlists)} playlists on Spotify.")
            except Exception as e:
                self.log_message(f"Error fetching playlists: {e}")

            self.all_fetched_playlists = playlists 
            self.set_active_task(None)
            
            # Use centralized sorting and UI update
            self.after(0, self.refresh_profile_lists)
            
            # Get display info for header
            display_name = user['display_name']
            followers = user['followers']['total']
            
            # Still need to handle image fetch for header
            image_payload = None
            if user['images']:
                try:
                    img_url = user['images'][0]['url']
                    response = requests.get(img_url, timeout=10)
                    image_payload = Image.open(BytesIO(response.content))
                except Exception as e:
                    self.log_message(f"Failed to fetch profile picture: {e}")

            def _final_ui_update():
                # Set user ID for future refereshes/sorting
                self.last_spotify_user_id = user['id']
                self._update_profile_ui(display_name, followers, image_payload)
            
            self.after(0, _final_ui_update)

            # Update UI
            try:
                # refresh_profile_lists will now handle the population of scroll frames
                pass
            except RuntimeError:
                pass # Main thread not ready or shutting down
            
        except Exception as e:
            try:
                err_msg = str(e)
                self.after(0, lambda: self.lbl_profile_name.configure(text=f"Error: {err_msg}"))
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

    def _update_profile_ui(self, name, followers, image_payload):
        """Updates the profile header info and image."""
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

    def refresh_profile_lists(self):
        """Re-sorts cached playlists based on latest activity and refreshes UI."""
        if not hasattr(self, 'all_fetched_playlists'):
            return
            
        # Build Activity Map (URL -> Latest ISO Timestamp)
        activity_map = {}
        library = self.config_manager.get("library") or []
        for item in library:
            url = item.get('url')
            if not url: continue
            ts_list = [item.get('last_synced'), item.get('last_downloaded'), item.get('spotify_updated')]
            ts_list = [ts for ts in ts_list if ts and isinstance(ts, str) and ts != "Never"]
            if ts_list:
                activity_map[url] = max(ts_list)
        
        history = self.history_manager.history
        for entry in history:
            url = entry.get('source')
            if not url: continue
            ts = entry.get('timestamp')
            if ts and (url not in activity_map or ts > activity_map[url]):
                activity_map[url] = ts
        
        # Key: (Priority (0 for Saved, 1 for others), Usage Count (desc via negation), Name (asc))
        # Sort by Usage then by Original Index (Recent)
        # Note: Spotify API returns playlists in user's order (often custom or added order)
        # We can't strictly get 'last_updated' easily, so we rely on index stability or usage.
        def sort_key(item_tuple):
            index, p = item_tuple
            pin = 1 if p['id'] == 'saved_tracks' else 0
            url = p.get('external_urls', {}).get('spotify', '')
            ts = activity_map.get(url, "0000-00-00")
            return (pin, ts, -index) # reverse=True puts pin 1 first, then latest TS, then smaller index
            
        indexed_playlists = list(enumerate(self.all_fetched_playlists))
        indexed_playlists.sort(key=sort_key, reverse=True)
        
        # Unpack
        sorted_playlists = [p for i, p in indexed_playlists]
        self.all_fetched_playlists = sorted_playlists
        
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
        
        # Reset selections
        self.profile_checkboxes = []
        
        # Trigger Library Discovery (Deep Scan) to find "Synced" status for these playlists
        self.after(0, self.refresh_library_ui)



    def _on_profile_checkbox_toggle(self):
        """Enable or disable the download button based on selection."""
        any_selected = any(entry["var"].get() for entry in self.profile_checkboxes)
        self.btn_dl_selected.configure(state="normal" if any_selected else "disabled", 
                                      text="Download selected and add to the library" if any_selected else "Select playlists to download")

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
                    
                    # Hover Effects
                    def on_enter(e, f=row): f.configure(fg_color="#333333")
                    def on_leave(e, f=row, v=None): 
                         if v and v.get(): f.configure(fg_color="#333333")
                         else: f.configure(fg_color="transparent")

                    row.bind("<Enter>", on_enter)
                    # We need to bind late to pass variable if needed, but 'var' is local. 
                    
                    # Render initial state
                    var = ctk.BooleanVar()
                    
                    # Proper closure for leave event
                    def on_leave_closure(e, f=row, v=var):
                        if v.get(): f.configure(fg_color="#333333")
                        else: f.configure(fg_color="transparent")
                    row.bind("<Leave>", on_leave_closure)
                    
                    # Toggle background when clicked
                    def toggle_bg():
                         if var.get(): row.configure(fg_color="#333333")
                         else: row.configure(fg_color="transparent")
                         self._on_profile_checkbox_toggle()

                    chk = ctk.CTkCheckBox(row, text=pl_name, variable=var, font=("Arial", 12),
                                          command=toggle_bg)
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
        lib_map = {normalize_spotify_url(item.get('url')): item for item in self._flatten_library(library) if item.get('url')}
        
        total = len(queue)
        for i, (pl, lbl, chk) in enumerate(queue):
            try:
                # Correctly handle Spotify object structure
                url = normalize_spotify_url(pl.get('external_urls', {}).get('spotify') or pl.get('url'))
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
        lib_map = {normalize_spotify_url(item.get('url')): item for item in self._flatten_library(library) if item.get('url')}

        for item in self.profile_checkboxes:
            if item["var"].get():
                try:
                    pl = item["data"]
                    # Safe URL extraction (handle both flat 'url' and nested 'external_urls')
                    raw_url = pl.get('url') or pl.get('external_urls', {}).get('spotify')
                    url = normalize_spotify_url(raw_url)
                    
                    # Safe track count
                    track_count = pl.get('tracks', {}).get('total', 0)
                    
                    lib_item = lib_map.get(url)
                    l_path = lib_item.get('local_path') if lib_item else None
                    e_files = lib_item.get('expected_files') if lib_item else None
                    
                    status_text, _, _ = self.get_playlist_sync_status(pl['name'], track_count, l_path, e_files)
                    
                    if status_text.startswith("Synced"):
                        full_synced.append(pl['name'])
                    elif status_text.startswith("Partial"):
                        if messagebox.askyesno("Partial Sync", f"'{pl['name']}' is partially synced ({status_text.split()[-1]}).\n\nWould you like to resume and download missing tracks?"):
                            selected.append(pl)
                            partial_confirmed.append(pl['name'])
                    else:
                        selected.append(pl)
                except Exception as e:
                    self.log_message(f"Error preparing playlist for download: {e}")
                    continue

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
            # Safe URL extraction logic repeated
            raw_url = pl.get('url') or pl.get('external_urls', {}).get('spotify')
            url = normalize_spotify_url(raw_url)
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
                    safe_name = get_safe_dirname(name).strip()
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

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitizes a string to match spotDL's default filename behavior.
        Replaces invalid filesystem characters and standardizes whitespace.
        """
        if not filename:
            return ""
        # 1. Standardize whitespace
        filename = " ".join(filename.split())
        # 2. Characters spotDL/OS usually replace or strip
        # Note: spotDL uses a complex mapping, but these are the most common
        invalid = '<>:"/\\|?*'
        for char in invalid:
            filename = filename.replace(char, '_')
        # 3. Handle specific formatting quirks (optional but helpful)
        # spotDL often replaces special quotes with standard ones
        filename = filename.replace('’', "'").replace('“', '"').replace('”', '"')
        return filename.strip()


    def _safe_spotify_call(self, func, *args, **kwargs):
        """
        Wraps Spotify API calls with rate-limit handling.
        Respects 'Retry-After' header for 429 Too Many Requests.
        """
        if not SPOTIPY_AVAILABLE:
            return None
            
        retries = 0
        max_retries = 3
        
        while retries <= max_retries:
            try:
                return func(*args, **kwargs)
            except SpotifyException as e:
                if e.http_status == 429:
                    retry_after = int(e.headers.get("Retry-After", 1))
                    wait_time = retry_after + 1 # Add buffer
                    
                    if wait_time > 600:
                        self.log_message(f"EXTREME Rate Limit (429): {wait_time}s required. Aborting API call to prevent hang.")
                        self.set_active_task(None)
                        raise Exception(f"Spotify API Extreme Rate Limit: {wait_time}s")

                    self.log_message(f"Rate limited (429). Retrying in {wait_time}s...")
                    self.set_active_task(f"Rate Limited: Waiting {wait_time}s")
                    
                    time.sleep(wait_time)
                    retries += 1
                    
                    if retries > max_retries:
                        self.log_message(f"Max retries exceeded for API call.")
                        self.set_active_task(None)
                        raise e
                else:
                    raise e
            except Exception as e:
                raise e
        return None


    def get_playlist_sync_status(self, name, total_tracks, local_path=None, expected_files=None):
        """
        Ultra-fast status check. Returns (status_text, color, count).
        Simply checks if the folder exists and contains ANY music files.
        Detailed sync state (New Songs) is handled by the worker timestamps.
        """
        if local_path and os.path.exists(local_path):
            full_path = local_path
        else:
            safe_name = get_safe_dirname(name)
            base_path = self.config_manager.get("output_path")
            full_path = os.path.join(base_path, safe_name)
        
        if not name: return "New", "gray", 0
        
        if not os.path.exists(full_path):
            # print(f"DEBUG: Path not found: {full_path}")
            return "New", "gray", 0
            
        # If the folder exists, check for content
        try:
             # Fast check: are there likely enough files?
             files = [f for f in os.listdir(full_path) if f.endswith(('.mp3', '.flac', '.m4a', '.ogg'))]
             count = len(files)
             
             if count == 0:
                 return "New", "gray", 0
             
             if total_tracks > 0 and count >= total_tracks:
                 return "Synced", "green", count
             
             if count > 0:
                 return "Synced", "green", count
                 
             return "Synced", "green", count
        except Exception:
            return "New", "gray", 0

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

            success, tracks = self.downloader.download(url, cwd=target_cwd, status_callback=update_status)
            if success:
                successful_downloads += 1
                total_tracks += len(tracks)
                for t in tracks:
                    self.log_download(t)
        
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
        ToolTip(self.btn_download, "Add this URL to the download queue")

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
        
        # Refresh Indicator (hidden by default)
        self.lbl_lib_refresh_status = ctk.CTkLabel(frm_header, text="🔄 Refreshing Library...", font=("Arial", 11, "italic"), text_color="orange")
        # Start hidden
        
        btn_refresh = ctk.CTkButton(frm_header, text="Refresh Status", command=self.refresh_library_metadata, fg_color="gray")
        btn_refresh.pack(side="right", padx=5)
        ToolTip(btn_refresh, "Check Spotify for new tracks in your library")

        btn_import = ctk.CTkButton(frm_header, text="Import Folder", command=self.import_existing_folder, fg_color="#3a3a3a")
        btn_import.pack(side="right", padx=5)
        ToolTip(btn_import, "Import an existing local music folder")

        btn_add_profile = ctk.CTkButton(frm_header, text="Add from Profile", command=self.open_playlist_selector)
        btn_add_profile.pack(side="right", padx=5)
        ToolTip(btn_add_profile, "Pick playlists directly from a Spotify profile")

        btn_add_url = ctk.CTkButton(frm_header, text="Add URL Manually", command=self.add_manual_url)
        btn_add_url.pack(side="right", padx=5)
        ToolTip(btn_add_url, "Paste a Spotify URL to track and download")

        btn_new_group = ctk.CTkButton(frm_header, text="New Group", command=self.add_new_group, fg_color="#3a3a3a")
        btn_new_group.pack(side="right", padx=5)
        ToolTip(btn_new_group, "Create a new folder to organize your playlists")

        # List of Playlists
        self.library_frame = ctk.CTkScrollableFrame(self.tab_library)
        self.library_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        # Sync Button
        self.btn_sync = ctk.CTkButton(self.tab_library, text="Sync All", command=self.sync_all, fg_color="green", hover_color="darkgreen")
        self.btn_sync.grid(row=2, column=0, pady=10)
        ToolTip(self.btn_sync, "Download all new content for every playlist in your library")

    def refresh_library_ui(self):
        """Reloads the library list with sync status, folder icons, and grouping support."""
        for widget in self.library_frame.winfo_children():
            widget.destroy()
            
        library = self.config_manager.get("library") or []
        
        # 1. Background Logic: Sync URLs from history/disk if missing (discovery always adds to root)
        history = self.history_manager.load_history() or []
        library_urls = self._get_all_library_urls(library)
        ignored_urls = set(normalize_spotify_url(u) for u in (self.config_manager.get("ignored_library_urls") or []))
        
        discovered_count = 0
        for entry in history:
            url = normalize_spotify_url(entry.get('source', ''))
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
                url = normalize_spotify_url(item.get("url", ""))
                if url: urls.add(url)
            elif item.get("type") == "group":
                urls.update(self._get_all_library_urls(item.get("items", [])))
        return urls

    def _render_library_items(self, parent, items, level=0):
        """Recursively renders library items using a staggered approach to keep the UI snappy."""
        if level == 0:
            self._lib_status_queue = []
            if len(items) > 5:
                 self.loading_lbl = ctk.CTkLabel(parent, text="Rendering items...", font=("Arial", 11, "italic"), text_color="gray")
                 self.loading_lbl.pack(pady=10)

        def render_staggered(iterator, current_level, p, source_list):
            # Safety Check 1: Parent must exist (prevent race condition crash)
            try:
                if not p.winfo_exists():
                    return
            except Exception:
                return

            try:
                # Render in batches of 5 to speed up huge libraries
                for _ in range(5):
                    try:
                        idx, item = next(iterator)
                        # Safety Check 2: Render call might fail if p is destroyed mid-call
                        try:
                            self._render_single_item(p, item, current_level, idx, source_list)
                        except Exception as e:
                            self.log_message(f"DEBUG: Error rendering item {idx}: {e}")
                    except StopIteration:
                        raise StopIteration
                
                # Breath the main thread after each batch
                self.after(1, lambda: render_staggered(iterator, current_level, p, source_list))
            except StopIteration:
                if current_level == 0:
                    try:
                        if hasattr(self, 'loading_lbl') and self.loading_lbl.winfo_exists():
                            self.loading_lbl.destroy()
                    except: pass
                    
                    if self._lib_status_queue:
                        threading.Thread(target=self._async_lib_status_worker, daemon=True).start()

        it = enumerate(items)
        render_staggered(it, level, parent, items)

    def _render_single_item(self, parent, item, level, index, source_list):
        """Renders a single playlist or group item with all bells and whistles."""
        item_type = item.get("type", "playlist")
        if item_type == "group":
            # 1. Header Frame
            group_header = ctk.CTkFrame(parent, fg_color="#2b2b2b" if level == 0 else "transparent")
            # Increase indentation step to 50 for clear hierarchy
            indent_px = level * 50 + 5
            group_header.pack(fill="x", padx=(indent_px, 5), pady=2)
            
            # Aligned Toggle Area
            toggle_container = ctk.CTkFrame(group_header, width=30, height=26, fg_color="transparent")
            toggle_container.pack(side="left", padx=(5, 0))
            toggle_container.pack_propagate(False)
            
            exp_char = "▼" if item.get("expanded", True) else "▶"
            btn_toggle = ctk.CTkButton(toggle_container, text=exp_char, width=20, height=20, fg_color="transparent",
                                      hover_color="#333333", command=lambda it=item: self._toggle_group(it))
            btn_toggle.pack(expand=True)
            
            lbl_group = ctk.CTkLabel(group_header, text=item.get("name", "New Group"), font=("Arial", 14, "bold"), text_color="#1DB954")
            lbl_group.pack(side="left", padx=5)
            
            ctk.CTkButton(group_header, text="✖", width=20, height=20, fg_color="transparent", 
                          hover_color="red", command=lambda it=item: self._remove_group(it)).pack(side="right", padx=5)
            ctk.CTkButton(group_header, text="✎", width=20, height=20, fg_color="transparent", 
                          hover_color="#3a3a3a", command=lambda it=item: self._rename_group(it)).pack(side="right", padx=5)

            # 2. Children Container (Reserved Space)
            children_container = ctk.CTkFrame(parent, fg_color="transparent", height=0)
            children_container.pack(fill="x")

            if item.get("expanded", True):
                child_items = item.get("items", [])
                if not child_items:
                    ctk.CTkLabel(children_container, text="  (Empty Group)", font=("Arial", 10, "italic"), text_color="gray").pack(fill="x", padx=(level * 50 + 55, 0))
                else:
                    self._render_library_items(children_container, child_items, level + 1)
        else:
            # Render Playlist Card
            card = ctk.CTkFrame(parent)
            indent_px = level * 50 + 5
            card.pack(fill="x", padx=(indent_px, 5), pady=2)

            # Visual Guide for Nested Items
            # Visual Guide for Nested Items (Simplified)
            if level > 0:
                # Use a label with bg color instead of empty frame to avoid expanding
                guide_lbl = ctk.CTkLabel(card, text="", width=4, fg_color="#1DB954", font=("Arial", 1))
                guide_lbl.pack(side="left", fill="y", pady=4, padx=(0, 4))
            
            # Aligned Handle Area
            # --- Phase 77: Interactive Hover Effect ---
            default_bg = card._fg_color
            hover_bg = "#3a3a3a" # Slightly lighter gray
            
            def _on_enter(e):
                try: card.configure(fg_color=hover_bg)
                except: pass
            def _on_leave(e):
                try: card.configure(fg_color=default_bg)
                except: pass
                
            card.bind("<Enter>", _on_enter)
            card.bind("<Leave>", _on_leave)

            handle_container = ctk.CTkFrame(card, width=30, height=26, fg_color="transparent")
            handle_container.pack(side="left", padx=(5, 0))
            handle_container.pack_propagate(False)
            
            handle = ctk.CTkLabel(handle_container, text="⠿", font=("Arial", 16), cursor="fleur", text_color="gray")
            handle.pack(expand=True)
            handle.bind("<Button-1>", lambda e, it_list=source_list, idx=index: self._on_drag_start(e, it_list, idx))
            handle.bind("<B1-Motion>", self._on_drag_motion)
            handle.bind("<ButtonRelease-1>", self._on_drag_stop)
            
            raw_name = item.get("name", "Unknown")
            lbl_name = ctk.CTkLabel(card, text=raw_name, font=("Arial", 11, "bold"))
            lbl_name.pack(side="left", padx=5)

            # --- Right Side Grid (Metadata & Actions) ---
            right_side = ctk.CTkFrame(card, fg_color="transparent")
            right_side.pack(side="right", padx=5)

            # 1. Action Buttons (Rightmost)
            ctk.CTkButton(right_side, text="Remove", width=55, height=24, fg_color="red", hover_color="darkred",
                          command=lambda it=item: self._smart_remove_item(it)).pack(side="right", padx=5)
            
            btn_sync_item = ctk.CTkButton(right_side, text="Sync", width=55, height=24, fg_color="green", hover_color="darkgreen")
            btn_sync_item.configure(command=lambda u=item.get('url'), n=item.get('name'), b=btn_sync_item, lp=item.get('local_path'): 
                                         self.sync_individual(u, n, b, lp))
            btn_sync_item.pack(side="right", padx=5)
            
            playlist_path = self._get_item_path(item)
            ctk.CTkButton(right_side, text="📂", width=25, height=24, fg_color="transparent", hover_color="#333333",
                          command=lambda p=playlist_path: self.open_file_explorer(p)).pack(side="right", padx=5)
            
            ctk.CTkButton(right_side, text="➔📁", width=25, height=24, fg_color="transparent", hover_color="#333333",
                          command=lambda it=item: self._show_move_dialog_safe(it)).pack(side="right", padx=2)

            def _format_time(iso_str):
                if not iso_str: return None
                try:
                    dt = datetime.fromisoformat(iso_str) if "T" in iso_str else None
                    if dt: return dt.strftime("%d/%m/%Y %H:%M:%S")
                    return iso_str
                except: return None

            # 2. Consolidated Status Badge & Time (Left of Buttons)
            ls_iso = _format_time(item.get('last_synced') or item.get('last_downloaded'))
            lbl_time = ctk.CTkLabel(right_side, text=ls_iso or "Never", font=("Arial", 9), text_color="gray")
            lbl_time.pack(side="right", padx=5)

            status_badge = ctk.CTkLabel(right_side, text="⚪", font=("Arial", 18, "bold"), text_color="gray")
            status_badge.pack(side="right", padx=10)
            
            # Initial Metadata for Tooltip
            st_iso = _format_time(item.get('spotify_updated'))
            tip_text = f"Status: Checking...\nLast Sync: {ls_iso or 'Never'}"
            if st_iso: tip_text += f"\nSpotify Updated: {st_iso}"
            
            self._create_tooltip(status_badge, tip_text)
            
            # Store badge reference for async worker
            self._lib_status_queue.append((item, status_badge, lbl_time))

    def _smart_remove_item(self, target_item):
        """Removes an item by searching for it in the library structure."""
        library = self.config_manager.get("library")
        def _rem_rec(items):
            for i, it in enumerate(items):
                if it is target_item:
                    del items[i]
                    return True
                if it.get("type") == "group" and _rem_rec(it.get("items", [])):
                    return True
            return False
            
        if messagebox.askyesno("Remove", f"Remove '{target_item.get('name')}' from library?"):
            if _rem_rec(library):
                self.config_manager.set("library", library)
                self.refresh_library_ui()

    def _show_move_dialog_safe(self, target_item):
        """Finds items list then shows move dialog."""
        library = self.config_manager.get("library")
        def _find_list(items):
            for it in items:
                if it is target_item: return items
                if it.get("type") == "group":
                    res = _find_list(it.get("items", []))
                    if res: return res
            return None
        lst = _find_list(library)
        if lst: self._show_move_to_group_dialog(target_item, lst)

    def _async_lib_status_worker(self):
        """Processes library sync status checks in the background."""
        self.set_active_task("Checking Library Sync Status")
        # Keep the indicator visible if it was already showing (e.g. startup)
        if not self.lbl_lib_refresh_status.winfo_ismapped():
            self.after(0, lambda: self.lbl_lib_refresh_status.pack(side="left", padx=20))
            
        queue = list(self._lib_status_queue)
        total_items = len(queue)
        checked_count = [0] # List for mutability in closure
        
        def _check_status(item_data):
            try:
                item, lbl, lbl_t = item_data
                raw_name = item.get("name", "Unknown")
                target_count = item.get('total_tracks') or 0
                status_text, status_color, _ = self.get_playlist_sync_status(
                    raw_name, target_count, item.get('local_path'), item.get('expected_files')
                )

                checked_count[0] += 1
                prog = f"Checking Library ({checked_count[0]}/{total_items})"
                self.after(0, lambda: self.lbl_lib_refresh_status.configure(text=f"🔄 {prog}..."))
                
                def _update_ui(st=status_text, sc=status_color, b=lbl, lt=lbl_t, it=item):
                    try:
                        # Logic for Minimalist Icons
                        icon = "⚪"
                        color = "#aaaaaa"
                        tooltip_status = st
                        
                        # 1. Determine Icon based on state
                        sync_time = it.get('last_synced') or it.get('last_downloaded')
                        s_iso = it.get('spotify_updated')
                        
                        # PRIORITY 1: Spotify Updates (User added songs)
                        if s_iso and sync_time and s_iso > sync_time:
                            icon = "🔄"
                            color = "orange"
                            tooltip_status = "New Songs Available"
                        # PRIORITY 2: Interrupted status
                        elif it.get('sync_interrupted'):
                            icon = "⚠️"
                            color = "yellow"
                            tooltip_status += " (Interrupted)"
                        # PRIORITY 3: Never Synced
                        elif st == "New":
                            icon = "⚪"
                            color = "gray"
                        # PRIORITY 4: Fully Synced
                        elif st == "Synced":
                            icon = "🟢"
                            color = "#1DB954"
                        elif "Partial" in st:
                            icon = "🔵"
                            color = "#3498db"
                        
                        b.configure(text=icon, text_color=color)
                        
                        # tooltips need a date formatter
                        def f_time(iso):
                            if not iso: return "Never"
                            try:
                                return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M:%S")
                            except: return iso

                        # Update visible time label if it exists
                        if lt and lt.winfo_exists():
                            lt.configure(text=f_time(sync_time))

                        # 2. Update Tooltip with Consolidated Info
                        tip = f"Status: {tooltip_status}"
                        tip += f"\nLast Sync: {f_time(sync_time)}"
                        if s_iso and (not sync_time or s_iso > sync_time):
                            tip += f"\nSpotify Updated: {f_time(s_iso)}"
                        
                        self._create_tooltip(b, tip)
                    except: pass
                
                self.after(0, _update_ui)
            except: pass

        # Parallelize the checks (up to 10 concurrent disk scans)
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(_check_status, queue)
            
        self.after(0, self.lbl_lib_refresh_status.pack_forget)
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
                url = normalize_spotify_url(pl.get('external_urls', {}).get('spotify'))
                if not url or url in library_urls: continue
                safe_name = get_safe_dirname(pl['name'])
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
        """Internal recursive renderer - DEPRECATED in favor of staggered _render_library_items."""
        pass

    def _get_item_path(self, item):
        """Helper to get local path for a playlist item."""
        if item.get('local_path') and os.path.exists(item['local_path']):
            return item['local_path']
        output_base = self.config_manager.get("output_path")
        safe_name = get_safe_dirname(item.get('name', 'Unknown'))
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

        self.lbl_lib_refresh_status.pack(side="left", padx=20)

        def work():
            self.set_active_task("Refreshing Library Metadata")
            self.log_message("Refreshing Library metadata recursively...")
            library = self.config_manager.get("library") or []
            auth_manager = SpotifyClientCredentials(client_id=cid, client_secret=secret)
            sp = spotipy.Spotify(auth_manager=auth_manager)
            
            def _get_flattened(items):
                res = []
                for it in items:
                    if it.get("type", "playlist") == "playlist": res.append(it)
                    elif it.get("type") == "group": res.extend(_get_flattened(it.get("items", [])))
                return res
            
            all_playlists = _get_flattened(library)
            total_pl = len(all_playlists)
            completed = [0]

            def _refresh_item(item):
                url = item.get('url', '')
                if not url: return
                try:
                    # Parallel refresh is faster, but we keep a small jitter to stay 429-safe
                    time.sleep(0.1)
                    
                    if 'playlist' in url:
                        data = self.spotify_service.safe_call(sp.playlist, url, fields="name,tracks.total")
                        if data:
                            item['name'] = data.get('name', item['name'])
                            item['total_tracks'] = data['tracks']['total']
                    elif 'album' in url:
                        data = self.spotify_service.safe_call(sp.album, url)
                        if data:
                            item['name'] = data.get('name', item['name'])
                            item['total_tracks'] = data['tracks']['total']
                    
                    variants_list, max_spotify_date = self._get_expected_filenames(url, sp=sp)
                    item['expected_files'] = variants_list
                    item['total_tracks'] = len(variants_list)
                    
                    if 'last_synced' not in item:
                        item['last_synced'] = item.get('last_downloaded')
                        
                    item['last_checked'] = datetime.now().isoformat()
                    if max_spotify_date:
                        item['spotify_updated'] = max_spotify_date
                    
                    completed[0] += 1
                    prog = f"Refreshing Metadata ({completed[0]}/{total_pl})"
                    self.after(0, lambda: self.lbl_lib_refresh_status.configure(text=f"🔄 {prog}..."))
                except Exception as e:
                    # Handle 404 or other Spotify Exceptions gracefully
                    if "404" in str(e) or (hasattr(e, 'http_status') and e.http_status == 404):
                        self.log_message(f"Playlist skipped (404 Not Found): {url}")
                        # Mark as unknown/removed but don't crash the loop
                        item['name'] = item.get('name', 'Unknown (Likely Removed)')
                        completed[0] += 1
                        return
                        
                    self.log_message(f"Error refreshing metadata for {url}: {e}")

            # Parallelize API calls (max 5 workers to avoid aggressive 429s)
            with ThreadPoolExecutor(max_workers=5) as executor:
                executor.map(_refresh_item, all_playlists)

            self.config_manager.set("library", library)
            self.set_active_task(None)
            self.after(0, self.lbl_lib_refresh_status.pack_forget)
            self.after(0, self.refresh_library_ui) 
            self.after(0, lambda: messagebox.showinfo("Refresh Complete", f"Successfully refreshed {total_pl} library items."))

        threading.Thread(target=work, daemon=True).start()

    def _get_expected_filenames(self, spotify_url, sp=None):
        """Helper to fetch tracklist and return (list of variants per track, max_spotify_date)."""
        if not SPOTIPY_AVAILABLE or not spotify_url:
            return [], None
            
        try:
            if not sp:
                cid = self.config_manager.get("spotify_client_id")
                secret = self.config_manager.get("spotify_client_secret")
                auth_manager = SpotifyClientCredentials(client_id=cid, client_secret=secret)
                sp = spotipy.Spotify(auth_manager=auth_manager)
            
            tracks = []
            max_date = None
            
            if 'playlist' in spotify_url:
                # Include added_at to track when the playlist was last updated on Spotify
                results = self.spotify_service.safe_call(sp.playlist_items, spotify_url, fields="items(added_at,track(name,artists(name))),next")
                if results and 'items' in results:
                    tracks.extend(results['items'])
                    while results['next']:
                        results = self.spotify_service.safe_call(sp.next, results)
                        if not results: break
                        tracks.extend(results['items'])
                
                # Extract max added_at
                dates = [i.get('added_at') for i in tracks if i.get('added_at')]
                if dates:
                    max_date = max(dates)
            elif 'album' in spotify_url:
                album_data = self.spotify_service.safe_call(sp.album, spotify_url)
                if album_data:
                    max_date = album_data.get('release_date')
                
                results = self.spotify_service.safe_call(sp.album_tracks, spotify_url)
                if results and 'items' in results:
                    tracks = [{"track": t} for t in results['items']]
                    while results['next']:
                        results = self.spotify_service.safe_call(sp.next, results)
                        if not results: break
                        tracks.extend([{"track": t} for t in results['items']])

            expected_variants = []
            for item in tracks:
                t = item.get('track')
                if not t: continue
                
                artists = [a['name'] for a in t['artists']]
                title = t['name']
                
                # VARIANT EXPLOSION ENGINE
                # -------------------------
                base_variants = []
                
                # 1. Primary Artist only
                primary = artists[0]
                base_variants.append(f"{primary} - {title}")
                
                # 2. All Artists with different separators
                if len(artists) > 1:
                    # spotDL default: "Artist 1, Artist 2 - Title"
                    base_variants.append(f"{', '.join(artists)} - {title}")
                    # Common alternative: "Artist 1 & Artist 2 - Title"
                    base_variants.append(f"{' & '.join(artists)} - {title}")
                    # Common alternative: "Artist 1 and Artist 2 - Title"
                    base_variants.append(f"{' and '.join(artists)} - {title}")
                    # Space separated: "Artist 1 Artist 2 - Title"
                    base_variants.append(f"{' '.join(artists)} - {title}")

                # 3. Handle (feat. X) variations in Title
                # Some spotDL versions move feat to the end or strip it
                expanded = []
                for bv in base_variants:
                    expanded.append(bv)
                    if " (feat. " in bv:
                        # Variant without feat. suffix
                        expanded.append(bv.split(" (feat. ")[0])
                    elif " feat. " in bv:
                        expanded.append(bv.split(" feat. ")[0])

                # Sanitize all and deduplicate
                track_variants = set()
                for v in expanded:
                    sanitized = self._sanitize_filename(v).lower()
                    if sanitized:
                        track_variants.add(sanitized)
                
                expected_variants.append(list(track_variants))
                
            return expected_variants, max_date
        except Exception as e:
            self.log_message(f"Error fetching expected filenames: {e}")
            return []

    def _update_item_timestamps(self, url, downloaded=False, checked=False):
        """Helper to update timestamp fields for a playlist in the library."""
        library = self.config_manager.get("library") or []
        norm_url = normalize_spotify_url(url)
        now = datetime.now().isoformat()
        
        def _update_recursive(items):
            found = False
            for item in items:
                if item.get("type", "playlist") == "playlist":
                    if normalize_spotify_url(item.get("url")) == norm_url:
                        if checked: 
                            item['last_checked'] = now
                            item['last_synced'] = now # New consistent field
                        if downloaded: item['last_downloaded'] = now
                        found = True
                elif item.get("type") == "group":
                    if _update_recursive(item.get("items", [])):
                        found = True
            return found

        if _update_recursive(library):
            self.config_manager.set("library", library)

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
            new_item = {
                "url": normalize_spotify_url(url), 
                "name": name,
                "last_checked": datetime.now().isoformat()
            }
            library.append(new_item)
            self.config_manager.set("library", library)
            
            # Add to History
            self.history_manager.add_entry(url, 0, name=f"[MANUAL] {name}")
            self.after(0, self.refresh_history_ui)
            
            self.refresh_library_ui()


    def import_existing_folder(self):
        """Allows importing an existing folder and linking it to a Spotify URL."""
        if not SPOTIPY_AVAILABLE:
            messagebox.showwarning("Spotify API", "Spotify API is not available.")
            return

        folder = filedialog.askdirectory(title="Select Existing Playlist Folder", initialdir=self.config_manager.get("output_path"))
        if not folder: return

        url = simpledialog.askstring("Spotify URL", "Paste the Spotify Playlist URL for this folder:")
        if not url: return
        url = normalize_spotify_url(url)

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
                    safe_name = get_safe_dirname(pl_name)
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
                    "total_tracks": track_count,
                    "last_checked": datetime.now().isoformat()
                }
                if local_path:
                    new_item["local_path"] = local_path
                    
                library.append(new_item)
                self.config_manager.set("library", library)
                
                # Add to History
                self.history_manager.add_entry(url, track_count, name=f"[IMPORTED] {pl_name}")
                self.after(0, self.refresh_history_ui)
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
        
        if dialog.result:
            library = self.config_manager.get("library")
            library.extend(dialog.result)
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
            safe_name = get_safe_dirname(name)
            target_cwd = os.path.join(base_path, safe_name)
        
        if not os.path.exists(target_cwd):
            try: os.makedirs(target_cwd, exist_ok=True)
            except: pass

        # Track progress for crash recovery
        self._set_item_progress_flag(url, True)
        success, tracks = self.downloader.download(url, cwd=target_cwd)
        self._set_item_progress_flag(url, False)
        
        # Update sync_interrupted flag based on success
        self._set_item_interrupted_flag(url, not success)
        
        # Final UI update
        self._update_item_timestamps(url, downloaded=(len(tracks) > 0), checked=True)
        
        self.set_active_task(None)
        self.after(0, self.refresh_library_ui)
        self.set_active_task(None)
        
        if success:
            count = len(tracks)
            self.log_message(f"Successfully synced {name} ({count} tracks).")
            
            # Populate Download Feed
            for track in tracks:
                self.log_download(track)
            
            if button:
                def _safe_button_reset_success():
                    try:
                        if button.winfo_exists():
                            button.configure(state="normal", text="Sync", fg_color="green")
                    except: pass
                self.after(0, _safe_button_reset_success)
            
            # Format track list for popup
            if count > 0:
                display_tracks = tracks[:10]
                tracks_str = "\n- ".join(display_tracks)
                if count > 10:
                    tracks_str += f"\n... and {count - 10} more"
                msg = f"Finished syncing '{name}'.\n\nNewly Synced Songs:\n- {tracks_str}"
            else:
                # Log an "Up-to-date" entry so user sees the check in history
                self.history_manager.add_entry(url, 0, name=f"[SYNC] {name} (Up-to-date)")
                self.after(0, self.refresh_history_ui)
                msg = f"Finished syncing '{name}'.\n(All tracks were already up to date)"
                
            self.after(0, lambda: messagebox.showinfo("Sync Complete", msg))
        else:
            self.log_message(f"Failed to sync {name}. Check logs.")
            if button:
                def _safe_button_reset():
                    try:
                        if button.winfo_exists():
                            button.configure(state="normal", text="Sync", fg_color="green")
                    except: pass
                self.after(0, _safe_button_reset)

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
                safe_name = get_safe_dirname(name)
                target_cwd = os.path.join(base_path, safe_name)
                
            if not os.path.exists(target_cwd):
                os.makedirs(target_cwd, exist_ok=True)
                
            self._set_item_progress_flag(item['url'], True)
            success, tracks = self.downloader.download(item['url'], cwd=target_cwd)
            self._set_item_progress_flag(item['url'], False)
            
            self._set_item_interrupted_flag(item['url'], not success)
            
            if success:
                all_new_tracks.extend(tracks)
                # Update last_downloaded if tracks > 0, always check
                self._update_item_timestamps(item['url'], downloaded=(len(tracks) > 0), checked=True)
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





    def setup_history_tab(self):
        """Builds the History tab."""
        self.tab_history.grid_columnconfigure(0, weight=1)
        self.tab_history.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(self.tab_history, text="Download History", font=("Arial", 18, "bold")).grid(row=0, column=0, pady=10)
        
        # Scrollable Frame for history items
        self.history_frame = ctk.CTkScrollableFrame(self.tab_history)
        self.history_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        # Button Row
        btn_row = ctk.CTkFrame(self.tab_history, fg_color="transparent")
        btn_row.grid(row=2, column=0, pady=10)
        
        btn_refresh_hist = ctk.CTkButton(btn_row, text="Refresh", command=self.refresh_history_ui)
        btn_refresh_hist.pack(side="left", padx=5)
        ToolTip(btn_refresh_hist, "Reload the download history from disk")

        btn_clear_hist = ctk.CTkButton(btn_row, text="Clear History", command=self.confirm_clear_history, fg_color="red", hover_color="darkred")
        btn_clear_hist.pack(side="left", padx=5)
        ToolTip(btn_clear_hist, "Permanently delete all download records")
        
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
            
        # Use live list from manager instead of reloading from disk
        history = self.history_manager.history
        if not history:
            ctk.CTkLabel(self.history_frame, text="No history found.").pack(pady=20)
            return

        # Sort history by newest first (create a copy)
        history_items = history[::-1]
        history_updated = False

        for i, entry in enumerate(history_items):
            card = ctk.CTkFrame(self.history_frame)
            card.pack(fill="x", padx=5, pady=2)
            
            # Header with Name and Time
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=10, pady=5)
            
            ts = datetime.fromisoformat(entry['timestamp']).strftime("%m-%d %H:%M")
            entry_name = entry.get('name')
            source_url = entry.get('source', 'Unknown')
            
            if not entry_name or entry_name == "Downloaded Playlist":
                resolved = self.resolve_name_from_url(source_url)
                if resolved and resolved != source_url:
                    entry_name = resolved
                    orig_idx = len(history) - 1 - i
                    history[orig_idx]['name'] = resolved
                    history_updated = True
            
            display_name = entry_name if entry_name else source_url
            if len(display_name) > 60:
                display_name = display_name[:57] + "..."
                
            interrupted_tag = " [Interrupted]" if entry.get('interrupted') else ""
            lbl_info = ctk.CTkLabel(top_row, text=f"{ts} - {display_name}{interrupted_tag}", 
                                    font=("Arial", 12, "bold"), anchor="w")
            if interrupted_tag:
                lbl_info.configure(text_color="orange")
            lbl_info.pack(side="left", fill="x", expand=True)

            count = entry.get('count', 0)
            lbl_count = ctk.CTkLabel(top_row, text=f"{count} tracks", text_color="gray")
            lbl_count.pack(side="right", padx=10)

            # Hover Effects
            def on_enter(e):
                card.configure(fg_color=("gray75", "gray25"))

            def on_leave(e):
                card.configure(fg_color=("gray86", "gray17"))

            for w in [card, top_row, lbl_info, lbl_count]:
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)

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
        btn_browse_cookie = ctk.CTkButton(self.tab_settings, text="Browse", width=80, command=self.browse_cookie)
        btn_browse_cookie.grid(row=0, column=2, padx=10)
        ToolTip(btn_browse_cookie, "Select a cookies.txt file to bypass YouTube age-restrictions")

        # Output Path
        ctk.CTkLabel(self.tab_settings, text="Output Path:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.entry_output = ctk.CTkEntry(self.tab_settings)
        self.entry_output.insert(0, self.config_manager.get("output_path"))
        self.entry_output.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        btn_browse_output = ctk.CTkButton(self.tab_settings, text="Browse", width=80, command=self.browse_output)
        btn_browse_output.grid(row=1, column=2, padx=10)
        ToolTip(btn_browse_output, "Choose the root folder where all music will be saved")
        
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
        
        btn_save = ctk.CTkButton(self.tab_settings, text="Save Settings", command=self.save_settings)
        btn_save.grid(row=10, column=0, columnspan=3, pady=(20, 10))
        ToolTip(btn_save, "Save all configuration changes to disk")
        
        btn_restore = ctk.CTkButton(self.tab_settings, text="Restore Defaults", command=self.confirm_restore_defaults, fg_color="red", hover_color="darkred")
        btn_restore.grid(row=11, column=0, columnspan=3, pady=10)
        ToolTip(btn_restore, "Reset all settings to their initial factory values")


    def setup_about_tab(self):
        """Builds the About/FAQ tab with a professional structured view."""
        self.tab_about.grid_columnconfigure(0, weight=1)
        self.tab_about.grid_rowconfigure(0, weight=1)

        # Scrollable container for the whole tab
        scroll_about = ctk.CTkScrollableFrame(self.tab_about, fg_color="transparent")
        scroll_about.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        scroll_about.grid_columnconfigure(0, weight=1)

        # 1. Hero Section
        hero_frm = ctk.CTkFrame(scroll_about, fg_color="transparent")
        hero_frm.pack(fill="x", pady=(20, 30))
        
        # Logo
        try:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
            if os.path.exists(icon_path):
                img = Image.open(icon_path)
                logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(120, 120))
                lbl_logo = ctk.CTkLabel(hero_frm, image=logo_img, text="")
                lbl_logo.pack(pady=5)
        except Exception:
            pass

        ctk.CTkLabel(hero_frm, text=APP_NAME, font=("Arial", 32, "bold")).pack()
        ctk.CTkLabel(hero_frm, text=f"Version {APP_VERSION}", font=("Arial", 16), text_color="gray").pack()
        
        # 2. Load and Basic Parse README.md
        content = ""
        possible_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../README.md"),
            "README.md"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    break
                except Exception:
                    continue

        if not content:
            ctk.CTkLabel(scroll_about, text="Could not load README.md documentation.").pack(pady=20)
            return

    def _render_markdown_block(self, container, text, default_indent=0):
        """Renders a block of markdown text (potentially containing lists, code blocks, etc)."""
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                i += 1
                continue

            # Detect leading whitespace for relative indentation
            indent_level = len(line) - len(line.lstrip())
            total_indent = default_indent + (indent_level * 2) # scale indent

            if stripped.startswith("```"):
                # Code Block
                code_lines = []
                # Check if it has a lang like ```bash
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1 # skip closing ```
                
                if not code_lines: continue
                
                code_text = "\n".join(code_lines)
                code_frm = ctk.CTkFrame(container, fg_color=("gray85", "gray10"), corner_radius=8)
                code_frm.pack(fill="x", padx=(total_indent + 25, 25), pady=12)
                
                # If short, use a label to avoid scrollbars
                if len(code_lines) <= 15:
                    lbl_code = ctk.CTkLabel(code_frm, text=code_text, font=("Courier", 12), 
                                          justify="left", anchor="w")
                    lbl_code.pack(fill="x", padx=15, pady=15)
                else:
                    # For long code, use a textbox with a fixed height
                    txt = ctk.CTkTextbox(code_frm, height=300, 
                                       wrap="none", font=("Courier", 12), fg_color="transparent")
                    txt.insert("0.0", code_text)
                    txt.configure(state="disabled")
                    txt.pack(fill="x", padx=15, pady=15)
                continue

            elif stripped.startswith(("* ", "- ", "> ")) or (stripped and stripped[0].isdigit() and ". " in stripped[:4]):
                # List Item or Quote
                marker = ""
                content = ""
                item_indent = total_indent
                
                if stripped.startswith(("* ", "- ")):
                    marker = " • "
                    content = stripped[2:].strip()
                elif stripped.startswith("> "): 
                    marker = "   " # Remove the bar for simpler look
                    content = stripped[2:].strip()
                else: # Ordered list N.
                    dot_idx = stripped.find(". ")
                    marker = f" {stripped[:dot_idx + 1]} "
                    content = stripped[dot_idx + 2:].strip()
                    # Add extra space for ordered lists to align markers
                    item_indent += 5
                
                # Clean markers and URL syntax [text](url) -> text
                import re
                content = content.replace("**", "")
                content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
                
                lbl = ctk.CTkLabel(container, text=f"{marker}{content}", font=("Arial", 13), 
                                   justify="left", anchor="w", wraplength=720 - item_indent)
                lbl.pack(fill="x", padx=(item_indent + 25, 15), pady=3)
                i += 1
            else:
                # Ordinary text
                if stripped.startswith("---"): # Skip any divider variations
                    i += 1
                    continue
                
                import re
                content = stripped.replace("**", "")
                content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
                
                # Check for FAQ style "Q: ..." or "**Q: ...**"
                if content.upper().startswith("Q:") or (content.startswith("**Q:") and content.endswith("**")):
                    # Create a Question Card
                    card = ctk.CTkFrame(container, fg_color=("gray88", "gray13"), corner_radius=6)
                    card.pack(fill="x", padx=(total_indent + 25, 15), pady=8)
                    
                    lbl = ctk.CTkLabel(card, text=content, font=("Arial", 14, "bold"), 
                                       wraplength=760 - total_indent, justify="left", anchor="w")
                    lbl.pack(fill="x", padx=15, pady=12)
                else:
                    lbl = ctk.CTkLabel(container, text=content, font=("Arial", 14), 
                                       wraplength=780 - total_indent, justify="left", anchor="w")
                    lbl.pack(fill="x", padx=(total_indent + 25, 15), pady=6)
                i += 1

    def setup_about_tab(self):
        """Builds the About/FAQ tab with a professional structured view."""
        self.tab_about.grid_columnconfigure(0, weight=1)
        self.tab_about.grid_rowconfigure(0, weight=1)

        # Scrollable container for the whole tab
        scroll_about = ctk.CTkScrollableFrame(self.tab_about, fg_color="transparent")
        scroll_about.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        scroll_about.grid_columnconfigure(0, weight=1)

        # 1. Hero Section
        hero_frm = ctk.CTkFrame(scroll_about, fg_color="transparent")
        hero_frm.pack(fill="x", pady=(20, 30))
        
        # Logo
        try:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
            if os.path.exists(icon_path):
                img = Image.open(icon_path)
                logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(120, 120))
                lbl_logo = ctk.CTkLabel(hero_frm, image=logo_img, text="")
                lbl_logo.pack(pady=5)
        except Exception:
            pass

        ctk.CTkLabel(hero_frm, text=APP_NAME, font=("Arial", 32, "bold")).pack()
        ctk.CTkLabel(hero_frm, text=f"Version {APP_VERSION}", font=("Arial", 16), text_color="gray").pack()
        
        # 2. Load README.md
        content = ""
        possible_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../README.md"),
            "README.md"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    break
                except Exception:
                    continue

        if not content:
            ctk.CTkLabel(scroll_about, text="Could not load README.md documentation.").pack(pady=20)
            return

        # Simple Section Parser
        sections = content.split("\n\n")
        current_card = None
        
        for sec in sections:
            sec = sec.strip()
            if not sec: continue

            if sec.startswith("# "):
                continue

            elif sec.startswith("## "):
                # Section Header
                title = sec.replace("## ", "").strip()
                # Skip Attribution section as we handle it in footer
                if "Attribution" in title:
                    current_card = "SKIP"
                    continue

                lbl = ctk.CTkLabel(scroll_about, text=title, font=("Arial", 22, "bold"), anchor="w")
                lbl.pack(fill="x", padx=20, pady=(30, 5))
                # Add a thick separator
                sep = ctk.CTkFrame(scroll_about, height=3, fg_color="#3498db")
                sep.pack(fill="x", padx=20, pady=(0, 15))
                current_card = None
                
            elif sec.startswith("### "):
                lines = sec.split("\n")
                title = lines[0].replace("### ", "").strip()
                
                card = ctk.CTkFrame(scroll_about, fg_color=("gray90", "gray15"), corner_radius=10)
                card.pack(fill="x", padx=25, pady=12)
                
                lbl_title = ctk.CTkLabel(card, text=title, font=("Arial", 18, "bold"), anchor="w", text_color="#3498db")
                lbl_title.pack(fill="x", padx=15, pady=(15, 10))
                
                # Render the rest of this section into the card
                body = "\n".join(lines[1:])
                if body.strip():
                    self._render_markdown_block(card, body, default_indent=5)
                current_card = card
            
            elif current_card == "SKIP":
                continue
            else:
                # Content block for current card or scroll area
                target = current_card if current_card else scroll_about
                indent = 5 if current_card else 0
                self._render_markdown_block(target, sec, default_indent=indent)

        # 3. Clean Professional Footer
        foot_frm = ctk.CTkFrame(scroll_about, fg_color="transparent")
        foot_frm.pack(fill="x", pady=(60, 30))
        ctk.CTkLabel(foot_frm, text=f"{APP_NAME} v{APP_VERSION}", font=("Arial", 11, "bold"), text_color="gray").pack()
        ctk.CTkLabel(foot_frm, text="Developed with ❤️ for music lovers", font=("Arial", 10), text_color="gray").pack()
        ctk.CTkLabel(foot_frm, text="Powered by Antigravity", font=("Arial", 9, "italic"), text_color="gray").pack()



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

        # Textbox for the Feed (More reliable than many labels)
        self.txt_feed = ctk.CTkTextbox(self.tab_logs, height=150, font=("Arial", 12))
        self.txt_feed.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.txt_feed.configure(state="disabled")
        
        # Divider/Label for Technical Logs
        ctk.CTkLabel(self.tab_logs, text="Technical Debug Logs", font=("Arial", 10, "italic"), text_color="gray").grid(row=2, column=0, padx=10, pady=(5, 0), sticky="w")

        # Technical Debug Logs
        self.txt_logs = ctk.CTkTextbox(self.tab_logs)
        self.txt_logs.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.tab_logs.grid_rowconfigure(3, weight=2) # Debug logs are larger

    def toggle_download_feed(self):
        """Toggles the visibility of the download feed."""
        if self.feed_expanded:
            self.txt_feed.grid_forget()
            self.btn_toggle_feed.configure(text="Expand")
            self.feed_expanded = False
        else:
            self.txt_feed.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
            self.btn_toggle_feed.configure(text="Collapse")
            self.feed_expanded = True

    def log_download(self, track_name):
        """Adds a track to the session download feed."""
        self.session_new_downloads.append(track_name)
        
        def _update_feed():
            ts = datetime.now().strftime('%H:%M:%S')
            if hasattr(self, 'txt_feed'):
                self.txt_feed.configure(state="normal")
                self.txt_feed.insert("end", f"[{ts}] {track_name}\n")
                self.txt_feed.configure(state="disabled")
                self.txt_feed.see("end")
        
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

        cmd.extend(["download", normalize_spotify_url(url)])
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
        # No longer redundant: history handled in download_synchronously or batch
        self.log_message("Download finished successfully.")
        messagebox.showinfo("Success", f"Downloaded {len(tracks)} tracks successfully!")

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

    # --- Sync & History Helpers ---
    def _set_item_interrupted_flag(self, url, is_interrupted):
        """Sets the sync_interrupted flag for a library item."""
        library = self.config_manager.get("library") or []
        norm_url = normalize_spotify_url(url)
        
        def _set_rec(items):
            for item in items:
                if item.get("type", "playlist") == "playlist":
                    if normalize_spotify_url(item.get("url")) == norm_url:
                        item['sync_interrupted'] = is_interrupted
                        return True
                elif item.get("type") == "group":
                    if _set_rec(item.get("items", [])): return True
            return False
            
        if _set_rec(library):
            self.config_manager.set("library", library)

    def confirm_clear_history(self):
        """Prompts and wipes history."""
        if messagebox.askyesno("Clear History", "Are you sure you want to clear your download history?"):
            self.history_manager.clear_history()
            self.refresh_history_ui()
            messagebox.showinfo("History Cleared", "History has been wiped.")

    def _recover_interrupted_syncs(self):
        """Checks library for items that were in progress when the app closed."""
        library = self.config_manager.get("library") or []
        updated = False
        
        def _rec(items):
            nonlocal updated
            for it in items:
                if it.get("sync_in_progress"):
                    it["sync_in_progress"] = False
                    it["sync_interrupted"] = True
                    updated = True
                if it.get("type") == "group":
                    _rec(it.get("items", []))
                    
        _rec(library)
        if updated:
            self.config_manager.set("library", library)

    def _set_item_progress_flag(self, url, in_progress):
        """Sets the sync_in_progress flag for a library item."""
        library = self.config_manager.get("library") or []
        norm_url = normalize_spotify_url(url)
        
        def _set_rec(items):
            for item in items:
                if item.get("type", "playlist") == "playlist":
                    if normalize_spotify_url(item.get("url")) == norm_url:
                        item['sync_in_progress'] = in_progress
                        return True
                elif item.get("type") == "group":
                    if _set_rec(item.get("items", [])): return True
            return False
            
        if _set_rec(library):
            self.config_manager.set("library", library)

    # --- UI Helpers ---
    def _create_tooltip(self, widget, text):
        """Simple hover tooltip for CTK widgets that supports dynamic updates."""
        widget.tooltip_text = text
        if hasattr(widget, "_has_tooltip_binding"):
            return
            
        widget._has_tooltip_binding = True
        tooltip_window = [None]
        
        def show_tooltip(event):
            # Read text dynamically from the widget attribute
            current_text = getattr(widget, "tooltip_text", "")
            if tooltip_window[0] or not current_text: return
            
            x = event.x_root + 20
            y = event.y_root + 10
            
            tw = ctk.CTkToplevel(self)
            tw.wm_overrideredirect(True)
            tw.geometry(f"+{x}+{y}")
            tw.attributes("-topmost", True)
            
            label = ctk.CTkLabel(tw, text=current_text, fg_color="#333333", text_color="white", 
                                 corner_radius=6, padx=10, pady=5, font=("Arial", 11))
            label.pack()
            tooltip_window[0] = tw

        def hide_tooltip(event):
            if tooltip_window[0]:
                tooltip_window[0].destroy()
                tooltip_window[0] = None

        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)

if __name__ == "__main__":
    app = SpotDLApp()
    app.mainloop()
