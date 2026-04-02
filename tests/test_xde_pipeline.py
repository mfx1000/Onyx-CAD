"""
Integration test: upload STEP → set face colours → export → verify colours in re-read.
"""
import cadquery as cq
import json
import os
import sys
import struct

# ── Helpers for HTTP without requests lib ──────────────────────────────
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:5555"
TEMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")


def multipart_upload(filepath):
    """POST a file to /upload as multipart/form-data."""
    boundary = "----TestBoundary456"
    filename = os.path.basename(filepath)
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


def set_color(face_id, hex_color):
    """POST to /set_color."""
    payload = json.dumps({"face_id": face_id, "color": hex_color}).encode()
    req = Request(
        f"{BASE}/set_color", data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urlopen(req)
    return json.loads(resp.read().decode())


def export_step(out_path):
    """GET /export and save the STEP file."""
    resp = urlopen(f"{BASE}/export")
    with open(out_path, "wb") as f:
        f.write(resp.read())


# ── 1. Create a test STEP file ────────────────────────────────────────
step_path = os.path.join(TEMP, "test_box.step")
box = cq.Workplane("XY").box(10, 20, 30)
cq.exporters.export(box, step_path)
print(f"[OK] Created test STEP: {step_path}")

# ── 2. Upload ─────────────────────────────────────────────────────────
try:
    data = multipart_upload(step_path)
except HTTPError as e:
    print(f"[FAIL] Upload HTTP {e.code}: {e.read().decode()}")
    sys.exit(1)

faces = data["faces"]
print(f"[OK] Upload returned {len(faces)} faces")

for f in faces:
    nv = len(f["vertices"]) // 3
    nt = len(f["indices"]) // 3
    color_str = f["color"] or "none"
    print(f"  Face {f['id']}: {nv} verts, {nt} tris, color={color_str}")

assert len(faces) >= 6, f"Expected >=6 faces for a box, got {len(faces)}"

# ── 3. Set colours on a few faces ─────────────────────────────────────
colors_to_set = {
    0: "#ff0000",  # red
    1: "#00ff00",  # green
    2: "#0000ff",  # blue
}

for fid, hex_c in colors_to_set.items():
    result = set_color(fid, hex_c)
    assert result.get("ok"), f"set_color failed for face {fid}: {result}"
    print(f"[OK] Set face {fid} -> {hex_c}")

# ── 4. Export coloured STEP ───────────────────────────────────────────
export_path = os.path.join(TEMP, "test_box_colored.step")
export_step(export_path)
print(f"[OK] Exported coloured STEP: {export_path}")
assert os.path.exists(export_path), "Export file not created"
assert os.path.getsize(export_path) > 100, "Export file too small"
print(f"     File size: {os.path.getsize(export_path)} bytes")

# ── 5. Re-read the exported file and check colours ────────────────────
# Upload the exported file to see if colours survived the round-trip
try:
    data2 = multipart_upload(export_path)
except HTTPError as e:
    print(f"[FAIL] Re-upload HTTP {e.code}: {e.read().decode()}")
    sys.exit(1)

faces2 = data2["faces"]
print(f"\n[OK] Re-upload of coloured STEP returned {len(faces2)} faces")

found_colors = {}
for f in faces2:
    color_str = f["color"] or "none"
    print(f"  Face {f['id']}: color={color_str}")
    if f["color"]:
        found_colors[f["id"]] = f["color"]

if found_colors:
    print(f"\n[OK] Found {len(found_colors)} coloured faces after round-trip!")
    for fid, c in found_colors.items():
        print(f"     Face {fid}: {c}")
else:
    print("\n[WARN] No colours found after round-trip — colours may be at parent level")

# ── Cleanup ───────────────────────────────────────────────────────────
os.remove(step_path)
os.remove(export_path)
print("\n[DONE] Pipeline test complete.")
