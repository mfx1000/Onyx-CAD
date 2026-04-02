"""
Database operations — Firestore edition.
All model/subscription queries go through Firestore.
"""
import uuid
from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_admin import firestore
from core.firebase_init import get_firestore

COLL_MODELS = "models"
COLL_SUBS = "user_subscriptions"


# ── Model CRUD ───────────────────────────────────────────────────────────────

def create_model(user_id: str, original_filename: str, storage_path: str) -> str:
    """Create a new model document. Returns the model UUID."""
    model_id = uuid.uuid4().hex
    db = get_firestore()
    db.collection(COLL_MODELS).document(model_id).set({
        "user_id": user_id,
        "original_filename": original_filename,
        "storage_path": storage_path,
        "is_public": False,
        "is_archived": False,
        "share_token": None,
        "created_at": firestore.SERVER_TIMESTAMP,
    })
    return model_id


def get_model_by_id(model_id: str, user_id: str) -> dict | None:
    """Fetch a model, scoped to user. Returns None if not found."""
    db = get_firestore()
    doc = db.collection(COLL_MODELS).document(model_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    if data.get("user_id") != user_id:
        return None
    result = {"id": doc.id, **data}
    return result


def get_public_model(model_id: str) -> dict | None:
    """Fetch a model if it's public, regardless of owner."""
    db = get_firestore()
    doc = db.collection(COLL_MODELS).document(model_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    if not data.get("is_public"):
        return None
    return {"id": doc.id, **data}


def get_model_by_share_token(share_token: str) -> dict | None:
    """Fetch a model by its share_token (only if public)."""
    db = get_firestore()
    docs = (
        db.collection(COLL_MODELS)
        .where(filter=FieldFilter("share_token", "==", share_token))
        .where(filter=FieldFilter("is_public", "==", True))
        .limit(1)
        .stream()
    )
    for doc in docs:
        return {"id": doc.id, **doc.to_dict()}
    return None


def list_user_models(user_id: str) -> list[dict]:
    """List all models for a user, newest first."""
    db = get_firestore()
    docs = (
        db.collection(COLL_MODELS)
        .where(filter=FieldFilter("user_id", "==", user_id))
        .order_by("created_at", direction="DESCENDING")
        .stream()
    )
    results = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        results.append(d)
    return results


def update_model(model_id: str, fields: dict):
    """Update specific fields on a model document."""
    db = get_firestore()
    db.collection(COLL_MODELS).document(model_id).update(fields)


def delete_model_doc(model_id: str):
    """Delete a model document and all its face_meta subdocuments."""
    db = get_firestore()
    # Delete face_meta docs for this model
    face_docs = (
        db.collection("face_meta")
        .where(filter=FieldFilter("model_id", "==", model_id))
        .stream()
    )
    batch = db.batch()
    count = 0
    for doc in face_docs:
        batch.delete(doc.reference)
        count += 1
        if count >= 400:  # Firestore batch limit is 500
            batch.commit()
            batch = db.batch()
            count = 0
    # Delete the model itself
    batch.delete(db.collection(COLL_MODELS).document(model_id))
    batch.commit()


# ── Subscription CRUD ────────────────────────────────────────────────────────

def get_subscription(user_id: str) -> dict | None:
    """Fetch subscription doc for a user."""
    db = get_firestore()
    doc = db.collection(COLL_SUBS).document(user_id).get()
    if not doc.exists:
        return None
    return doc.to_dict()


def create_subscription(user_id: str, plan: str = "free", email: str = ""):
    """Create a default free subscription for a user."""
    db = get_firestore()
    db.collection(COLL_SUBS).document(user_id).set({
        "plan": plan,
        "polar_subscription_id": None,
        "email": email,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })


def update_subscription(user_id: str, fields: dict):
    """Update subscription fields."""
    fields["updated_at"] = firestore.SERVER_TIMESTAMP
    db = get_firestore()
    doc_ref = db.collection(COLL_SUBS).document(user_id)
    doc = doc_ref.get()
    if doc.exists:
        doc_ref.update(fields)
    else:
        fields["plan"] = fields.get("plan", "free")
        fields["polar_subscription_id"] = fields.get("polar_subscription_id")
        fields["created_at"] = firestore.SERVER_TIMESTAMP
        doc_ref.set(fields)
