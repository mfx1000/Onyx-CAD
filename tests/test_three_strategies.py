"""
Verify all three metadata embedding strategies are present in the STEP file,
and that each one can independently recover the data (simulating different
CAD tools stripping different things).
"""
import base64, json, os, re, sys
from urllib.request import Request, urlopen

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

THREAD = {"type":"M (ISO Metric)","size":"M12","pitch":"1.75","class":"6g / 6H (ISO Medium)"}

print("="*60)
print("THREE-STRATEGY EMBEDDING TEST")
print("="*60)

# Setup: load cube, set thread, export
post_empty(f"{BASE}/test_cube")
post_json(f"{BASE}/set_thread", {"face_id":0, "thread":THREAD})
post_json(f"{BASE}/set_color", {"face_id":0, "color":"#0000ff"})

path = os.path.join(TEMP, "three_strat.step")
with open(path,"wb") as f: f.write(urlopen(f"{BASE}/export").read())
with open(path,"r",errors="replace") as f: text = f.read()

print(f"\nFile: {os.path.getsize(path)} bytes")

# ── Check all three strategies are present ───────────────────
print("\n--- Strategy presence ---")

# 1. PROPERTY_DEFINITION → PRODUCT_DEFINITION (not _SHAPE!)
has_pd = bool(re.search(r"PROPERTY_DEFINITION\s*\(\s*'StepViewerFaceMetadata'\s*,\s*''\s*,\s*#(\d+)", text))
# Verify it points to PRODUCT_DEFINITION, not PRODUCT_DEFINITION_SHAPE
pd_ref_match = re.search(r"PROPERTY_DEFINITION\s*\(\s*'StepViewerFaceMetadata'\s*,\s*''\s*,\s*#(\d+)", text)
if pd_ref_match:
    ref_id = pd_ref_match.group(1)
    # Check what entity that ID points to
    ref_entity = re.search(rf"#{ref_id}\s*=\s*(\w+)", text)
    ref_type = ref_entity.group(1) if ref_entity else "???"
    print(f"  1. PROPERTY_DEFINITION -> #{ref_id} = {ref_type}: {'CORRECT' if ref_type=='PRODUCT_DEFINITION' else 'WRONG (should be PRODUCT_DEFINITION)'}")
else:
    print(f"  1. PROPERTY_DEFINITION: MISSING")

# 2. PRODUCT description
desc_match = re.search(r"\[SVFM:([A-Za-z0-9+/=]+)\]", text)
has_desc = bool(desc_match)
print(f"  2. PRODUCT description [SVFM:...]: {has_desc}")
if has_desc:
    # Show context
    prod_line = [l for l in text.split("\n") if "SVFM:" in l]
    if prod_line:
        print(f"     Line: {prod_line[0].strip()[:100]}...")

# 3. Comment
has_comment = "__STEPVIEWER_META_START__" in text
print(f"  3. Comment block: {has_comment}")

# 4. DESCRIPTIVE_REPRESENTATION_ITEM
dri_match = re.search(r"DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*'StepViewerFaceMetadata'\s*,\s*\n?\s*'([^']*)'\s*\)", text, re.DOTALL)
has_dri = bool(dri_match)
print(f"  4. DESCRIPTIVE_REPRESENTATION_ITEM: {has_dri}")

# ── Test each strategy independently ─────────────────────────
print("\n--- Independent extraction tests ---")

def decode_b64(s):
    return json.loads(base64.b64decode(s).decode())

# Test 1: Strip comment + description, keep only entities
text_1 = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)  # strip comments
text_1 = re.sub(r"\[SVFM:[A-Za-z0-9+/=]+\]", "", text_1)  # strip desc tag
p1 = os.path.join(TEMP, "strat1_entity_only.step")
with open(p1,"w") as f: f.write(text_1)
d1 = upload(p1, "strat1.step")
t1 = d1["faces"][0].get("thread")
ok1 = t1 and t1["size"] == "M12"
print(f"  Entity-only:      thread={t1 and t1.get('size')} {'PASS' if ok1 else 'FAIL'}")

# Test 2: Strip entities + comment, keep only description
text_2 = text
# Remove the PROPERTY_DEFINITION chain (our 4 entities at the end)
text_2 = re.sub(r"#\d+\s*=\s*PROPERTY_DEFINITION\s*\(\s*'StepViewerFaceMetadata'[^;]*;", "", text_2)
text_2 = re.sub(r"#\d+\s*=\s*DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*'StepViewerFaceMetadata'[^;]*;", "", text_2, flags=re.DOTALL)
text_2 = re.sub(r"#\d+\s*=\s*PROPERTY_DEFINITION_REPRESENTATION[^;]*;", "", text_2)
# Also strip comment
text_2 = re.sub(r"/\*.*?\*/", "", text_2, flags=re.DOTALL)
p2 = os.path.join(TEMP, "strat2_desc_only.step")
with open(p2,"w") as f: f.write(text_2)
d2 = upload(p2, "strat2.step")
t2 = d2["faces"][0].get("thread")
ok2 = t2 and t2["size"] == "M12"
print(f"  Description-only: thread={t2 and t2.get('size')} {'PASS' if ok2 else 'FAIL'}")

# Test 3: Strip entities + description, keep only comment
text_3 = text
text_3 = re.sub(r"#\d+\s*=\s*PROPERTY_DEFINITION\s*\(\s*'StepViewerFaceMetadata'[^;]*;", "", text_3)
text_3 = re.sub(r"#\d+\s*=\s*DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*'StepViewerFaceMetadata'[^;]*;", "", text_3, flags=re.DOTALL)
text_3 = re.sub(r"#\d+\s*=\s*PROPERTY_DEFINITION_REPRESENTATION[^;]*;", "", text_3)
text_3 = re.sub(r"\[SVFM:[A-Za-z0-9+/=]+\]", "", text_3)
p3 = os.path.join(TEMP, "strat3_comment_only.step")
with open(p3,"w") as f: f.write(text_3)
d3 = upload(p3, "strat3.step")
t3 = d3["faces"][0].get("thread")
ok3 = t3 and t3["size"] == "M12"
print(f"  Comment-only:     thread={t3 and t3.get('size')} {'PASS' if ok3 else 'FAIL'}")

# Cleanup
for p in [path, p1, p2, p3]:
    if os.path.exists(p): os.remove(p)

print("\n" + "="*60)
all_ok = ok1 and ok2 and ok3 and has_pd and has_desc and has_comment
print(f"{'ALL PASSED' if all_ok else 'SOME FAILED'}")
print(f"  Entity extraction:      {'PASS' if ok1 else 'FAIL'}")
print(f"  Description extraction: {'PASS' if ok2 else 'FAIL'}")
print(f"  Comment extraction:     {'PASS' if ok3 else 'FAIL'}")
print(f"  PROPERTY_DEF -> PRODUCT_DEFINITION: {'YES' if ref_type=='PRODUCT_DEFINITION' else 'NO'}")
sys.exit(0 if all_ok else 1)
