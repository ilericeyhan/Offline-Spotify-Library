========================================================================
             SPOTDL GUI - OFFLINE SPOTIFY LIBRARY MANAGER
========================================================================
Version: 1.3.0
========================================================================

1. INTRODUCTION
---------------
SpotDL GUI is a powerful tool designed to help you manage and download
your Spotify playlists for offline use. It uses 'spotdl' in the background
to fetch high-quality audio while providing a clean, organized interface
for your music library.

2. GETTING STARTED
------------------
A. PREREQUISITES:
   - Python 3.9+ installed.
   - FFmpeg installed and added to your system PATH.
   - Spotify API Keys (Client ID & Client Secret).

B. SETUP:
   1. Go to the 'Settings' tab and set your 'Output Path' (where music is saved).
   2. Go to 'My Profile' tab and click 'Login with Spotify'. 
      You will be prompted to enter your credentials in the Settings tab.
   3. Once logged in, you can fetch your playlists and add them to your Sync Library.

C. WHY DO I NEED API KEYS (CLIENT ID/SECRET)?
   - PRIVACY: By using your own keys, this app talks DIRECTLY to Spotify. 
     Your data never passes through a third-party server.
   - SECURITY: Your login happens via official Spotify OAuth in your browser. 
     The app only stores a temporary "permission token" locally on your machine.
   - CONTROL: You are in full control of your "app" via the Spotify Dashboard.

3. UNDERSTANDING THE TABS
-------------------------
- LIBRARY: The heart of the app. Track your synchronized playlists here.
- DOWNLOADER: Quick download for any single Spotify URL (Playlist, Album, Song).
- MY PROFILE: Manage your Spotify account, browse playlists, and add them to sync.
- HISTORY: View all your past download sessions and recently added tracks.
- SETTINGS: Configure paths, API keys, cookie files, and UI preferences.
- LOGS: Technical debug logs and a live "New Downloads" feed.
- ABOUT/FAQ: This guide and common troubleshooting steps.

4. KEY FEATURES
---------------
A. PLAYLIST GROUPING (TREE VIEW):
   You can create "Groups" in the Library tab to organize playlists (e.g., By Genre).
   Use the "➔📁" button on any playlist to move it into a group.
   Toggle groups with the "▶/▼" icons to keep your view tidy.

B. SMART REORDERING:
   Grab the "⠿" handle on any playlist to move it up or down. Your custom 
   order is saved automatically.

C. SYNC LOGIC:
   Click "Sync All" in the Library to automatically download any new songs
   added to your tracked playlists. The app remembers what you have and 
   only downloads what's missing.

D. EXTRA TRACKS DETECTION:
   If you delete a song from Spotify but it stays on your disk, the app 
   will show "(+X extras)". Click it to see and manage those files.

5. FAQ / TROUBLESHOOTING
------------------------
Q: Why aren't my playlist names refreshing?
A: Go to Settings and ensure your Spotify API keys are correct. Then use 
   the "Refresh Status" button in the Library tab.

Q: Where is my music?
A: Music is saved in your 'Output Path' (set in Settings), typically 
   categorized into subfolders with the playlist name.

Q: The sync is failing/stuck. What do I do?
A: Check the 'Logs' tab for specific errors. Often, updating 'spotdl' 
   (pip install -U spotdl) or providing a 'Cookie File' in Settings fixes 
   most connection issues.

Q: How do I move a playlist out of a group?
A: Click the "➔📁" button and select "Root" from the dropdown menu.

========================================================================
Developed with love for music lovers. 🚀🎶
========================================================================
