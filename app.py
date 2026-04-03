"""
OnyxCAD — Flask app for loading STEP files with XDE (Extended Data Exchange).
Multi-tenant edition with Supabase auth, PostgreSQL, and cloud storage.
"""
import logging
import os
import re
import uuid
import secrets
import tempfile
import io
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, send_file, g

# ── Core Modules ─────────────────────────────────────────────────────────────
from core.state import ModelState, manager
from core.loader import load_step_xcaf
from core.utils import hex_to_quantity
from core.exporter import export_step_xcaf
from core.auth import require_auth, optional_auth
from core.db import (
    get_model_by_id,
    get_public_model,
    get_model_by_share_token,
    create_model,
    update_model,
    delete_model_doc,
    list_user_models,
)
from core.firebase_init import get_user_email

# ── Billing ──────────────────────────────────────────────────────────────────
from core.billing import (
    check_can_upload,
    check_can_share,
    get_user_plan,
    get_upload_limit,
    UPLOAD_LIMITS,
    MAX_UPLOAD_SIZE,
    create_checkout_session,
    create_customer_portal_url,
    verify_webhook_signature,
    handle_webhook_event,
)

# ── OCP imports needed for routes ───────────────────────────────────────────
from OCP.XCAFDoc import XCAFDoc_ColorSurf
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

# ── Geometry fingerprinting + Postgres persistence ───────────────────────────
from face_db import (
    save_face_meta,
    get_all_face_meta,
    get_db_stats,
    clear_model_metadata,
    delete_faces,
    clear_database,
    upload_step_to_storage,
    download_step_from_storage,
    delete_step_from_storage,
    save_mesh_cache,
    get_mesh_cache,
    delete_mesh_cache,
    save_model_annotations,
    get_model_annotations,
    delete_model_annotations,
)

# ── Flask setup ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE  # Hard ceiling — rejects before body is read
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ── Logging setup ────────────────────────────────────────────────────────────
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_logs.txt")
file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addHandler(file_handler)
werkzeug_logger.setLevel(logging.INFO)

app.logger.info("Flask server starting up")


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify({
        "error": f"File too large. Max allowed upload is {MAX_UPLOAD_SIZE / (1024 * 1024):.0f} MB."
    }), 413


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_owned_model(model_id: str):
    """
    Verify ownership and return (model_row, model_state).
    Uses g.user_id set by @require_auth.
    Returns (model_row, model_state) or raises a JSON error response tuple.
    """
    model_row = get_model_by_id(model_id, g.user_id)
    if model_row is None:
        return None, None
    model_state = manager.get_state(g.user_id, model_id)
    return model_row, model_state


def _load_public_or_owned_model(model_id: str):
    """
    Load a model if the user owns it OR it's public.
    Returns (model_row, model_state) or (None, None).
    """
    # Try owned first
    model_row = get_model_by_id(model_id, g.user_id) if g.user_id else None
    if model_row:
        return model_row, manager.get_state(g.user_id, model_id)
    # Try public
    model_row = get_public_model(model_id)
    if model_row:
        # Public models get a shared read-only state keyed under "public"
        return model_row, manager.get_state("public", model_id)
    return None, None


# ── Routes ───────────────────────────────────────────────────────────────────

FIRST_BOOT = True
APP_VERSION = 1


@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/login")
def login():
    return render_template(
        "auth.html",
        firebase_api_key=os.environ.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", ""),
    )


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/dashboard")
def dashboard_view():
    """User dashboard - shows all projects."""
    return render_template("dashboard.html",
        firebase_api_key=os.environ.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", ""),
    )


@app.route("/viewer/<uuid_str>")
def viewer_view(uuid_str):
    """Serve the viewer for a specific model UUID."""
    return render_template("index.html", boot_test=False, version=APP_VERSION, read_only=False, share_token="",
        firebase_api_key=os.environ.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", ""),
        model_uuid=uuid_str,
    )


@app.route("/app")
def app_view():
    """Redirect to dashboard."""
    return render_template("dashboard.html",
        firebase_api_key=os.environ.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", ""),
    )


@app.route("/app/<uuid_str>")
def app_view_model(uuid_str):
    """Serve the viewer for a specific model UUID (legacy route, redirect to viewer)."""
    return render_template("index.html", boot_test=False, version=APP_VERSION, read_only=False, share_token="",
        firebase_api_key=os.environ.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", ""),
        model_uuid=uuid_str,
    )


@app.route("/api/me", methods=["GET"])
@require_auth
def get_me():
    """Return current user info + plan."""
    plan_info = get_user_plan(g.user_id)
    email = get_user_email(g.user_id)

    return jsonify({
        "user_id": g.user_id,
        "email": email,
        "plan": plan_info["plan"],
        "active_projects": plan_info["active_projects"],
        "limit": plan_info["limit"],
    })


# ── Model CRUD ───────────────────────────────────────────────────────────────

@app.route("/api/models", methods=["GET"])
@require_auth
def list_models():
    """Return all models owned by the current user (active + archived)."""
    models = list_user_models(g.user_id)
    return jsonify({"models": models})


@app.route("/api/models/<model_id>", methods=["GET"])
@require_auth
def get_model_detail(model_id):
    """Return metadata for a single model the user owns."""
    model_row = get_model_by_id(model_id, g.user_id)
    if model_row is None:
        return jsonify({"error": "Model not found"}), 404
    return jsonify({"model": model_row})


