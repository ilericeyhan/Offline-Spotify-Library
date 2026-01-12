# How to Package and Share the App

## Building the Self-Contained App

### Prerequisites (Only for Building)
You need `ffmpeg` installed on **your machine** to build the app:
```bash
brew install ffmpeg
```

### Build Steps

1. **Run the build script:**
   ```bash
   ./build_app.sh
   ```

2. **The app will be created in:**
   ```
   dist/Offline Spotify Library.app
   ```

3. **Package for distribution:**
   ```bash
   cd dist
   zip -r "Offline Spotify Library.zip" "Offline Spotify Library.app"
   ```

## What Your Friends Need

### ✅ Good News: Almost Nothing!

The app is **self-contained** and includes:
- ✓ spotdl (bundled)
- ✓ ffmpeg & ffprobe (bundled)
- ✓ All Python dependencies (bundled)

They **only** need:

1. **Spotify API Credentials** (free):
   - Go to https://developer.spotify.com/dashboard
   - Create an app (takes 2 minutes)
   - Note the **Client ID** and **Client Secret**
   - Add redirect URI: `http://127.0.0.1:8888/callback`

2. **Spotify Cookies** (for downloading):
   - Get from browser using an extension like "Get cookies.txt LOCALLY"
   - Add via Settings tab in the app

### Installation

1. Download the `.zip` file
2. Unzip and drag `Offline Spotify Library.app` to Applications folder
3. **First launch:** Right-click > Open (to bypass macOS security)
4. Click "Link Profile" and enter Spotify credentials
5. Add cookie file path in Settings
6. Start downloading!

## Important Notes

- **First launch security warning:** macOS will show a warning because the app isn't signed. Users need to right-click > Open.
- **Size:** The app bundle will be ~200-300 MB due to bundled dependencies
- **macOS only:** This build is for macOS. Windows/Linux users need the source code version.

## Signing the App (Optional)

To avoid the security warning, you can sign the app with an Apple Developer account:
```bash
codesign --deep --force --verify --verbose --sign "Developer ID Application: Your Name" "dist/Offline Spotify Library.app"
```

## Alternative: Share Source Code

For cross-platform support or smaller download size:
```bash
# Your friends would run:
git clone <your-repo>
cd spotdl_gui
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install spotdl
brew install ffmpeg  # or equivalent for their OS
./run.sh
```
