"""Quick boot-test: call /test_cube, verify response."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

try:
    req = Request("http://127.0.0.1:5555/test_cube", method="POST",
                  data=b"", headers={"Content-Length": "0"})
    resp = urlopen(req)
    data = json.loads(resp.read().decode())
    faces = data["faces"]
    print(f"[OK] test_cube returned {len(faces)} faces")
    for f in faces:
        nv = len(f["vertices"]) // 3
        nt = len(f["indices"]) // 3
        print(f"  Face {f['id']}: {nv} verts, {nt} tris, color={f['color'] or 'none'}")
    assert len(faces) == 6, f"Expected 6 faces, got {len(faces)}"
    print("[PASS] Boot test cube works")
except HTTPError as e:
    print(f"[FAIL] HTTP {e.code}: {e.read().decode()[:500]}")
except Exception as e:
    print(f"[FAIL] {e}")