@app.route("/api/models/<model_id>", methods=["DELETE"])
@require_auth
def delete_model(model_id):
    """Delete a model: DB row (cascades to face_meta), Storage file, in-memory state."""
    model_row = get_model_by_id(model_id, g.user_id)
    if model_row is None:
        return jsonify({"error": "Model not found"}), 404

    # Delete from Supabase Storage
    storage_path = model_row.get("storage_path")
    if storage_path:
        try:
            delete_step_from_storage(storage_path)
        except Exception as e:
            app.logger.warning(f"Storage delete failed for {storage_path}: {e}")

    # Delete mesh cache
    try:
        delete_mesh_cache(model_id)
    except Exception as e:
        app.logger.warning(f"Mesh cache delete failed for {model_id}: {e}")

    # Delete annotations
    try:
        delete_model_annotations(model_id)
    except Exception as e:
        app.logger.warning(f"Annotation delete failed for {model_id}: {e}")

    # Delete from DB (cascades to face_meta)
    delete_model_doc(model_id)

    # Clear in-memory state
    manager.clear_state(g.user_id, model_id)

    return jsonify({"ok": True, "deleted": model_id})


@app.route("/api/models/<model_id>/archive", methods=["POST"])
@require_auth
def archive_model(model_id):
    """Archive a project — frees an active slot, share links still work."""
    model_row = get_model_by_id(model_id, g.user_id)
    if model_row is None:
        return jsonify({"error": "Model not found"}), 404

    if model_row.get("is_archived"):
        return jsonify({"ok": True, "already_archived": True})

    update_model(model_id, {"is_archived": True})

    # Clear in-memory state for this model
    manager.clear_state(g.user_id, model_id)

    plan_info = get_user_plan(g.user_id)
    return jsonify({
        "ok": True,
        "archived": model_id,
        "active_projects": plan_info["active_projects"],
        "limit": plan_info["limit"],
    })


@app.route("/api/models/<model_id>/unarchive", methods=["POST"])
@require_auth
def unarchive_model(model_id):
    """Unarchive a project — reclaims an active slot if under limit."""
    model_row = get_model_by_id(model_id, g.user_id)
    if model_row is None:
        return jsonify({"error": "Model not found"}), 404

    if not model_row.get("is_archived"):
        return jsonify({"ok": True, "already_active": True})

    # Check if user has an available slot
    allowed, msg = check_can_upload(g.user_id)
    if not allowed:
        return jsonify({"error": "upgrade_required", "message": msg}), 403

    update_model(model_id, {"is_archived": False})

    plan_info = get_user_plan(g.user_id)
    return jsonify({
        "ok": True,
        "unarchived": model_id,
        "active_projects": plan_info["active_projects"],
        "limit": plan_info["limit"],
    })


@app.route("/api/projects", methods=["POST"])
@require_auth
def create_project():
    """Create a new empty project (no file attached yet)."""
    data = request.get_json() or {}
    project_name = data.get("name", "Untitled Project")
    allowed, msg = check_can_upload(g.user_id)
    if not allowed:
        return jsonify({"error": msg, "message": msg}), 403
    
    model_id = create_model(g.user_id, project_name, "")
    update_model(model_id, {"name": project_name})
    
    return jsonify({
        "ok": True,
        "project_id": model_id,
        "name": project_name,
    })


# ── Public Sharing ────────────────────────────────────────────────────────────

@app.route("/api/models/<model_id>/share", methods=["POST"])
@require_auth
def create_share_link(model_id):
    """Generate a share token and make the model public."""
    # ── Plan gate: sharing requires Pro or Growth ────────────────────────
    if not check_can_share(g.user_id):
        return jsonify({
            "error": "upgrade_required",
            "message": "Sharing requires Pro plan ($79/month). Upgrade to unlock shareable links.",
        }), 403

    model_row = get_model_by_id(model_id, g.user_id)
    if model_row is None:
        return jsonify({"error": "Model not found"}), 404

    # Reuse existing token if already shared
    if model_row.get("share_token"):
        share_token = model_row["share_token"]
    else:
        share_token = secrets.token_urlsafe(16)

    update_model(model_id, {"is_public": True, "share_token": share_token})

    # Build share URL from request host
    host = request.host_url.rstrip("/")
    share_url = f"{host}/share/{share_token}"

    return jsonify({
        "ok": True,
        "share_token": share_token,
        "share_url": share_url,
    })


@app.route("/api/models/<model_id>/share", methods=["DELETE"])
@require_auth
def revoke_share_link(model_id):
    """Revoke public sharing: set is_public=false, clear share_token."""
    model_row = get_model_by_id(model_id, g.user_id)
    if model_row is None:
        return jsonify({"error": "Model not found"}), 404

    update_model(model_id, {"is_public": False, "share_token": None})

    return jsonify({"ok": True, "revoked": True})


@app.route("/share/<share_token>", methods=["GET"])
@optional_auth
def load_shared_model(share_token):
    """
    Render the viewer in read-only mode for a shared model.
    The viewer JS will fetch mesh data from /share/<token>/mesh.
    """
    model_row = get_model_by_share_token(share_token)
    if model_row is None:
        return render_template(
            "index.html", boot_test=False, version=APP_VERSION,
            read_only=False, share_token="",
        ), 404

    return render_template(
        "index.html", boot_test=False, version=APP_VERSION,
        read_only=True, share_token=share_token,
        firebase_api_key=os.environ.get("FIREBASE_API_KEY", ""),
        firebase_auth_domain=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", ""),
    )


