import json
import os
import sys

bak_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json.bak")
target_path = os.path.expanduser("~/Library/Application Support/Offline Spotify Library/config.json")

with open(bak_path, 'r', errors='ignore') as f:
    content = f.read()

print(f"File length: {len(content)}")

def try_fixing(s):
    # Iteratively try to close brackets
    # Common suffixes for this app's structure:
    # 1. Inside expected_files: ] ] } ] } }
    # 2. Inside tracks: ] } ] } }
    # 3. Inside group: } ] } }
    suffixes = [
        " ] ] } ] } }",
        " ] } ] } }",
        " } ] } }",
        " ] } }",
        " } }",
        " }",
        " ] ] }",
        " ] }",
        " ]"
    ]
    
    # Try from the end working backwards
    for i in range(len(s), 0, -1):
        if s[i-1] not in ['}', ']', ',', ' ', '\n', '"']:
            continue
            
        candidate = s[:i].strip()
        if candidate.endswith(','):
            candidate = candidate[:-1].strip()
            
        for suffix in suffixes:
            try:
                data = json.loads(candidate + suffix)
                if isinstance(data, dict) and 'library' in data:
                    return data, i, suffix
            except:
                continue
                
        if i % 1000 == 0:
            print(f"Checked up to {i}...")
            
    return None, 0, ""

data, index, suffix = try_fixing(content)
if data:
    print(f"RESCUE SUCCESS! Index: {index}, Suffix: {suffix}")
    with open(target_path, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"Rescued {len(data['library'])} root items.")
    # Check if we have items in the group
    if data['library'] and 'items' in data['library'][0]:
        print(f"Group items rescued: {len(data['library'][0]['items'])}")
else:
    print("Could not rescue.")
