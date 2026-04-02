"""
Geometry-based face metadata database — Firestore edition.

Each face gets a fingerprint from its geometry (surface type, centroid, area,
bounding box dimensions, edge/vertex counts).  Metadata is stored in the
Firestore ``face_meta`` collection, keyed by ``{model_id}_{face_hash}``.

Storage uses Supabase Storage for the ``step-files`` bucket.
"""

import os
import hashlib
import json
import math

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer

from google.cloud.firestore_v1.base_query import FieldFilter
from supabase import create_client
from firebase_admin import firestore
from core.firebase_init import get_firestore

# ── Config ───────────────────────────────────────────────────────────────────

FUZZY_TOL_POSITION = 0.01
FUZZY_TOL_AREA     = 0.1
FUZZY_TOL_DIM      = 0.01

BUCKET = "step-files"
MESH_CACHE_BUCKET = "mesh-cache"

# Lazy Supabase client for storage only
_supabase_client = None


def _get_storage_client():
    global _supabase_client
    if _supabase_client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        _supabase_client = create_client(url, key)
    return _supabase_client


# ── Face fingerprinting (pure geometry — unchanged) ─────────────────────────

def _norm(val):
    return val + 0.0


def face_fingerprint_raw(face) -> dict:
    surf = BRepAdaptor_Surface(face)
    surf_type = int(surf.GetType())

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    area = _norm(props.Mass())
    cm = props.CentreOfMass()
    cx, cy, cz = _norm(cm.X()), _norm(cm.Y()), _norm(cm.Z())

    bbox = Bnd_Box()
    BRepBndLib.Add_s(face, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    dims = sorted([
        _norm(abs(xmax - xmin)),
        _norm(abs(ymax - ymin)),
        _norm(abs(zmax - zmin)),
    ])

    n_edges = 0
    exp_e = TopExp_Explorer(face, TopAbs_EDGE)
    while exp_e.More():
        n_edges += 1
        exp_e.Next()

    n_verts = 0
    exp_v = TopExp_Explorer(face, TopAbs_VERTEX)
    while exp_v.More():
        n_verts += 1
        exp_v.Next()

    return {
        "surf_type": surf_type,
        "cx": cx, "cy": cy, "cz": cz,
        "area": area,
        "dx": dims[0], "dy": dims[1], "dz": dims[2],
        "n_edges": n_edges, "n_verts": n_verts,
    }


def face_fingerprint(face) -> str:
    raw = face_fingerprint_raw(face)
    canonical = (
        f"T{raw['surf_type']}|"
        f"C{round(raw['cx'],3)},{round(raw['cy'],3)},{round(raw['cz'],3)}|"
        f"A{round(raw['area'],3)}|"
        f"D{round(raw['dx'],3)},{round(raw['dy'],3)},{round(raw['dz'],3)}|"
        f"E{raw['n_edges']}V{raw['n_verts']}"
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ── Database operations (Firestore) ──────────────────────────────────────────

def _face_doc_id(model_id: str, face_hash: str) -> str:
    return f"{model_id}_{face_hash}"


def save_face_meta(model_id: str, face_hash: str, meta: dict, raw: dict = None):
    """Upsert metadata + raw fingerprint for a face."""
    db = get_firestore()
    doc_id = _face_doc_id(model_id, face_hash)
    row = {
        "model_id": model_id,
        "face_hash": face_hash,
        "meta": meta,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if raw:
        row.update({
            "surf_type": raw["surf_type"],
            "cx": raw["cx"], "cy": raw["cy"], "cz": raw["cz"],
            "area": raw["area"],
            "dx": raw["dx"], "dy": raw["dy"], "dz": raw["dz"],
            "n_edges": raw["n_edges"], "n_verts": raw["n_verts"],
        })
    db.collection("face_meta").document(doc_id).set(row, merge=True)


def get_face_meta(model_id: str, face_hash: str) -> dict | None:
    db = get_firestore()
    doc_id = _face_doc_id(model_id, face_hash)
    doc = db.collection("face_meta").document(doc_id).get()
    if doc.exists:
        return doc.to_dict().get("meta")
    return None


def get_all_face_meta(model_id: str) -> list[dict]:
    db = get_firestore()
    docs = (
        db.collection("face_meta")
        .where(filter=FieldFilter("model_id", "==", model_id))
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def lookup_face_meta(model_id: str, face_hashes: list[str]) -> dict[str, dict]:
    """Exact hash lookup — batched Firestore reads (single gRPC call)."""
    if not face_hashes:
        return {}
    db = get_firestore()
    refs = [db.collection("face_meta").document(_face_doc_id(model_id, fh)) for fh in face_hashes]
    docs = db.get_all(refs)  # Single batched gRPC call
    result = {}
    for doc in docs:
        if doc.exists:
            data = doc.to_dict()
            meta = data.get("meta")
            if meta:
                result[data.get("face_hash")] = meta
    return result


def fuzzy_lookup_face(model_id: str, raw: dict,
                      tol_pos=FUZZY_TOL_POSITION,
                      tol_area=FUZZY_TOL_AREA,
                      tol_dim=FUZZY_TOL_DIM) -> tuple:
    """Fuzzy match by topology + tolerance on continuous values."""
    db = get_firestore()
    docs = (
        db.collection("face_meta")
        .where(filter=FieldFilter("model_id", "==", model_id))
        .where(filter=FieldFilter("surf_type", "==", raw["surf_type"]))
        .where(filter=FieldFilter("n_edges", "==", raw["n_edges"]))
        .where(filter=FieldFilter("n_verts", "==", raw["n_verts"]))
        .stream()
    )

    best = None
    best_dist = float("inf")

    for doc in docs:
        data = doc.to_dict()
        if abs((data.get("area", 0)) - raw["area"]) > tol_area:
            continue
        if (abs(data.get("dx", 0) - raw["dx"]) > tol_dim or
            abs(data.get("dy", 0) - raw["dy"]) > tol_dim or
            abs(data.get("dz", 0) - raw["dz"]) > tol_dim):
            continue
        if (abs(data.get("cx", 0) - raw["cx"]) > tol_pos or
            abs(data.get("cy", 0) - raw["cy"]) > tol_pos or
            abs(data.get("cz", 0) - raw["cz"]) > tol_pos):
            continue

        dist = math.sqrt(
            (data.get("cx", 0) - raw["cx"]) ** 2
            + (data.get("cy", 0) - raw["cy"]) ** 2
            + (data.get("cz", 0) - raw["cz"]) ** 2
            + (data.get("area", 0) - raw["area"]) ** 2
        )
        if dist < best_dist:
            best_dist = dist
            meta = data.get("meta")
            if meta:
                best = (data.get("face_hash"), meta)

    return best if best else (None, None)


def lookup_faces_batch(model_id: str,
                       face_hashes: list[str],
                       face_raws: list[dict]) -> dict[str, dict]:
    """Batch: exact hash first, then fuzzy for misses."""
    result = lookup_face_meta(model_id, face_hashes)

    for h, raw in zip(face_hashes, face_raws):
        if h in result or raw is None:
            continue
        fh, meta = fuzzy_lookup_face(model_id, raw)
        if meta:
            result[h] = meta

    return result


def delete_face_meta(model_id: str, face_hash: str):
    db = get_firestore()
    db.collection("face_meta").document(_face_doc_id(model_id, face_hash)).delete()


def delete_faces(model_id: str, face_hashes: list[str]):
    if not face_hashes:
        return
    db = get_firestore()
    batch = db.batch()
    for fh in face_hashes:
        batch.delete(db.collection("face_meta").document(_face_doc_id(model_id, fh)))
    batch.commit()


def clear_model_metadata(model_id: str):
    db = get_firestore()
    docs = (
        db.collection("face_meta")
        .where(filter=FieldFilter("model_id", "==", model_id))
        .stream()
    )
    batch = db.batch()
    count = 0
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
    batch.commit()


def clear_database():
    """GLOBAL NUKE — delete all face_meta docs."""
    db = get_firestore()
    docs = db.collection("face_meta").stream()
    batch = db.batch()
    count = 0
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
    batch.commit()


def get_db_stats(model_id: str = None) -> dict:
    db = get_firestore()
    if model_id:
        docs = (
            db.collection("face_meta")
            .where(filter=FieldFilter("model_id", "==", model_id))
            .stream()
        )
        return {"total_faces": sum(1 for _ in docs)}
    # Global count
    docs = db.collection("face_meta").stream()
    return {"total_faces": sum(1 for _ in docs)}


# ── Face-ID based annotation storage (simple, reliable) ─────────────────────

COLL_ANNOTATIONS = "model_annotations"


def save_model_annotations(model_id: str, annotations: dict) -> bool:
    """
    Bulk-save all face annotations for a model.
    annotations: { "0": {"color": "#ff0000", "thread": {...}, "tolerance": {...}}, ... }
    Only faces with non-default data should be included.
    """
    db = get_firestore()
    doc_ref = db.collection(COLL_ANNOTATIONS).document(model_id)
    doc_ref.set({
        "model_id": model_id,
        "annotations": annotations,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)
    return True


def get_model_annotations(model_id: str) -> dict:
    """
    Retrieve all face annotations for a model.
    Returns: { "0": {"color": "#ff0000", ...}, "3": {...}, ... } or {}
    """
    db = get_firestore()
    doc = db.collection(COLL_ANNOTATIONS).document(model_id).get()
    if doc.exists:
        data = doc.to_dict()
        return data.get("annotations", {})
    return {}


def delete_model_annotations(model_id: str):
    """Delete all annotations for a model."""
    db = get_firestore()
    db.collection(COLL_ANNOTATIONS).document(model_id).delete()


# ── Storage helpers (Supabase Storage) ───────────────────────────────────────

def upload_step_to_storage(user_id: str, model_id: str, filename: str, file_bytes: bytes) -> str:
    """Upload STEP file to Supabase Storage. Returns storage path."""
    client = _get_storage_client()
    path = f"{user_id}/{model_id}/{filename}"
    client.storage.from_(BUCKET).upload(path, file_bytes)
    return path


def download_step_from_storage(storage_path: str) -> bytes:
    """Download STEP file from Supabase Storage."""
    client = _get_storage_client()
    return client.storage.from_(BUCKET).download(storage_path)


def delete_step_from_storage(storage_path: str):
    """Delete STEP file from Supabase Storage."""
    client = _get_storage_client()
    client.storage.from_(BUCKET).remove([storage_path])


# ── Mesh Cache (Supabase Storage) ────────────────────────────────────────────

def save_mesh_cache(model_id: str, faces_data: list, original_filename: str = "") -> bool:
    """
    Save tessellated mesh data to Supabase Storage cache.
    Returns True if successful, False otherwise.
    """
    import json
    from datetime import datetime
    
    cache_data = {
        "faces": faces_data,
        "uuid": model_id,
        "original_filename": original_filename,
        "cached_at": datetime.utcnow().isoformat(),
        "version": 1
    }
    
    try:
        client = _get_storage_client()
        path = f"{model_id}/mesh.json"
        json_str = json.dumps(cache_data)
        client.storage.from_(MESH_CACHE_BUCKET).upload(path, json_str.encode(), {"upsert": "true"})
        return True
    except Exception as e:
        print(f"[MESH CACHE] Failed to save: {e}")
        return False


def get_mesh_cache(model_id: str) -> dict | None:
    """
    Retrieve cached mesh data from Supabase Storage.
    Returns the cache dict or None if not found.
    """
    import json
    
    try:
        client = _get_storage_client()
        path = f"{model_id}/mesh.json"
        data = client.storage.from_(MESH_CACHE_BUCKET).download(path)
        return json.loads(data.decode("utf-8"))
    except Exception as e:
        return None


def delete_mesh_cache(model_id: str) -> bool:
    """Delete mesh cache for a model."""
    try:
        client = _get_storage_client()
        path = f"{model_id}/mesh.json"
        client.storage.from_(MESH_CACHE_BUCKET).remove([path])
        return True
    except Exception as e:
        print(f"[MESH CACHE] Failed to delete: {e}")
        return False
