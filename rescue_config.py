import json
import os
import sys

config_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json")

if not os.path.exists(config_path):
    print("Config file not found.")
    sys.exit(1)

with open(config_path, 'r') as f:
    content = f.read()

print(f"Read {len(content)} characters.")

# Try to find the last valid playlist entry before truncation
# The cat output showed it ended near '"_widget":'
# We'll try to truncate at the last valid dictionary closing '}' that is part of a list entry.

def rescue_json(s):
    # This is a bit brute-force: keep removing characters from the end until it parses
    # or until we reach some minimum.
    for i in range(len(s), 0, -1):
        candidate = s[:i].strip()
        # If it ends with a comma, remove it
        if candidate.endswith(','):
            candidate = candidate[:-1].strip()
            
        # Try appending various closing characters to find a valid sub-structure
        for suffix in ["", "}", "}]", "}]}", "}]}]", "]}", "]} }"]:
            try:
                test = candidate + suffix
                data = json.loads(test)
                print(f"Success! Recovered at length {i} with suffix '{suffix}'")
                return data
            except:
                continue
    return None

data = rescue_json(content)
if data:
    backup_path = config_path + ".bak"
    os.rename(config_path, backup_path)
    with open(config_path, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"Recovered config saved. Original backed up to {backup_path}")
else:
    print("Could not recover JSON.")
