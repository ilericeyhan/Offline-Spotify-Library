#!/bin/bash
# Build script for creating a self-contained macOS .app bundle with spotdl and ffmpeg

set -e  # Exit on error

echo "🔨 Building Offline Spotify Library.app (self-contained, Python 3.13)..."

# Activate virtual environment
source venv/bin/activate

# Install dependencies including spotdl
echo "📦 Ensuring dependencies are correct..."
pip install spotdl pyinstaller customtkinter

# Check if ffmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ ffmpeg not found. Please install it first:"
    echo "   brew install ffmpeg"
    exit 1
fi

# Get ffmpeg path
FFMPEG_PATH=$(which ffmpeg)
FFPROBE_PATH=$(which ffprobe)
echo "✅ Found ffmpeg at: $FFMPEG_PATH"
echo "✅ Found ffprobe at: $FFPROBE_PATH"

# Clean previous build
echo "🧹 Cleaning previous build..."
rm -rf build dist *.spec

# Build the app with all dependencies bundled (using onedir mode for macOS compatibility)
echo "🔨 Building app bundle..."
pyinstaller \
    --name "Offline Spotify Library" \
    --windowed \
    --onedir \
    --add-binary "$FFMPEG_PATH:." \
    --add-binary "$FFPROBE_PATH:." \
    --hidden-import customtkinter \
    --hidden-import PIL._tkinter_finder \
    --hidden-import spotdl \
    --hidden-import spotdl.download \
    --hidden-import spotdl.utils \
    --hidden-import yt_dlp \
    --collect-all spotdl \
    --collect-all yt-dlp \
    --collect-all customtkinter \
    main.py

echo ""
echo "🔏 Comprehensive signing for macOS compatibility..."
# Find and sign all executable files
find "dist/Offline Spotify Library.app" -type f \( -name "*.so" -o -name "*.dylib" -o -name "Offline Spotify Library" \) -exec codesign --force --sign - {} \;

# Clear extended attributes then sign the entire bundle
xattr -cr "dist/Offline Spotify Library.app"
codesign --force --deep --sign - "dist/Offline Spotify Library.app"

echo ""
echo "✅ Build complete! App is in dist/Offline Spotify Library.app"
echo ""
echo "📦 This app is now SELF-CONTAINED and includes:"
echo "   ✓ spotdl"
echo "   ✓ ffmpeg & ffprobe"
echo "   ✓ All Python dependencies"
echo ""
echo "📤 To share with friends:"
echo "   cd dist && zip -r 'Offline Spotify Library.zip' 'Offline Spotify Library.app'"
echo ""
echo "👥 Your friends only need:"
echo "   1. Spotify API credentials (free from developer.spotify.com)"
echo "   2. Download the .zip and extract"
echo "   3. Right-click app > Open (first time only)"
echo ""
