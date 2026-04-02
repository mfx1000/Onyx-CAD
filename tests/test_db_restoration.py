"""
Test that DB-restored colors are properly sent in the upload response.

This tests the fix where fingerprint-matched faces should have their
stored colors returned, not just the STEP file's XDE colors.
"""
import json
import os
import sys
import tempfile

import pytest

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, model, load_step_xcaf
from face_db import save_face_meta, init_db, _get_conn


@pytest.fixture
def client():
    """Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def clean_db():
    """Start with empty face_meta table."""
    conn = _get_conn()
    conn.execute("DELETE FROM face_meta")
    conn.commit()
    conn.close()
    yield
    # Cleanup after test
    conn = _get_conn()
    conn.execute("DELETE FROM face_meta")
    conn.commit()
    conn.close()


def test_db_color_restoration(client, clean_db):
    """
    Test that when a face fingerprint matches in the DB,
    the stored color is returned in the upload response.
    """
    # Step 1: Upload test cube to get face hashes
    resp = client.post('/test_cube')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    faces = data['faces']
    assert len(faces) == 6, "Test cube should have 6 faces"
    
    # Get face hash for face 0
    face_hash = faces[0]['face_hash']
    assert face_hash is not None, "Face hash should be computed"
    
    # Step 2: Save a custom color to DB for this face hash
    test_color = "#ff00ff"
    save_face_meta(face_hash, {"color": test_color}, raw=None)
    
    # Step 3: Reset model state and re-upload test cube
    model.reset()
    resp2 = client.post('/test_cube')
    assert resp2.status_code == 200
    data2 = json.loads(resp2.data)
    faces2 = data2['faces']
    
    # Step 4: Verify the face with matching hash has DB color
    face0 = next(f for f in faces2 if f['face_hash'] == face_hash)
    assert face0['color'] == test_color, \
        f"DB-restored color should be {test_color}, got {face0['color']}"


def test_db_color_priority_over_xde(client, clean_db):
    """
    Test that DB color takes priority over STEP file XDE color.
    """
    # Upload test cube first time
    resp = client.post('/test_cube')
    data = json.loads(resp.data)
    faces = data['faces']
    
    # Pick a face and note its original color (from XDE or default)
    face = faces[0]
    original_color = face['color']
    face_hash = face['face_hash']
    
    # Save different color to DB
    db_color = "#123456"
    save_face_meta(face_hash, {"color": db_color}, raw=None)
    
    # Re-upload
    model.reset()
    resp2 = client.post('/test_cube')
    data2 = json.loads(resp2.data)
    
    # Find same face
    face2 = next(f for f in data2['faces'] if f['face_hash'] == face_hash)
    
    # DB color should win
    assert face2['color'] == db_color, \
        f"DB color {db_color} should override XDE color {original_color}"


def test_thread_metadata_restoration(client, clean_db):
    """
    Test that thread metadata is also restored from DB.
    """
    # Upload test cube
    resp = client.post('/test_cube')
    data = json.loads(resp.data)
    face_hash = data['faces'][0]['face_hash']
    
    # Save thread metadata
    thread_data = {
        "type": "M (ISO Metric)",
        "size": "M6",
        "pitch": "1.0",
        "class": "6g / 6H (ISO Medium)"
    }
    save_face_meta(face_hash, {"thread": thread_data}, raw=None)
    
    # Re-upload
    model.reset()
    resp2 = client.post('/test_cube')
    data2 = json.loads(resp2.data)
    
    face = next(f for f in data2['faces'] if f['face_hash'] == face_hash)
    assert face['thread'] == thread_data, \
        f"Thread metadata should be restored: {face['thread']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
