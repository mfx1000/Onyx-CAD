"""
Roundtrip test: thread metadata must survive STEP export + reimport.

Flow:
  1. POST /test_cube         -> load a cube
  2. POST /set_thread        -> set thread on face 0
  3. POST /set_color          -> set color on face 0
  4. GET  /export             -> download colored+threaded STEP
  5. Inspect the STEP file for our metadata comment
  6. POST /upload             -> re-upload the exported file
  7. Verify: face 0 has both color AND thread data
"""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:5555"
TEMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")

def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urlopen(req).read().decode())

def post_empty(url):
    req = Request(url, data=b"", headers={"Content-Length": "0"}, method="POST")
    return json.loads(urlopen(req).read().decode())

def multipart_upload(filepath, filename):
    boundary = "----TestBoundary999"
    with open(filepath, "rb") as f:
        file_data = f.read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    req = Request(f"{BASE}/upload", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    return json.loads(urlopen(req).read().decode())


print("=" * 60)
print("METADATA ROUND-TRIP TEST")
print("=" * 60)

# ── 1. Load test cube ──────────────────────────────────────
print("\n[1] Loading test cube...")
data = post_empty(f"{BASE}/test_cube")
assert len(data["faces"]) == 6, f"Expected 6 faces, got {len(data['faces'])}"
print(f"    OK: {len(data['faces'])} faces, no thread data initially")

# ── 2. Set thread on face 0 ────────────────────────────────
THREAD = {
    "type": "UNC (Unified Coarse)",
    "size": "1/4-20",
    "pitch": "20 TPI",
    "class": "2A / 2B (Standard)",
}
print(f"\n[2] Setting thread on face 0: {THREAD}")
result = post_json(f"{BASE}/set_thread", {"face_id": 0, "thread": THREAD})
assert result.get("ok"), f"set_thread failed: {result}"
print("    OK")

# ── 3. Set color on face 0 ─────────────────────────────────
print("\n[3] Setting color on face 0: #ff0000")
result = post_json(f"{BASE}/set_color", {"face_id": 0, "color": "#ff0000"})
assert result.get("ok"), f"set_color failed: {result}"
print("    OK")

# ── 4. Export ───────────────────────────────────────────────
export_path = os.path.join(TEMP, "meta_roundtrip.step")
print(f"\n[4] Exporting STEP to {export_path}...")
resp = urlopen(f"{BASE}/export")
with open(export_path, "wb") as f:
    f.write(resp.read())
size = os.path.getsize(export_path)
print(f"    OK: {size} bytes")

# ── 5. Inspect the STEP file ───────────────────────────────
print("\n[5] Inspecting STEP file for metadata...")
with open(export_path, "r", errors="replace") as f:
    content = f.read()

has_styled = "STYLED_ITEM" in content
has_meta_marker = "__STEPVIEWER_META_START__" in content
print(f"    Has STYLED_ITEM (color): {has_styled}")
print(f"    Has metadata comment:    {has_meta_marker}")

if has_meta_marker:
    import re
    m = re.search(r"__STEPVIEWER_META_START__ (.*?) __STEPVIEWER_META_END__", content, re.DOTALL)
    if m:
        embedded = json.loads(m.group(1))
        print(f"    Embedded JSON: {json.dumps(embedded, indent=2)}")
        assert "face_meta" in embedded, "Missing face_meta key"
        assert "0" in embedded["face_meta"], "Missing face 0 in face_meta"
        face0_meta = embedded["face_meta"]["0"]
        assert "thread" in face0_meta, "Missing thread data for face 0"
        assert face0_meta["thread"]["type"] == THREAD["type"], f"Thread type mismatch"
        assert face0_meta["thread"]["size"] == THREAD["size"], f"Thread size mismatch"
        assert face0_meta["thread"]["pitch"] == THREAD["pitch"], f"Thread pitch mismatch"
        print("    Embedded metadata is CORRECT")
    else:
        print("    ERROR: Could not extract metadata JSON")
        sys.exit(1)
else:
    print("    FAIL: No metadata found in STEP file!")
    sys.exit(1)

# ── 6. Re-upload the exported file ──────────────────────────
print(f"\n[6] Re-uploading {export_path}...")
try:
    data2 = multipart_upload(export_path, "meta_roundtrip.step")
except HTTPError as e:
    print(f"    FAIL: HTTP {e.code}: {e.read().decode()[:500]}")
    sys.exit(1)

faces2 = data2["faces"]
print(f"    OK: {len(faces2)} faces returned")

# ── 7. Verify face 0 has both color AND thread ─────────────
print("\n[7] Verifying face 0 after round-trip...")
face0 = faces2[0]
print(f"    Color:  {face0.get('color')}")
print(f"    Thread: {face0.get('thread')}")

color_ok = face0.get("color") == "#ff0000"
thread_ok = face0.get("thread") is not None
if thread_ok:
    th = face0["thread"]
    thread_ok = (
        th.get("type") == THREAD["type"] and
        th.get("size") == THREAD["size"] and
        th.get("pitch") == THREAD["pitch"] and
        th.get("class") == THREAD["class"]
    )

print(f"\n    Color survived:  {'PASS' if color_ok else 'FAIL'}")
print(f"    Thread survived: {'PASS' if thread_ok else 'FAIL'}")

# ── Summary ─────────────────────────────────────────────────
print("\n" + "=" * 60)
if color_ok and thread_ok:
    print("ALL TESTS PASSED - metadata round-trip works!")
else:
    print("TESTS FAILED")
    if not color_ok:
        print(f"  Color: expected #ff0000, got {face0.get('color')}")
    if not thread_ok:
        print(f"  Thread: expected {THREAD}, got {face0.get('thread')}")

# Cleanup
os.remove(export_path)
print(f"\nCleaned up {export_path}")

sys.exit(0 if (color_ok and thread_ok) else 1)
