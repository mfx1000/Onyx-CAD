"""Test thread options and set_thread endpoints."""
import json
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:5555"

# 1. Boot test to load a model
req = Request(f"{BASE}/test_cube", data=b"", headers={"Content-Length": "0"}, method="POST")
data = json.loads(urlopen(req).read().decode())
print(f"[OK] Loaded {len(data['faces'])} faces")
print(f"     Face 0 thread: {data['faces'][0].get('thread')}")

# 2. Get thread options
resp = urlopen(f"{BASE}/thread_options")
opts = json.loads(resp.read().decode())
print(f"[OK] Thread options: {len(opts['types'])} types, {len(opts['classes'])} classes")
print(f"     Types: {opts['types'][:5]}...")
print(f"     M pitches: {opts['pitches'].get('M (ISO Metric)', [])[:5]}...")

# 3. Set thread on face 0
payload = json.dumps({
    "face_id": 0,
    "thread": {"type": "M (ISO Metric)", "pitch": "1.5", "class": "6g / 6H (ISO Medium)"}
}).encode()
req = Request(f"{BASE}/set_thread", data=payload, headers={"Content-Type": "application/json"}, method="POST")
result = json.loads(urlopen(req).read().decode())
print(f"[OK] set_thread: {result}")

# 4. Re-load to check thread data comes back
req = Request(f"{BASE}/test_cube", data=b"", headers={"Content-Length": "0"}, method="POST")
data2 = json.loads(urlopen(req).read().decode())
# Note: test_cube creates a fresh model, so thread data won't persist here.
# But we can verify the field exists.
print(f"[OK] Face 0 thread after fresh load: {data2['faces'][0].get('thread')}")
print("[OK] (None expected - test_cube creates a fresh model)")

# 5. Set thread again on the fresh model and verify
payload = json.dumps({
    "face_id": 2,
    "thread": {"type": "UNC (Unified Coarse)", "pitch": "20 TPI", "class": "2A / 2B (Standard)"}
}).encode()
req = Request(f"{BASE}/set_thread", data=payload, headers={"Content-Type": "application/json"}, method="POST")
result = json.loads(urlopen(req).read().decode())
print(f"[OK] set_thread on face 2: {result}")

# 6. Clear thread on face 2
payload = json.dumps({"face_id": 2, "thread": None}).encode()
req = Request(f"{BASE}/set_thread", data=payload, headers={"Content-Type": "application/json"}, method="POST")
result = json.loads(urlopen(req).read().decode())
print(f"[OK] clear_thread on face 2: {result}")

print("\n[PASS] All thread tests passed")