@app.route("/share/<share_token>/mesh", methods=["GET"])
@optional_auth
def shared_model_mesh(share_token):
    """
    Return tessellated mesh data for a shared model.
    Uses mesh cache if available, otherwise downloads and tessellates.
    """
    model_row = get_model_by_share_token(share_token)
    if model_row is None:
        return jsonify({"error": "Shared model not found or link revoked"}), 404

    model_id = model_row["id"]
    state = manager.get_state("shared", model_id)

    # Check persistent mesh cache first
    cache = get_mesh_cache(model_id)
    if cache and cache.get("faces"):
        faces = cache["faces"]

        # Overlay annotations from Firestore onto cached mesh data
        annotations = get_model_annotations(model_id)
        if annotations:
            for face in faces:
                fid = str(face.get("id", ""))
                if fid in annotations:
                    ann = annotations[fid]
                    if "color" in ann:
                        face["color"] = ann["color"]
                    if "thread" in ann:
                        face["thread"] = ann["thread"]
                    if "tolerance" in ann:
                        face["tolerance"] = ann["tolerance"]

        state.faces_cache = faces
        return jsonify({
            "faces": faces,
            "uuid": model_id,
            "original_filename": model_row["original_filename"],
            "is_shared": True,
        })

    # Cache miss - need to tessellate
    try:
        file_bytes = download_step_from_storage(model_row["storage_path"])
        tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
        try:
            tmp.write(file_bytes)
            tmp.close()

            state.reset()
            state.original_filename = model_row["original_filename"]
            state.model_uuid = model_id

            faces = load_step_xcaf(tmp.name, state, model_id=model_id)
            
            # Save to persistent mesh cache for future loads
            save_mesh_cache(model_id, faces, model_row.get("original_filename", ""))
            
            return jsonify({
                "faces": faces,
                "uuid": model_id,
                "original_filename": model_row["original_filename"],
                "is_shared": True,
            })
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/share/<share_token>/data", methods=["GET"])
@optional_auth
def shared_model_data(share_token):
    """
    Return metadata for a shared model (read-only).
    Returns face_meta rows from the DB — no tessellation.
    """
    model_row = get_model_by_share_token(share_token)
    if model_row is None:
        return jsonify({"error": "Shared model not found or link revoked"}), 404

    model_id = model_row["id"]
    face_docs = get_all_face_meta(model_id)

    meta_list = []
    for row in face_docs:
        meta = row.get("meta", {})
        meta_list.append({"face_hash": row.get("face_hash"), "meta": meta})

    return jsonify({
        "model_id": model_id,
        "original_filename": model_row["original_filename"],
        "face_count": len(meta_list),
        "face_meta": meta_list,
    })


# ── Upload ───────────────────────────────────────────────────────────────────

@app.route("/upload", methods=["POST"])
@require_auth
def upload():
    # Check for optional existing project ID
    existing_project_id = request.form.get("project_id") or None
    
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No selected file"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".step", ".stp"):
        return jsonify({"error": "Only .step / .stp files are supported"}), 400

    original_filename = os.path.splitext(f.filename)[0]
    user_id = g.user_id

    # ── Enforce per-plan upload size limit ───────────────────────────────
    upload_limit = get_upload_limit(user_id)
    upload_limit_mb = upload_limit / (1024 * 1024)

    # Fast check via Content-Length header (avoids reading oversized body)
    content_length = request.content_length
    if content_length and content_length > upload_limit:
        return jsonify({
            "error": f"File too large. Your plan allows up to {upload_limit_mb:.0f} MB uploads."
        }), 413

    # Precise check on actual file stream (catches chunked/mismatched headers)
    f.seek(0, 2)
    actual_size = f.tell()
    f.seek(0)
    if actual_size > upload_limit:
        return jsonify({
            "error": f"File too large ({actual_size / (1024 * 1024):.1f} MB). "
                     f"Your plan allows up to {upload_limit_mb:.0f} MB uploads."
        }), 413

    # Use existing project ID if provided, otherwise create new
    if existing_project_id:
        # Verify user owns this project
        existing_model = get_model_by_id(existing_project_id, user_id)
        if existing_model:
            model_uuid = existing_project_id
        else:
            # Invalid project ID, create new
            model_uuid = uuid.uuid4().hex
    else:
        model_uuid = uuid.uuid4().hex

    # Read file bytes
    file_bytes = f.read()

    # ── Tessellate FIRST (CPU-bound, instant, no network) ───────────────
    tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
    try:
        tmp.write(file_bytes)
        tmp.close()

        model_state = manager.get_state(user_id, model_uuid)
        model_state.original_filename = original_filename
        model_state.model_uuid = model_uuid

        # ── Dynamic Deflection ───────────────────────────────────────────────
        # Adjust tessellation quality based on file size to prevent hangs
        file_size_mb = len(file_bytes) / (1024 * 1024)
        if file_size_mb < 2.0:
            lin_def = 0.1  # Perfect quality for small files
        elif file_size_mb < 10.0:
            lin_def = 0.5  # Great quality for medium files
        else:
            lin_def = 1.0  # Good quality for large files (>10MB) to prevent 10+ min hangs

        app.logger.info(f"Uploading {file_size_mb:.2f}MB file. Using linear_deflection={lin_def}")

        faces = load_step_xcaf(tmp.name, model_state, model_id=None, linear_deflection=lin_def)
        model_state.faces_cache = faces

    except Exception as e:
        app.logger.error(f"Tessellation failed: {e}", exc_info=True)
        manager.clear_state(user_id, model_uuid)
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)

    # ── Allow all uploads (quota enforced only during project creation) ───
    # Project creation in /api/projects already enforces the limit
    # Once project exists, uploads should always work - ensures all slots usable

    # ── Persist to storage + DB ─────────────────────────────────────────
    try:
        storage_path = upload_step_to_storage(user_id, model_uuid, f.filename, file_bytes)
    except Exception as e:
        app.logger.error(f"Storage upload failed: {e}", exc_info=True)
        return jsonify({"error": f"Storage upload failed: {e}"}), 500

    # If using existing project, update it; otherwise create new
    if existing_project_id and get_model_by_id(existing_project_id, user_id):
        update_model(existing_project_id, {
            "original_filename": original_filename,
            "storage_path": storage_path,
            "has_file": True
        })
    else:
        create_model(user_id, original_filename, storage_path)
        # Mark as having a file for new projects
        update_model(model_uuid, {"has_file": True})

    # Pre-tessellation: save mesh to persistent cache for instant future loads
    save_mesh_cache(model_uuid, faces, original_filename)

    return jsonify({"faces": faces, "uuid": model_uuid})


