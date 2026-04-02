"""
Comprehensive Test Suite for Hole Wizard & Tolerance Features
"""
import json
import os
import sys
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:5555"
TEMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")

class TestHoleToleranceFeatures(unittest.TestCase):
    def setUp(self):
        """Ensure we start with a fresh model."""
        self.load_model()

    def post_json(self, endpoint, payload):
        req = Request(f"{BASE}/{endpoint}", 
                      data=json.dumps(payload).encode(), 
                      headers={"Content-Type": "application/json"}, 
                      method="POST")
        return json.loads(urlopen(req).read().decode())

    def get_json(self, endpoint):
        req = Request(f"{BASE}/{endpoint}")
        return json.loads(urlopen(req).read().decode())

    def load_model(self):
        req = Request(f"{BASE}/test_sample", data=b"", headers={"Content-Length": "0"}, method="GET") # GET for sample
        self.data = json.loads(urlopen(req).read().decode())
        
    def get_cylindrical_face_id(self):
        """Helper to find a cylindrical face ID from the model."""
        holes_data = self.get_json("get_holes")
        if not holes_data.get("holes"):
            self.fail("No holes (cylindrical faces) found in sample model")
        
        # Return the first face ID of the first hole group
        # structure: {"holes": [{"diameter": X, "ids": [id1, id2], ...}, ...]}
        return holes_data["holes"][0]["ids"][0]

    def test_01_thread_options(self):
        """Verify thread options structure and content."""
        opts = self.get_json("thread_options")
        self.assertIn("types", opts)
        self.assertIn("UNC (Unified Coarse)", opts["types"])
        self.assertIn("M (ISO Metric)", opts["types"])
        
        # Check sizes for UNC
        unc_sizes = opts["sizes"]["UNC (Unified Coarse)"]
        self.assertIn("1/4-20", unc_sizes)
        self.assertIn("#4-40", unc_sizes)

    def test_02_tolerance_options(self):
        """Verify tolerance options include inch-based values."""
        opts = self.get_json("tolerance_options")
        self.assertIn("types", opts)
        self.assertIn("Linear +/-", opts["types"])
        self.assertIn("Position", opts["types"])
        
        self.assertIn("values", opts)
        # Verify inch values
        self.assertIn("+/- 0.005", opts["values"])
        self.assertIn("0.001 TIR", opts["values"])

    def test_03_set_and_retrieve_thread(self):
        """Set thread data on a face and verify it persists in DB."""
        face_id = self.get_cylindrical_face_id()
        print(f"    [INFO] Using Face #{face_id} for thread test")
        
        thread_data = {
            "type": "UNC (Unified Coarse)",
            "size": "1/4-20",
            "pitch": "20 TPI",
            "class": "2B"
        }
        res = self.post_json("set_thread", {"face_id": face_id, "thread": thread_data})
        self.assertTrue(res.get("ok"))
        self.assertGreater(res.get("db_updated_count"), 0)

    def test_04_set_and_retrieve_tolerance(self):
        """Set tolerance data on a face and verify it persists in DB."""
        # Use face 0 (likely planar) for simple tolerance, or cylinder if desired.
        # Let's use generic face 0 for now as it's stable.
        target_face = 0 
        
        tol_data = {
            "type": "Position",
            "value": "0.005 TIR",
            "datum": "A|B|C"
        }
        res = self.post_json("set_tolerance", {
            "updates": [{"face_id": target_face, "tolerance": tol_data}]
        })
        self.assertTrue(res.get("ok"))
        self.assertGreater(res.get("db_updated_count"), 0)

    def test_05_full_roundtrip(self):
        """
        Full integration test:
        1. Load model
        2. Set Color (Face 0)
        3. Set Thread (Cylindrical Face)
        4. Set Tolerance (Face 0)
        5. Export STEP
        6. Re-upload STEP
        7. Verify all metadata survived
        """
        # 1. Setup
        self.load_model()
        
        # 2. Set Color
        self.post_json("set_color", {"face_id": 0, "color": "#ff00ff"}) # Magenta
        
        # 3. Set Thread
        cyl_face = self.get_cylindrical_face_id()
        thread_data = {"type": "M (ISO Metric)", "size": "M6x1", "pitch": "1.0", "class": "6H"}
        self.post_json("set_thread", {"face_id": cyl_face, "thread": thread_data})
        
        # 4. Set Tolerance
        tol_data = {"type": "Linear +/-", "value": "+/- 0.005", "datum": ""}
        self.post_json("set_tolerance", {"updates": [{"face_id": 0, "tolerance": tol_data}]})
        
        # 5. Export
        export_url = f"{BASE}/export"
        export_path = os.path.join(TEMP, "test_suite_export.step")
        if not os.path.exists(TEMP): os.makedirs(TEMP)
        
        with urlopen(export_url) as resp, open(export_path, "wb") as f:
            f.write(resp.read())
            
        self.assertTrue(os.path.exists(export_path))
        self.assertGreater(os.path.getsize(export_path), 1000)
        
        # 6. Re-upload
        boundary = "----TestBoundary"
        with open(export_path, "rb") as f:
            file_data = f.read()
            
        print(f"    [INFO] Export size: {len(file_data)} bytes")
        print(f"    [INFO] Header: {file_data[:80]}")

        body = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"test_suite_export.step\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
        
        req = Request(f"{BASE}/upload", data=body, 
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, 
                      method="POST")
        try:
            data = json.loads(urlopen(req).read().decode())
        except HTTPError as e:
            print(f"    [ERROR] Upload failed: {e.read().decode()}")
            raise
        
        # 7. Verify
        faces = data["faces"]
        
        # Check Face 0 (Color + Tolerance)
        # Note: Face IDs *should* remain stable if geometry is identical and order preserved.
        f0 = next((f for f in faces if f["id"] == 0), None)
        self.assertIsNotNone(f0, "Face 0 not found after reload")
        self.assertEqual(f0["color"], "#ff00ff", "Color failed roundtrip")
        
        self.assertIsNotNone(f0.get("tolerance"), "Tolerance data lost on face 0")
        self.assertEqual(f0["tolerance"]["type"], tol_data["type"])
        
        # Check Cylindrical Face (Thread)
        # We need to find the face again (ID might stay same, let's assume so for XDE -> XDE)
        # If IDs shift, we'd need to find via geometric match, but that's complex. 
        # For this test with sample.STEP, we assume stability.
        f_cyl = next((f for f in faces if f["id"] == cyl_face), None)
        self.assertIsNotNone(f_cyl, f"Cylindrical face {cyl_face} not found after reload")
        
        self.assertIsNotNone(f_cyl.get("thread"), "Thread data lost")
        self.assertEqual(f_cyl["thread"]["type"], thread_data["type"])
        
        print("\n[SUCCESS] Full round-trip test passed: Color, Thread, and Tolerance metadata preserved.")
        
        # Cleanup
        try: os.remove(export_path)
        except: pass

if __name__ == "__main__":
    unittest.main()
