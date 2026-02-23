import re
import json
import os

bak_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json.bak")
target_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json")

with open(bak_path, 'r', errors='ignore') as f:
    content = f.read()

print(f"Original length: {len(content)}")

# Remove all "_widget": ... entries. 
# They usually look like: "_widget": <something>
# We'll use a lazy match to find the next comma or closing brace
clean_content = re.sub(r'"_widget":\s*<[^>]*>,?', '', content)
# Also handle if it was partially written
clean_content = re.sub(r'"_widget":\s*$', '', clean_content)

print(f"Cleaned length: {len(clean_content)}")

# Now try to close it
found = False
for i in range(len(clean_content), 0, -1):
    candidate = clean_content[:i].strip()
    if candidate.endswith(','):
        candidate = candidate[:-1].strip()
        
    for suffix in ["", "}", "}]", "}]}", "]}", "]]}"]:
        try:
            data = json.loads(candidate + suffix)
            if isinstance(data, dict) and 'library' in data:
                print(f"RESCUE SUCCESS! Recovered at index {i} with suffix '{suffix}'")
                with open(target_path, 'w') as f:
                    json.dump(data, f, indent=4)
                print(f"Rescued {len(data['library'])} items.")
                found = True
                break
        except:
            continue
    if found: break

if not found:
    print("Could not rescue.")
