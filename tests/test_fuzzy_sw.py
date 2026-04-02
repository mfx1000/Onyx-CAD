"""
Test fuzzy matching: set metadata on OCC cube, then load SolidWorks cube.
The hashes will differ (different kernel) but fuzzy match should restore metadata.
"""
import json, os, sys
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:5555"
TEMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")
SW_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "cube_solidworks.step")

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

THREAD = {"type":"M (ISO Metric)","size":"M10","pitch":"1.5","class":"6g / 6H (ISO Medium)"}

print("="*60)
print("FUZZY MATCH TEST: OCC -> SolidWorks round-trip")
print("="*60)

# 1. Load OCC test cube, set thread on face 0
print("\n[1] Loading OCC test cube...")
data1 = post_empty(f"{BASE}/test_cube")
print(f"    {len(data1['faces'])} faces, face 0 hash: {data1['faces'][0]['face_hash']}")

print("\n[2] Setting thread on face 0...")
post_json(f"{BASE}/set_thread", {"face_id": 0, "thread": THREAD})
print(f"    Thread: {THREAD['type']} {THREAD['size']}")

stats = json.loads(urlopen(f"{BASE}/db_stats").read())
print(f"    DB has {stats['total_faces']} stored faces")

# 2. Now load the SolidWorks-exported cube
print(f"\n[3] Loading SolidWorks cube: {SW_FILE}")
data2 = upload(SW_FILE, "cube export 4.STEP")
print(f"    {len(data2['faces'])} faces")

# 3. Check each face for restored metadata
print("\n[4] Checking for restored metadata...")
found_thread = False
for f in data2["faces"]:
    th = f.get("thread")
    if th:
        found_thread = True
        print(f"    Face {f['id']} (hash {f['face_hash']}): RESTORED")
        print(f"      Thread: {th['type']} {th['size']} {th['pitch']} {th['class']}")
        ok = (th["type"] == THREAD["type"] and th["size"] == THREAD["size"])
        print(f"      Correct: {'YES' if ok else 'NO'}")
    else:
        print(f"    Face {f['id']} (hash {f['face_hash']}): no metadata")

print("\n" + "="*60)
if found_thread:
    print("PASSED - Fuzzy match restored metadata from SolidWorks file!")
else:
    print("FAILED - No metadata restored")

sys.exit(0 if found_thread else 1)