@app.route("/api/model/<uuid_str>", methods=["GET"])
@require_auth
def get_model_data(uuid_str):
    """Retrieve face data for a persisted model by UUID."""
    model_row, model_state = _load_owned_model(uuid_str)
    if model_row is None:
        return jsonify({"error": "Model not found"}), 404
    
    # Check if project has a file uploaded
    has_file = model_row.get("has_file", False)
    if not has_file:
        # Project exists but no file uploaded yet - return project name too
        return jsonify({
            "error": "No file uploaded", 
            "uuid": uuid_str, 
            "has_file": False,
            "name": model_row.get("name", "Untitled Project")
        }), 404

    # Check persistent mesh cache in Supabase Storage first
    cache = get_mesh_cache(uuid_str)
    if cache and cache.get("faces"):
        faces = cache["faces"]

        # Overlay annotations from Firestore
        annotations = get_model_annotations(uuid_str)
        if annotations:
            for face in faces:
                fid = str(face.get("id", ""))
                if fid in annotations:
                    ann = annotations[fid]
                    if "color" in ann:
                        face["color"] = ann["color"]
                    if "thread" in ann:
                        face["thread"] = ann["thread"]
                    if "tolerance" in ann:
                        face["tolerance"] = ann["tolerance"]

        model_state.faces_cache = faces
        has_file = model_row.get("has_file", True)
        # Include project name for display
        return jsonify({
            "faces": faces, 
            "uuid": uuid_str, 
            "has_file": has_file,
            "original_filename": model_row.get("original_filename", ""),
            "name": model_row.get("name", "")
        })

    # Return in-memory cache if available
    if model_state.faces_cache:
        has_file = model_row.get("has_file", True)
        return jsonify({
            "faces": model_state.faces_cache, 
            "uuid": uuid_str, 
            "has_file": has_file,
            "original_filename": model_row.get("original_filename", ""),
            "name": model_row.get("name", "")
        })

    try:
        # Download from storage to temp file
        file_bytes = download_step_from_storage(model_row["storage_path"])
        tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
        try:
            tmp.write(file_bytes)
            tmp.close()

            model_state.reset()
            model_state.original_filename = model_row["original_filename"]
            model_state.model_uuid = uuid_str

            faces = load_step_xcaf(tmp.name, model_state, model_id=uuid_str)
            model_state.faces_cache = faces  # Cache for instant re-load
            
            # Save to persistent mesh cache for future loads
            save_mesh_cache(uuid_str, faces, model_row.get("original_filename", ""))
            
            return jsonify({"faces": faces, "uuid": uuid_str})
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Annotation routes (face_id-based, production) ────────────────────────────

@app.route("/api/models/<model_id>/annotations", methods=["GET"])
@require_auth
def get_annotations(model_id):
    """Get all face annotations for a model."""
    model_row = get_model_by_id(model_id, g.user_id)
    if model_row is None:
        return jsonify({"error": "Model not found"}), 404
    annotations = get_model_annotations(model_id)
    return jsonify({"annotations": annotations})


