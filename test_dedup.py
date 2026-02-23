import json

def deduplicate_library(items):
    seen_urls = set()
    
    def _proc(lst):
        res = []
        for it in lst:
            if it.get("type") == "group":
                it["items"] = _proc(it.get("items", []))
                res.append(it)
            else:
                url = it.get("url", "")
                if url and url not in seen_urls:
                    res.append(it)
                    seen_urls.add(url)
        return res
        
    return _proc(items)

test_library = [
    {"type": "group", "name": "Swing DJ: Ultimate Pool", "items": [
        {"type": "playlist", "url": "https://open.spotify.com/playlist/78qU0gUvXj6gM8aR9G1a3", "name": "#DJ: Swing - Slow Tempo"},
        {"type": "playlist", "url": "https://open.spotify.com/playlist/123", "name": "Fake"}
    ]},
    {"type": "playlist", "url": "https://open.spotify.com/playlist/78qU0gUvXj6gM8aR9G1a3", "name": "#DJ: Swing - Slow Tempo"}
]

print(json.dumps(deduplicate_library(test_library), indent=2))
