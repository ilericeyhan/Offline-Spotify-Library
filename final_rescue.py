import json
import os
import sys

bak_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json.bak")
target_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json")

with open(bak_path, 'r', errors='ignore') as f:
    content = f.read()

print(f"Brute forcing rescue for {len(content)} characters...")

found = False
# Start from the end and work backwards
# We want to find the largest valid JSON
for i in range(len(content), 0, -1):
    # Performance: check only near potential closing characters
    if content[i-1] not in ['}', ']', ',', ' ', '\n']:
        continue
        
    candidate = content[:i].strip()
    if candidate.endswith(','):
        candidate = candidate[:-1].strip()
        
    for suffix in ["", "}", "}]", "}]}", "]}", "]]}"]:
        try:
            data = json.loads(candidate + suffix)
            # Basic validation: must have 'library'
            if isinstance(data, dict) and 'library' in data:
                print(f"SUPER SUCCESS! Recovered at index {i} with suffix '{suffix}'")
                with open(target_path, 'w') as f:
                    json.dump(data, f, indent=4)
                print(f"Rescued {len(data['library'])} items.")
                found = True
                break
        except:
            continue
    if found: break
    
    if i % 1000 == 0:
        print(f"Scanning... {i} remaining")

if not found:
    print("Could not rescue any valid library data.")
