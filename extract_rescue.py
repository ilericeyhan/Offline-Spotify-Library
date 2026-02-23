import re
import json
import os

bak_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json.bak")
target_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json")

with open(bak_path, 'r', errors='ignore') as f:
    content = f.read()

print(f"Analyzing {len(content)} characters for playlists...")

# Find all occurrences of URL and Name
# Pattern for a playlist dictionary: { "url": "...", "name": "...", ... }
# We'll just extract the URLs and Names and build a FRESH library to be safe.

playlists = []
seen_urls = set()

# Regex to find Spotify URLs
urls = re.findall(r'https://open.spotify.com/playlist/[a-zA-Z0-9]+', content)
print(f"Found {len(urls)} URLs in file.")

for url in urls:
    if url in seen_urls: continue
    
    # Try to find the name nearby. Search for '"name": "' before or after the URL.
    # Usually it's '"url": "...", "name": "..."'
    name = "Recovered Playlist"
    
    # Simple heuristic: find 'name' within 200 chars of the URL
    url_idx = content.find(url)
    nearby = content[max(0, url_idx-300):url_idx+300]
    name_match = re.search(r'"name":\s*"([^"]+)"', nearby)
    if name_match:
        name = name_match.group(1)
        
    playlists.append({
        "url": url,
        "name": name,
        "type": "playlist"
    })
    seen_urls.add(url)

if playlists:
    # Build a minimal valid config
    # We'll load the truncated one we created earlier to keep the other settings
    try:
        with open(target_path, 'r') as f:
            base_config = json.load(f)
    except:
        base_config = {
            "library": []
        }
        
    base_config["library"] = playlists
    with open(target_path, 'w') as f:
        json.dump(base_config, f, indent=4)
    print(f"RECOVERY COMPLETE: Extracted {len(playlists)} unique playlists.")
else:
    print("Could not find any playlist URLs.")
