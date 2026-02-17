# Offline Spotify Library

**A powerful, modern, and offline-first manager for your Spotify Library.**

This application provides a rich Graphical User Interface (GUI) for `spotdl`, allowing you to synchronize, manage, and organize your Spotify playlists for offline playback. It goes beyond simple downloading by offering a persistent library, drag-and-drop organization, and robust status tracking.

## 💾 Download

Ready-to-use binaries for **Windows**, **macOS**, and **Linux** are available on the [GitHub Releases](https://github.com/ilericeyhan/Offline-Spotify-Library/releases) page. No Python installation required!

## 🚀 Key Features

### 📚 Smart Library Management
*   **Persistent Library**: Track your favorite playlists and keep them synced forever.
*   **Visual Organization**: Create folders, group playlists by genre, and reorder them with simple **Drag & Drop**.
*   **Interactive UI**: A sleek, dark-themed interface with hover effects and responsive design.

### 🔄 Intelligent Sync Status (Smart Sync)
Know the state of your library at a glance with **Smart Status Icons**:
*   🟢 **Synced**: Up-to-date with Spotify.
*   🔄 **New Songs**: New tracks have been detected on Spotify.
*   ⚠️ **Interrupted**: The last sync attempt was aborted (e.g., extreme rate limit).
*   ⚪ **New**: Ready to be synced for the first time.

**Smart Logic**: If you've successfully synced all *newly added* tracks, the app will reward you with a **Green (Synced)** status, even if older tracks have persistent "Partial" or "Lookup" errors. It only turns Orange (🔄) when *new* content is detected.

### 🛡️ Smart Profile Integration
*   **Duplicate Prevention**: Already synced playlists in the "My Profile" tab are automatically identified, deselected, and disabled to prevent redundant downloads.
*   **Visual Feedback**: Sync states are reflected directly in the profile browser with clear status labels.

### 🛡️ Robust Rate Limit Protection
*   **Safety Guards**: The app intelligently detects Spotify's "429 Too Many Requests" errors.
*   **Extreme Limit Protection**: Automatically aborts syncs if Spotify demands a >10 minute coold-down (e.g., the rare 22-hour block), preventing the app from freezing.
*   **Exponential Backoff**: Uses smart retry logic for minor transient errors.

### 📊 Comprehensive History & Diagnosis
*   **Sync Logs**: Every download session is recorded automatically and the UI refreshes in real-time.
*   **Detailed Error Reporting**: When a sync is interrupted, click **"Details"** in the History tab to see the exact error message (e.g., Extreme Rate Limit) displayed in **bold red font** for quick troubleshooting.

---

## 🚀 Getting Started

### Prerequisites
1.  **Python 3.9+** installed.
2.  **FFmpeg** installed and added to your system PATH.
3.  **Spotify API Keys** (Client ID & Client Secret) from the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).

### Installation & Launch

**macOS / Linux (Ubuntu)**
1. Clone the repository and navigate to the folder.
2. Run the setup script:
   ```bash
   chmod +x run.sh
   ./run.sh
   ```

**Windows**
1. Clone the repository and navigate to the folder.
2. Double-click `run.bat` to launch the application.

### 🛡️ macOS Security
If the "Right-click -> Open" method fails, you can manually whitelist the app by running this command in your terminal:

```bash
sudo xattr -rd com.apple.quarantine "/path/to/Offline-Spotify-Library.app"
```

### Initial Configuration
1.  Go to the **Settings** tab.
2.  Set your **Output Path** (where music will be saved).
3.  Enter your **Spotify Client ID** and **Client Secret**.
4.  (Optional) Provide a `cookies.txt` file for YouTube Music to avoid age-restrictions.

---

## ❓ FAQ & Troubleshooting

**Q: My sync is stuck or failing?**
> Check the **History** tab and click **"Details"** on any [Interrupted] session to see the specific error. You can also check the **Logs** tab for low-level process output. If you see "429" errors, Spotify is rate-limiting you—the app will handle this, but you may need to wait.

**Q: Why don't I see new songs?**
> Click **Refresh Status** in the Library tab. If the icon turns Orange (🔄), hit **Sync All**.

**Q: Where is the music saved?**
> In the folder you selected in the **Settings** tab. Each playlist gets its own subfolder, while individual "Quick Downloads" are saved in a dedicated **"Quick Downloads"** folder.

---

## 👨‍💻 Attribution

Developed with ❤️ for music lovers.

**Powered by vibe coding - Antigravity**
