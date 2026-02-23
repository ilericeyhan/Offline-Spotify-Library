import json
import os
import sys

bak_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json.bak")
target_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json")

if not os.path.exists(bak_path):
    print("Backup not found.")
    sys.exit(1)

with open(bak_path, 'r', errors='ignore') as f:
    content = f.read()

print(f"Read {len(content)} characters from backup.")

# Find the first occurrence of "_widget": (which caused the first failure)
# Actually, it's usually the LAST successful write that got cut off.
# Let's find the first one that is NOT closed correctly.
# Or just find the first one at all, since we shouldn't have any.

idx = content.find('"_widget":')
if idx == -1:
    print("No corruption marker found. JSON might be okay or broken elsewhere.")
    idx = len(content)

# Search backwards from the marker for the last valid closing brace of an object
# that was fully written.
found = False
for i in range(idx, 0, -1):
    candidate = content[:i].strip()
    if candidate.endswith(','):
        candidate = candidate[:-1].strip()
    
    # Try common closing sequences for this specific app structure
    for suffix in ["}]}", "]}", "}", "}]", "]]}"]:
        try:
            data = json.loads(candidate + suffix)
            print(f"Restored at index {i} with suffix '{suffix}'")
            with open(target_path, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Successfully rescued {len(data.get('library', []))} items.")
            found = True
            break
        except:
            continue
    if found: break

if not found:
    print("Failed to surgically rescue. Trying brute force from the end...")
    # ... (fallback to previous rescue logic)
