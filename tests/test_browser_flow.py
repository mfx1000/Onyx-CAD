"""
Simulate the exact browser workflow via HTTP to find where color gets lost.

Flow:
  1. POST /test_cube  (boot test — loads the cube)
  2. POST /set_color   (user picks red for face 0)
  3. GET  /export      (user downloads colored STEP)
  4. POST /upload      (user re-uploads the colored STEP)
  5. Check: does the JSON response have color on face 0?
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
    resp = urlopen(req)
    return json.loads(resp.read().decode())

def post_empty(url):
    req = Request(url, data=b"", headers={"Content-Length": "0"}, method="POST")
    resp = urlopen(req)
    return json.loads(resp.read().decode())

def multipart_upload(filepath, filename):
    boundary = "----TestBoundary789"
    with open(filepath, "rb") as f:
        file_data = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    req = Request(
        f"{BASE}/upload", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    resp = urlopen(req)
    return json.loads(resp.read().decode())


print("=" * 60)
print("BROWSER FLOW SIMULATION")
print("=" * 60)

# ── Step 1: Boot test cube ────────────────────────────────────────
print("\n[1] POST /test_cube (simulates page load boot test)...")
try:
    data = post_empty(f"{BASE}/test_cube")
    faces = data["faces"]
    print(f"    Got {len(faces)} faces")
    for f in faces:
        print(f"    Face {f['id']}: color={f['color'] or 'none'}")
except HTTPError as e:
    print(f"    FAILED: HTTP {e.code}: {e.read().decode()[:300]}")
    sys.exit(1)

# ── Step 2: Set color on face 0 ──────────────────────────────────
print("\n[2] POST /set_color face_id=0 color=#ff0000...")
try:
    result = post_json(f"{BASE}/set_color", {"face_id": 0, "color": "#ff0000"})
    print(f"    Result: {result}")
except HTTPError as e:
    print(f"    FAILED: HTTP {e.code}: {e.read().decode()[:300]}")
    sys.exit(1)

# ── Step 3: Export ────────────────────────────────────────────────
print("\n[3] GET /export (download colored STEP)...")
export_path = os.path.join(TEMP, "browser_flow_export.step")
try:
    resp = urlopen(f"{BASE}/export")
    with open(export_path, "wb") as f:
        f.write(resp.read())
    print(f"    Saved: {export_path} ({os.path.getsize(export_path)} bytes)")
except HTTPError as e:
    print(f"    FAILED: HTTP {e.code}: {e.read().decode()[:300]}")
    sys.exit(1)

# Check if the exported file has color entities
with open(export_path, "r", errors="replace") as f:
    content = f.read()
has_styled = "STYLED_ITEM" in content
has_colour = "COLOUR" in content or "COLOR" in content
print(f"    STEP has STYLED_ITEM: {has_styled}")
print(f"    STEP has COLOUR/COLOR: {has_colour}")

# ── Step 4: Re-upload the exported file ───────────────────────────
print("\n[4] POST /upload (re-upload the colored STEP)...")
try:
    data2 = multipart_upload(export_path, "test_cube_colored.step")
    faces2 = data2["faces"]
    print(f"    Got {len(faces2)} faces")
    for f in faces2:
        print(f"    Face {f['id']}: color={f['color'] or 'none'}")
except HTTPError as e:
    print(f"    FAILED: HTTP {e.code}: {e.read().decode()[:300]}")
    sys.exit(1)

# ── Step 5: Verdict ───────────────────────────────────────────────
print("\n" + "=" * 60)
colored_faces = [f for f in faces2 if f["color"]]
if colored_faces:
    print(f"PASS: {len(colored_faces)} face(s) have color after round-trip:")
    for f in colored_faces:
        print(f"  Face {f['id']}: {f['color']}")
else:
    print("FAIL: NO faces have color after round-trip!")
    print("\nDebugging: Let's check if set_color actually persisted...")
    # Re-export without re-uploading to check current state
    print("  (The re-upload replaced the model state, so we can't check now)")
    print("  The STEP file should have had colors — check the STYLED_ITEM above")

# Cleanup
os.remove(export_path)
print(f"\nCleaned up {export_path}")
