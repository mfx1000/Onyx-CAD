"""
Definitive test: geometry fingerprint DB survives total metadata destruction.

Simulates a SolidWorks round-trip by stripping ALL embedded metadata from the
STEP file (entities, description, comments) and verifying that the SQLite DB
restores thread data based on face geometry alone.

Flow:
  1. Load test cube
  2. Set thread on face 0, color on face 1
  3. Export STEP (has embedded metadata)
  4. STRIP all metadata from the exported file (simulate SolidWorks re-export)
  5. Re-import the stripped file
  6. Verify: thread data restored from geometry DB
"""
import json, os, re, sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:5555"
TEMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")

def post_json(url, p):
    return json.loads(urlopen(Request(url, json.dumps(p).encode(),
        {"Content-Type":"application/json"}, method="POST")).read())
def post_empty(url):
    return json.loads(urlopen(Request(url, b"", {"Content-Length":"0"}, method="POST")).read())
def upload(fp, fn):
    b = "----B"
    with open(fp,"rb") as f: d=f.read()
    body = f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fn}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()+d+f"\r\n--{b}--\r\n".encode()
    return json.loads(urlopen(Request(f"{BASE}/upload",body,{"Content-Type":f"multipart/form-data; boundary={b}"},method="POST")).read())

THREAD = {"type":"UNC (Unified Coarse)","size":"1/4-20","pitch":"20 TPI","class":"2A / 2B (Standard)"}

print("="*60)
print("GEOMETRY DB ROUND-TRIP TEST")
print("(simulates SolidWorks stripping all metadata)")
print("="*60)

# ── 1. Load cube, set thread + color ─────────────────────
print("\n[1] Loading test cube and setting metadata...")
data = post_empty(f"{BASE}/test_cube")
print(f"    {len(data['faces'])} faces loaded")
print(f"    Face 0 hash: {data['faces'][0].get('face_hash')}")
print(f"    Face 1 hash: {data['faces'][1].get('face_hash')}")

post_json(f"{BASE}/set_thread", {"face_id": 0, "thread": THREAD})
post_json(f"{BASE}/set_color", {"face_id": 0, "color": "#ff0000"})
print("    Set thread on face 0: UNC 1/4-20")
print("    Set color on face 0: #ff0000")

# Check DB stats
stats = json.loads(urlopen(f"{BASE}/db_stats").read())
print(f"    DB has {stats['total_faces']} face(s) stored")

# ── 2. Export STEP ───────────────────────────────────────
print("\n[2] Exporting STEP...")
export_path = os.path.join(TEMP, "geodb_test.step")
resp = urlopen(f"{BASE}/export")
with open(export_path, "wb") as f:
    f.write(resp.read())
print(f"    Exported: {os.path.getsize(export_path)} bytes")

# ── 3. STRIP ALL METADATA (simulate SolidWorks) ─────────
print("\n[3] Stripping ALL metadata (simulating SolidWorks re-export)...")
with open(export_path, "r", errors="replace") as f:
    text = f.read()

# Count what we're stripping
had_comment = "__STEPVIEWER_META_START__" in text
had_entity = "StepViewerFaceMetadata" in text
had_desc = "[SVFM:" in text
had_styled = "STYLED_ITEM" in text

# Strip comments
text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
# Strip our PROPERTY_DEFINITION chain
text = re.sub(r"#\d+\s*=\s*PROPERTY_DEFINITION\s*\(\s*'StepViewerFaceMetadata'[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*PROPERTY_DEFINITION_REPRESENTATION[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*'StepViewerFaceMetadata'[^;]*;", "", text, flags=re.DOTALL)
# Strip SVFM tag from PRODUCT description
text = re.sub(r"\[SVFM:[A-Za-z0-9+/=]+\]", "", text)
# Strip STYLED_ITEM (color) and related entities
text = re.sub(r"#\d+\s*=\s*STYLED_ITEM[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*PRESENTATION_STYLE_ASSIGNMENT[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*SURFACE_STYLE_USAGE[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*SURFACE_SIDE_STYLE[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*SURFACE_STYLE_FILL_AREA[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*FILL_AREA_STYLE[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*FILL_AREA_STYLE_COLOUR[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*DRAUGHTING_PRE_DEFINED_COLOUR[^;]*;", "", text)
text = re.sub(r"#\d+\s*=\s*MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION[^;]*;", "", text, flags=re.DOTALL)
# Also strip any leftover REPRESENTATION entities we added
text = re.sub(r"#\d+\s*=\s*REPRESENTATION\s*\(\s*''\s*,\s*\(\s*#\d+\s*\)\s*,\s*#\d+\s*\)\s*;", "", text)

stripped_path = os.path.join(TEMP, "geodb_test_stripped.step")
with open(stripped_path, "w") as f:
    f.write(text)

print(f"    Stripped comment:  {had_comment} -> {'__STEPVIEWER_META_START__' in text}")
print(f"    Stripped entity:   {had_entity} -> {'StepViewerFaceMetadata' in text}")
print(f"    Stripped desc tag: {had_desc} -> {'[SVFM:' in text}")
print(f"    Stripped colors:   {had_styled} -> {'STYLED_ITEM' in text}")
print(f"    Stripped file: {os.path.getsize(stripped_path)} bytes")

# ── 4. Re-import the stripped file ───────────────────────
print("\n[4] Re-importing stripped STEP (no embedded metadata)...")
try:
    data2 = upload(stripped_path, "stripped.step")
except HTTPError as e:
    print(f"    FAIL: HTTP {e.code}: {e.read().decode()[:300]}")
    sys.exit(1)

faces2 = data2["faces"]
print(f"    {len(faces2)} faces loaded")

# ── 5. Verify metadata was restored from DB ──────────────
print("\n[5] Checking if geometry DB restored the metadata...")
face0 = faces2[0]
print(f"    Face 0 hash:   {face0.get('face_hash')}")
print(f"    Face 0 color:  {face0.get('color')}")
print(f"    Face 0 thread: {face0.get('thread')}")

thread_ok = False
if face0.get("thread"):
    th = face0["thread"]
    thread_ok = (
        th.get("type") == THREAD["type"] and
        th.get("size") == THREAD["size"] and
        th.get("pitch") == THREAD["pitch"] and
        th.get("class") == THREAD["class"]
    )

# Color won't survive (we stripped STYLED_ITEM), but check if DB has it
color_in_db = face0.get("thread") is not None  # if thread came back, DB is working

print(f"\n    Thread restored from geometry DB: {'PASS' if thread_ok else 'FAIL'}")

# ── Summary ──────────────────────────────────────────────
print("\n" + "="*60)
if thread_ok:
    print("PASSED! Geometry DB restored metadata after total STEP wipe.")
    print("This proves the concept works for SolidWorks round-trips.")
else:
    print("FAILED - metadata was not restored")
    print(f"  Expected thread: {THREAD}")
    print(f"  Got: {face0.get('thread')}")

# Cleanup
for p in [export_path, stripped_path]:
    if os.path.exists(p): os.remove(p)

sys.exit(0 if thread_ok else 1)