@app.route("/api/models/<model_id>/annotations", methods=["POST"])
@require_auth
def save_annotations(model_id):
    """
    Bulk-save all face annotations for a model.
    Body: { "annotations": { "0": {"color": "#ff0000", "thread": {...}}, ... } }
    """
    model_row = get_model_by_id(model_id, g.user_id)
    if model_row is None:
        return jsonify({"error": "Model not found"}), 404

    data = request.get_json()
    annotations = data.get("annotations", {})

    try:
        save_model_annotations(model_id, annotations)
        count = len(annotations)
        app.logger.info(f"Saved {count} face annotations for model {model_id}")

        # Update mesh cache to include annotations so cached loads have them
        cache = get_mesh_cache(model_id)
        if cache and cache.get("faces"):
            for face in cache["faces"]:
                fid = str(face.get("id", ""))
                if fid in annotations:
                    ann = annotations[fid]
                    if "color" in ann:
                        face["color"] = ann["color"]
                    if "thread" in ann:
                        face["thread"] = ann["thread"]
                    if "tolerance" in ann:
                        face["tolerance"] = ann["tolerance"]
            save_mesh_cache(model_id, cache["faces"], cache.get("original_filename", ""))

        return jsonify({"ok": True, "saved_count": count})
    except Exception as e:
        app.logger.error(f"Failed to save annotations: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ── Face metadata routes (legacy, kept for backward compat) ──────────────────

@app.route("/set_color", methods=["POST"])
@require_auth
def set_color():
    data = request.get_json()
    model_id = data.get("model_id")
    if not model_id:
        return jsonify({"error": "model_id required"}), 400

    model_row, state = _load_owned_model(model_id)
    if model_row is None:
        return jsonify({"error": "Model not found or not authorized"}), 403

    if state.doc is None:
        return jsonify({"error": "No model loaded in session"}), 400

    updates = data.get("updates")
    if updates is None:
        updates = [{"face_id": data.get("face_id"), "color": data.get("color")}]

    db_updated_count = 0

    for item in updates:
        face_id = item.get("face_id")
        hex_color = item.get("color")

        if face_id is None or hex_color is None:
            continue
        if face_id < 0 or face_id >= len(state.face_shapes):
            continue

        try:
            q_color = hex_to_quantity(hex_color)
            face_label = state.face_labels[face_id]
            face_shape = state.face_shapes[face_id]
            if face_label is not None and not face_label.IsNull():
                state.color_tool.SetColor(face_label, q_color, XCAFDoc_ColorSurf)
            else:
                state.color_tool.SetColor(face_shape, q_color, XCAFDoc_ColorSurf)

            state.face_meta.setdefault(face_id, {})["color"] = hex_color

            if face_id < len(state.face_hashes):
                fh = state.face_hashes[face_id]
                raw = state.face_raws[face_id] if face_id < len(state.face_raws) else None
                if fh and fh != "unknown":
                    meta = state.face_meta.get(face_id, {})
                    if meta:
                        save_face_meta(model_id, fh, meta, raw=raw)
                        db_updated_count += 1

        except Exception as e:
            print(f"Error setting color for face {face_id}: {e}")
            continue

    return jsonify({"ok": True, "db_updated_count": db_updated_count})


@app.route("/set_thread", methods=["POST"])
@require_auth
def set_thread():
    data = request.get_json()
    model_id = data.get("model_id")
    if not model_id:
        return jsonify({"error": "model_id required"}), 400

    model_row, state = _load_owned_model(model_id)
    if model_row is None:
        return jsonify({"error": "Model not found or not authorized"}), 403

    if state.doc is None:
        return jsonify({"error": "No model loaded in session"}), 400

    updates = data.get("updates")
    if updates is None:
        updates = [{"face_id": data.get("face_id"), "thread": data.get("thread")}]

    db_updated_count = 0

    for item in updates:
        face_id = item.get("face_id")
        thread = item.get("thread")

        if face_id is None:
            continue
        if face_id < 0 or face_id >= len(state.face_shapes):
            continue

        if thread:
            state.face_meta.setdefault(face_id, {})["thread"] = {
                "type": thread.get("type", ""),
                "size": thread.get("size", ""),
                "pitch": thread.get("pitch", ""),
                "class": thread.get("class", ""),
            }
        else:
            if face_id in state.face_meta:
                state.face_meta[face_id].pop("thread", None)
                if not state.face_meta[face_id]:
                    del state.face_meta[face_id]

        if face_id < len(state.face_hashes):
            fh = state.face_hashes[face_id]
            raw = state.face_raws[face_id] if face_id < len(state.face_raws) else None
            if fh and fh != "unknown":
                meta = state.face_meta.get(face_id, {})
                if meta:
                    save_face_meta(model_id, fh, meta, raw=raw)
                    db_updated_count += 1

    return jsonify({"ok": True, "db_updated_count": db_updated_count})


@app.route("/set_tolerance", methods=["POST"])
@require_auth
def set_tolerance():
    data = request.get_json()
    model_id = data.get("model_id")
    if not model_id:
        return jsonify({"error": "model_id required"}), 400

    model_row, state = _load_owned_model(model_id)
    if model_row is None:
        return jsonify({"error": "Model not found or not authorized"}), 403

    if state.doc is None:
        return jsonify({"error": "No model loaded in session"}), 400

    updates = data.get("updates")
    if updates is None:
        updates = [{"face_id": data.get("face_id"), "tolerance": data.get("tolerance")}]

    db_updated_count = 0

    for item in updates:
        face_id = item.get("face_id")
        tol = item.get("tolerance")

        if face_id is None:
            continue
        if face_id < 0 or face_id >= len(state.face_shapes):
            continue

        if tol:
            state.face_meta.setdefault(face_id, {})["tolerance"] = {
                "type": tol.get("type", ""),
                "value": tol.get("value", ""),
                "datum": tol.get("datum", ""),
            }
        else:
            if face_id in state.face_meta:
                state.face_meta[face_id].pop("tolerance", None)
                if not state.face_meta[face_id]:
                    del state.face_meta[face_id]

        if face_id < len(state.face_hashes):
            fh = state.face_hashes[face_id]
            if fh and fh != "unknown":
                meta = state.face_meta.get(face_id, {})
                if meta:
                    raw = state.face_raws[face_id] if face_id < len(state.face_raws) else None
                    save_face_meta(model_id, fh, meta, raw=raw)
                    db_updated_count += 1

    return jsonify({"ok": True, "db_updated_count": db_updated_count})


# ── Export ────────────────────────────────────────────────────────────────────

@app.route("/export", methods=["GET"])
@require_auth
def export_step():
    """Re-export STEP with colours (XDE) + metadata (comment block)."""
    model_id = request.args.get("model_id")
    if not model_id:
        return jsonify({"error": "model_id query param required"}), 400

    model_row, state = _load_owned_model(model_id)
    if model_row is None:
        return jsonify({"error": "Model not found or not authorized"}), 403

    if state.doc is None:
        return jsonify({"error": "No model loaded in session"}), 400

    try:
        filename, mimetype, file_stream = export_step_xcaf(
            state, app.config["UPLOAD_FOLDER"]
        )

        out_name = filename
        if state.model_uuid:
            out_name = f"{state.model_uuid}.step"

        return send_file(
            file_stream,
            as_attachment=True,
            download_name=out_name,
            mimetype=mimetype,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Analysis routes ──────────────────────────────────────────────────────────

@app.route("/get_holes", methods=["GET"])
@require_auth
def get_holes():
    """Analyze model and return grouped holes (cylindrical faces)."""
    model_id = request.args.get("model_id")
    if not model_id:
        return jsonify({"error": "model_id query param required"}), 400

    model_row, state = _load_owned_model(model_id)
    if model_row is None:
        return jsonify({"error": "Model not found or not authorized"}), 403

    if state.doc is None:
        return jsonify({"error": "No model loaded in session"}), 400

    def get_cylinder_info(face_shape):
        surf = BRepAdaptor_Surface(face_shape, True)
        if surf.GetType() == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            r = cyl.Radius()
            return {"type": "cylinder", "diameter": round(r * 2, 4)}
        return None

    grouped = {}
    for i, shape in enumerate(state.face_shapes):
        info = get_cylinder_info(shape)
        if info:
            d = info["diameter"]
            grouped.setdefault(d, []).append(i)

    result = []
    for d, ids in grouped.items():
        result.append({"diameter": d, "ids": ids, "count": len(ids)})
    result.sort(key=lambda x: x["diameter"])

    return jsonify({"holes": result})


# ── Static option routes (no auth needed) ────────────────────────────────────

@app.route("/thread_options", methods=["GET"])
def thread_options():
    """Return the standard option lists for thread dropdowns."""
    return jsonify({
        "types": [
            "None", "UNC (Unified Coarse)", "UNF (Unified Fine)", "M (ISO Metric)",
            "MF (ISO Metric Fine)", "STI (Helicoil Insert)", "Keensert",
            "UNEF (Unified Extra Fine)", "BSW (British Whitworth)", "BSF (British Fine)",
            "NPT (National Pipe Taper)", "NPTF (Dryseal Pipe)", "BSPT (British Pipe Taper)",
            "BSPP (British Pipe Parallel)", "Tr (Trapezoidal)", "ACME", "Buttress", "Custom",
        ],
        "sizes": {
            "M (ISO Metric)": [
                "M1", "M1.2", "M1.4", "M1.6", "M2", "M2.5", "M3", "M4", "M5",
                "M6", "M8", "M10", "M12", "M14", "M16", "M18", "M20", "M22",
                "M24", "M27", "M30", "M33", "M36", "M39", "M42", "M48", "M56", "M64",
            ],
            "MF (ISO Metric Fine)": [
                "M8x1", "M10x1", "M10x1.25", "M12x1.25", "M12x1.5",
                "M14x1.5", "M16x1.5", "M18x1.5", "M20x1.5", "M20x2",
                "M22x1.5", "M24x2", "M27x2", "M30x2", "M33x2", "M36x3",
            ],
            "UNC (Unified Coarse)": [
                "#0-80", "#1-64", "#2-56", "#3-48", "#4-40", "#5-40",
                "#6-32", "#8-32", "#10-24", "#12-24",
                "1/4-20", "5/16-18", "3/8-16", "7/16-14", "1/2-13",
                "9/16-12", "5/8-11", "3/4-10", "7/8-9", "1-8",
                "1-1/8-7", "1-1/4-7", "1-3/8-6", "1-1/2-6",
                "1-3/4-5", "2-4.5",
            ],
            "UNF (Unified Fine)": [
                "#0-80", "#1-72", "#2-64", "#3-56", "#4-48", "#5-44",
                "#6-40", "#8-36", "#10-32", "#12-28",
                "1/4-28", "5/16-24", "3/8-24", "7/16-20", "1/2-20",
                "9/16-18", "5/8-18", "3/4-16", "7/8-14", "1-12",
                "1-1/8-12", "1-1/4-12", "1-1/2-12",
            ],
            "UNEF (Unified Extra Fine)": [
                "1/4-32", "5/16-32", "3/8-32", "7/16-28", "1/2-28",
                "9/16-24", "5/8-24", "3/4-20", "7/8-20", "1-20",
            ],
            "STI (Helicoil Insert)": [
                "#2-56", "#4-40", "#6-32", "#8-32", "#10-24", "#10-32",
                "1/4-20", "1/4-28", "5/16-18", "5/16-24",
                "3/8-16", "3/8-24", "7/16-14", "7/16-20",
                "1/2-13", "1/2-20", "5/8-11", "5/8-18",
                "3/4-10", "3/4-16", "M3x0.5", "M4x0.7", "M5x0.8",
                "M6x1", "M8x1.25", "M10x1.5", "M12x1.75",
            ],
            "Keensert": [
                "#4-40", "#6-32", "#8-32", "#10-24", "#10-32",
                "1/4-20", "1/4-28", "5/16-18", "5/16-24",
                "3/8-16", "3/8-24", "7/16-14", "7/16-20",
                "1/2-13", "1/2-20", "5/8-11", "5/8-18",
                "3/4-10", "3/4-16", "M5x0.8", "M6x1", "M8x1.25",
                "M10x1.5", "M12x1.75",
            ],
            "BSW (British Whitworth)": [
                "1/16", "3/32", "1/8", "5/32", "3/16", "7/32", "1/4", "5/16",
                "3/8", "7/16", "1/2", "5/8", "3/4", "7/8", "1",
            ],
            "BSF (British Fine)": [
                "3/16", "7/32", "1/4", "5/16", "3/8", "7/16", "1/2",
                "9/16", "5/8", "3/4", "7/8", "1",
            ],
            "NPT (National Pipe Taper)": [
                "1/16", "1/8", "1/4", "3/8", "1/2", "3/4", "1", "1-1/4", "1-1/2", "2",
            ],
            "NPTF (Dryseal Pipe)": [
                "1/16", "1/8", "1/4", "3/8", "1/2", "3/4", "1", "1-1/4", "1-1/2", "2",
            ],
            "BSPT (British Pipe Taper)": [
                "1/16", "1/8", "1/4", "3/8", "1/2", "3/4", "1", "1-1/4", "1-1/2", "2",
            ],
            "BSPP (British Pipe Parallel)": [
                "1/16", "1/8", "1/4", "3/8", "1/2", "3/4", "1", "1-1/4", "1-1/2", "2",
            ],
        },
        "pitches": {
            "M (ISO Metric)": [
                "0.25", "0.3", "0.35", "0.4", "0.45", "0.5", "0.6", "0.7",
                "0.75", "0.8", "1.0", "1.25", "1.5", "1.75", "2.0", "2.5",
                "3.0", "3.5", "4.0", "4.5", "5.0", "5.5", "6.0",
            ],
            "MF (ISO Metric Fine)": [
                "0.2", "0.25", "0.35", "0.5", "0.75", "1.0", "1.25", "1.5", "2.0", "3.0",
            ],
            "UNC (Unified Coarse)": [
                "80 TPI", "72 TPI", "64 TPI", "56 TPI", "48 TPI", "44 TPI",
                "40 TPI", "32 TPI", "24 TPI", "20 TPI", "18 TPI", "16 TPI",
                "14 TPI", "13 TPI", "12 TPI", "11 TPI", "10 TPI", "9 TPI",
                "8 TPI", "7 TPI", "6 TPI", "5 TPI", "4.5 TPI", "4 TPI",
            ],
            "UNF (Unified Fine)": [
                "80 TPI", "72 TPI", "64 TPI", "56 TPI", "48 TPI", "44 TPI",
                "40 TPI", "36 TPI", "32 TPI", "28 TPI", "24 TPI", "20 TPI",
                "18 TPI", "16 TPI", "14 TPI", "12 TPI",
            ],
            "NPT (National Pipe Taper)": [
                "27 TPI", "18 TPI", "14 TPI", "11.5 TPI", "8 TPI",
            ],
        },
        "classes": [
            "None",
            "1A / 1B (Loose)",
            "2A / 2B (Standard)",
            "3A / 3B (Tight)",
            "4g6g / 6H (ISO Loose)",
            "6g / 6H (ISO Medium)",
            "4h6h / 5H (ISO Close)",
            "6e / 6H (ISO Sliding)",
            "Interference",
            "Custom",
        ],
    })


@app.route("/tolerance_options", methods=["GET"])
def tolerance_options():
    """Return standard tolerance options."""
    return jsonify({
        "types": [
            "None", "Linear +/-", "Limit", "Geometric (GD&T)",
            "Position", "Flatness", "Parallelism", "Perpendicularity",
            "Concentricity", "H7 (Hole)", "H8 (Hole)", "H9 (Hole)",
            "g6 (Shaft)", "f7 (Shaft)", "h6 (Shaft)", "h7 (Shaft)",
            "Custom"
        ],
        "values": [
            "None",
            "+/- 0.0005", "+/- 0.001", "+/- 0.002", "+/- 0.003", "+/- 0.005",
            "+/- 0.010", "+/- 0.015", "+/- 0.020", "+/- 0.030",
            "+0.000/-0.001", "+0.001/-0.000", "+0.000/-0.005", "+0.005/-0.000",
            "0.001 TIR", "0.002 TIR", "0.005 TIR", "0.010 TIR"
        ]
    })


@app.route("/db_stats", methods=["GET"])
@require_auth
def db_stats():
    """Return geometry DB statistics for the current user's models."""
    model_id = request.args.get("model_id")
    stats = get_db_stats(model_id=model_id)
    return jsonify(stats)


# ── Dev / test routes ────────────────────────────────────────────────────────

@app.route("/test_cube", methods=["POST"])
@require_auth
def test_cube():
    """Generate a CadQuery test cube, load into a transient (unsaved) state."""
    user_id = g.user_id
    # Use a fixed pseudo-UUID for test cube (not persisted to DB)
    test_model_id = f"test_cube_{user_id[:8]}"

    try:
        import cadquery as cq
        tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
        tmp_path = tmp.name
        tmp.close()
        box = cq.Workplane("XY").box(20, 20, 20)
        cq.exporters.export(box, tmp_path)

        state = manager.get_state(user_id, test_model_id)
        state.original_filename = "test_cube"
        state.model_uuid = test_model_id

        faces = load_step_xcaf(tmp_path, state, model_id=None)  # No DB writes for test
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
    return jsonify({"faces": faces})


@app.route("/test_sample", methods=["GET"])
@require_auth
def test_sample():
    """Load tests/sample.step directly."""
    user_id = g.user_id
    sample_model_id = f"sample_{user_id[:8]}"
    sample_path = os.path.join(app.root_path, 'tests', 'sample.step')
    if not os.path.exists(sample_path):
        return jsonify({"error": "Sample file not found"}), 404

    try:
        state = manager.get_state(user_id, sample_model_id)
        state.original_filename = "sample"
        state.model_uuid = sample_model_id
        faces = load_step_xcaf(sample_path, state, model_id=None)  # No DB writes for sample
        return jsonify({"faces": faces, "filename": "sample.step"})
    except Exception as e:
        print(f"Sample load error: {e}")
        return jsonify({"error": str(e)}), 500


# ── Admin routes ─────────────────────────────────────────────────────────────

@app.route("/api/admin/clear_metadata", methods=["POST"])
@require_auth
def admin_clear_metadata():
    """
    ADMIN TOOL — Nuke metadata from DB, STEP file, and/or in-memory state.
    Scope: "db" (DB only), "file" (file only), "all" (both).
    Always clears in-memory state to prevent re-injection on export.
    """
    data = request.get_json()
    target_uuid = data.get("uuid")
    scope = data.get("scope", "all")
    user_id = g.user_id

    if not target_uuid:
        return jsonify({"error": "UUID required"}), 400

    # Load model (verify ownership)
    model_row, state = _load_owned_model(target_uuid)
    if model_row is None:
        return jsonify({"error": "Model not found or not authorized"}), 403

    # If state doc is not loaded, load it from storage
    if state.doc is None:
        try:
            file_bytes = download_step_from_storage(model_row["storage_path"])
            tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
            try:
                tmp.write(file_bytes)
                tmp.close()
                state.reset()
                state.original_filename = model_row["original_filename"]
                state.model_uuid = target_uuid
                load_step_xcaf(tmp.name, state, model_id=target_uuid)
            finally:
                if os.path.exists(tmp.name):
                    os.remove(tmp.name)
        except Exception as e:
            return jsonify({"error": f"Failed to load model: {e}"}), 500

    deleted_count = 0
    message_parts = []

    # 1. Database cleanup
    if scope in ("db", "all"):
        if scope == "all":
            clear_model_metadata(target_uuid)
            message_parts.append(f"Deleted all DB entries for model {target_uuid[:8]}")
        else:
            hashes_to_delete = [h for h in state.face_hashes if h and h != "unknown"]
            delete_faces(target_uuid, hashes_to_delete)
            deleted_count = len(hashes_to_delete)
            message_parts.append(f"Deleted {deleted_count} DB entries")

    # 2. STEP file cleanup (strip from storage)
    if scope in ("file", "all"):
        storage_path = model_row.get("storage_path")
        if storage_path:
            try:
                file_bytes = download_step_from_storage(storage_path)
                content = file_bytes.decode("utf-8", errors="replace")
                original_len = len(content)

                # Strategy 2: Strip [SVFM:<base64>] tags
                content = re.sub(r"\[SVFM:.*?\]", "", content, flags=re.DOTALL)
                # Strategy 3: Strip comment blocks
                content = re.sub(
                    r"/\* __STEPVIEWER_META_START__ .*? __STEPVIEWER_META_END__ \*/",
                    "", content, flags=re.DOTALL
                )
                # Strategy 1: Blank DESCRIPTIVE_REPRESENTATION_ITEM payload
                entity_pattern = (
                    r"(DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*'"
                    r"(?:SVFM|StepViewerFaceMetadata)"
                    r"'\s*,\s*')[^']*('\s*\))"
                )
                content = re.sub(entity_pattern, r"\1\2", content, flags=re.DOTALL)

                stripped_chars = original_len - len(content)
                # Re-upload cleaned file
                upload_step_to_storage(user_id, target_uuid,
                                       model_row["original_filename"] + ".step",
                                       content.encode("utf-8"))
                message_parts.append(f"Stripped STEP file ({stripped_chars} chars removed)")
            except Exception as e:
                message_parts.append(f"File cleanup error: {e}")

    # 3. ALWAYS clear in-memory state
    state.face_meta = {}
    message_parts.append("Cleared in-memory metadata")

    return jsonify({
        "ok": True,
        "deleted_count": deleted_count,
        "message": " & ".join(message_parts),
    })


# ── Billing routes ───────────────────────────────────────────────────────────

@app.route("/api/billing/status", methods=["GET"])
@require_auth
def billing_status():
    """Return current plan, active projects, limit, and feature flags."""
    info = get_user_plan(g.user_id)
    return jsonify({
        "plan": info["plan"],
        "active_projects": info["active_projects"],
        "limit": info["limit"],
        "can_share": info["plan"] in ("pro", "growth"),
    })


@app.route("/api/billing/checkout", methods=["POST"])
@require_auth
def billing_checkout():
    """Create a Polar checkout session and return the URL."""
    data = request.get_json()
    plan = data.get("plan", "").lower()
    if plan not in ("pro", "growth"):
        return jsonify({"error": "Invalid plan. Choose 'pro' or 'growth'."}), 400

    try:
        checkout_url = create_checkout_session(g.user_id, plan)
        return jsonify({"checkout_url": checkout_url})
    except Exception as e:
        app.logger.error(f"Checkout creation failed: {e}", exc_info=True)
        return jsonify({"error": "Failed to create checkout session. Please try again."}), 500


@app.route("/api/billing/portal", methods=["POST"])
@require_auth
def billing_portal():
    """Create a Polar customer session and return the portal URL."""
    try:
        portal_url = create_customer_portal_url(g.user_id)
        return jsonify({"portal_url": portal_url})
    except Exception as e:
        app.logger.error(f"Portal session creation failed: {e}", exc_info=True)
        return jsonify({"error": "Failed to open billing portal. Please try again."}), 500


@app.route("/api/webhooks/polar", methods=["POST"])
def polar_webhook():
    """
    Polar.sh webhook receiver.
    Verifies signature, then dispatches event to billing handler.
    Always returns 200 to prevent Polar retries.
    """
    payload = request.get_data()

    if not verify_webhook_signature(payload, request.headers):
        app.logger.warning("Polar webhook: invalid signature")
        return jsonify({"error": "Invalid signature"}), 200

    try:
        event = request.get_json()
        handle_webhook_event(event)
    except Exception as e:
        app.logger.error(f"Webhook processing error: {e}", exc_info=True)

    # Always return 200 to prevent Polar from retrying
    return jsonify({"ok": True}), 200


# ── Misc ─────────────────────────────────────────────────────────────────────

@app.route("/mockups")
def mockups():
    """Serve the feature mockups page."""
    return render_template("mockups.html")


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5555))
    app.run(debug=debug, port=port)
