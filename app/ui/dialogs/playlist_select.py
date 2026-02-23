import customtkinter as ctk
import threading
from tkinter import messagebox
from app.core.constants import SPOTIPY_AVAILABLE

if SPOTIPY_AVAILABLE:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

class PlaylistSelectionDialog(ctk.CTkToplevel):
    def __init__(self, parent, client_id, client_secret, default_user=""):
        super().__init__(parent)
        self.title("Select Playlists")
        self.geometry("600x600")
        
        # Center
        self.update_idletasks()
        try:
             x = parent.winfo_x() + (parent.winfo_width() // 2) - (600 // 2)
             y = parent.winfo_y() + (parent.winfo_height() // 2) - (600 // 2)
             self.geometry(f"600x600+{x}+{y}")
        except: pass

        self.client_id = client_id
        self.client_secret = client_secret
        self.default_user = default_user
        self.result = None
        self.sp = None

        # UI Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        ctk.CTkLabel(self, text="Select Playlists to Sync", font=("Arial", 16, "bold")).grid(row=0, column=0, pady=10)

        # User ID Input
        input_frame = ctk.CTkFrame(self)
        input_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        
        ctk.CTkLabel(input_frame, text="Spotify User ID:").pack(side="left", padx=5)
        self.entry_user = ctk.CTkEntry(input_frame, width=200)
        self.entry_user.pack(side="left", padx=5)
        if default_user:
            self.entry_user.insert(0, default_user)
            
        self.btn_fetch = ctk.CTkButton(input_frame, text="Fetch Public Playlists", command=self.fetch_playlists)
        self.btn_fetch.pack(side="left", padx=5)

        # Scrollable Checklist
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Playlists")
        self.scroll_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")

        # Buttons
        self.btn_confirm = ctk.CTkButton(self, text="Import Selected", command=self.confirm_selection, state="disabled")
        self.btn_confirm.grid(row=3, column=0, columnspan=2, pady=20)
        
        self.checkboxes = []

        # Auto-fetch if user provided
        if default_user:
            self.after(100, self.fetch_playlists)

    def fetch_playlists(self):
        user_id = self.entry_user.get().strip()
        if not user_id:
            messagebox.showwarning("Input Error", "Please enter a Spotify User ID.")
            return

        if not SPOTIPY_AVAILABLE:
            messagebox.showerror("Error", "Spotipy library not installed.")
            return

        self.btn_fetch.configure(state="disabled", text="Fetching...")
        
        def _thread_target():
            try:
                # Use Client Credentials for public playlists
                # Note: This is simplified. Ideally we use the service or shared auth.
                sp = spotipy.Spotify(auth_manager=spotipy.oauth2.SpotifyClientCredentials(
                    client_id=self.client_id,
                    client_secret=self.client_secret
                ))
                
                playlists = []
                results = sp.user_playlists(user_id)
                playlists.extend(results['items'])
                while results['next']:
                    results = sp.next(results)
                    playlists.extend(results['items'])
                
                self.after(0, lambda: self.populate_list(playlists))
            except Exception as e:
                err_str = str(e)
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to fetch playlists: {err_str}"))
            finally:
                self.after(0, lambda: self.btn_fetch.configure(state="normal", text="Fetch Public Playlists"))

        threading.Thread(target=_thread_target, daemon=True).start()

    def populate_list(self, playlists):
        # Clear existing
        for cb in self.checkboxes:
            cb.destroy()
        self.checkboxes = []

        for pl in playlists:
            if not pl: continue
            name = pl.get('name', 'Unknown')
            url = pl.get('external_urls', {}).get('spotify', '')
            if not url: continue
            
            var = ctk.StringVar(value="off")
            cb = ctk.CTkCheckBox(self.scroll_frame, text=name, variable=var, onvalue=url, offvalue="off")
            cb.pack(anchor="w", padx=10, pady=2)
            self.checkboxes.append((cb, name, url, var))
            
        if self.checkboxes:
            self.btn_confirm.configure(state="normal")
        else:
             ctk.CTkLabel(self.scroll_frame, text="No public playlists found.").pack()

    def confirm_selection(self):
        selected = []
        for cb, name, url, var in self.checkboxes:
            if var.get() != "off":
                selected.append({"name": name, "url": url})
        
        self.result = selected
        self.destroy()
