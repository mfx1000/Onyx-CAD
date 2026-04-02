"""
Verify that metadata is embedded as REAL STEP entities, not just comments.
Inspect the STEP DATA section for PROPERTY_DEFINITION chain + SVFM payload.
Also test that the entity-based extraction works independently of the comment.
"""
import base64
import json
import os
import re
import sys
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:5555"
TEMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")

def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urlopen(req).read().decode())

def post_empty(url):
    req = Request(url, data=b"", headers={"Content-Length": "0"}, method="POST")
    return json.loads(urlopen(req).read().decode())


print("=" * 60)
print("STEP ENTITY EMBEDDING VERIFICATION")
print("=" * 60)

# Load cube, set thread + color, export
post_empty(f"{BASE}/test_cube")
post_json(f"{BASE}/set_thread", {
    "face_id": 0,
    "thread": {"type": "M (ISO Metric)", "size": "M10", "pitch": "1.5", "class": "6g / 6H (ISO Medium)"}
})
post_json(f"{BASE}/set_color", {"face_id": 0, "color": "#00ff00"})

export_path = os.path.join(TEMP, "entity_test.step")
resp = urlopen(f"{BASE}/export")
with open(export_path, "wb") as f:
    f.write(resp.read())

with open(export_path, "r", errors="replace") as f:
    content = f.read()

print(f"\nFile size: {os.path.getsize(export_path)} bytes")

# ── Check for STEP entities ──────────────────────────────────────
print("\n--- STEP Entity Checks ---")

has_prop_def = "PROPERTY_DEFINITION('StepViewerFaceMetadata'" in content
has_prop_rep = "PROPERTY_DEFINITION_REPRESENTATION" in content
has_dri = "DESCRIPTIVE_REPRESENTATION_ITEM('SVFM'" in content or "DESCRIPTIVE_REPRESENTATION_ITEM('StepViewerFaceMetadata'" in content
has_comment = "__STEPVIEWER_META_START__" in content
has_styled = "STYLED_ITEM" in content

print(f"  PROPERTY_DEFINITION('StepViewerFaceMetadata'):    {has_prop_def}")
print(f"  PROPERTY_DEFINITION_REPRESENTATION:                {has_prop_rep}")
print(f"  DESCRIPTIVE_REPRESENTATION_ITEM('SVFM'):           {has_dri}")
print(f"  Comment block (fallback):                          {has_comment}")
print(f"  STYLED_ITEM (color):                               {has_styled}")

# ── Extract and decode the base64 payload from the STEP entity ───
print("\n--- Entity Payload Extraction ---")
dri_match = re.search(
    r"DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*'(?:SVFM|StepViewerFaceMetadata)'\s*,\s*\n?\s*'([^']*)'\s*\)",
    content, re.DOTALL,
)
if dri_match:
    b64 = dri_match.group(1).strip()
    decoded = base64.b64decode(b64).decode("utf-8")
    meta = json.loads(decoded)
    print(f"  Base64 length: {len(b64)} chars")
    print(f"  Decoded JSON:  {json.dumps(meta, indent=2)}")

    # Verify content
    assert "face_meta" in meta
    assert "0" in meta["face_meta"]
    th = meta["face_meta"]["0"]["thread"]
    assert th["type"] == "M (ISO Metric)"
    assert th["size"] == "M10"
    assert th["pitch"] == "1.5"
    assert th["class"] == "6g / 6H (ISO Medium)"
    print("  Content verification: PASS")
else:
    print("  FAIL: Could not find SVFM entity in STEP data!")
    sys.exit(1)

# ── Show the actual STEP entity lines ────────────────────────────
print("\n--- Relevant STEP Entity Lines ---")
for line in content.split("\n"):
    line_s = line.strip()
    if any(kw in line_s for kw in [
        "StepViewerFaceMetadata", "SVFM", "PROPERTY_DEFINITION",
        "DESCRIPTIVE_REPRESENTATION_ITEM",
    ]):
        print(f"  {line_s[:120]}")

# ── Test: strip the comment and verify entity extraction still works ──
print("\n--- Comment-stripped extraction test ---")
stripped = re.sub(r"/\* __STEPVIEWER_META_START__.*?__STEPVIEWER_META_END__ \*/", "", content, flags=re.DOTALL)
assert "__STEPVIEWER_META_START__" not in stripped, "Comment wasn't stripped"

# Save stripped version and try to extract via our import path
stripped_path = os.path.join(TEMP, "entity_test_no_comment.step")
with open(stripped_path, "w") as f:
    f.write(stripped)

# Use the same extraction logic from app.py
dri_match2 = re.search(
    r"DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*'(?:SVFM|StepViewerFaceMetadata)'\s*,\s*'([^']*)'\s*\)",
    stripped, re.DOTALL,
)
if dri_match2:
    b64_2 = dri_match2.group(1).strip()
    decoded_2 = base64.b64decode(b64_2).decode("utf-8")
    meta_2 = json.loads(decoded_2)
    print(f"  Entity extraction WITHOUT comment: PASS")
    print(f"  Decoded: {json.dumps(meta_2, indent=2)}")
else:
    print("  FAIL: Entity extraction failed without comment!")
    sys.exit(1)

# Cleanup
os.remove(export_path)
os.remove(stripped_path)

print("\n" + "=" * 60)
all_ok = has_prop_def and has_prop_rep and has_dri and has_comment and has_styled
print(f"ALL CHECKS {'PASSED' if all_ok else 'FAILED'}")
print(f"  Entities: {'OK' if (has_prop_def and has_dri) else 'MISSING'}")
print(f"  Comment:  {'OK' if has_comment else 'MISSING'}")
print(f"  Color:    {'OK' if has_styled else 'MISSING'}")
sys.exit(0 if all_ok else 1)
