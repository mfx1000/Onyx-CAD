"""
Blog content system — stores blog posts in Firestore.
Used for SEO content generation and automated publishing.
"""
import uuid
from google.cloud import firestore
from firebase_admin import firestore as fs_admin
from core.firebase_init import get_firestore

COLL_POSTS = "blog_posts"


def create_post(
    title: str,
    slug: str,
    content: str,
    meta_description: str = "",
    status: str = "draft",
) -> str:
    """Create a new blog post. Returns post ID."""
    post_id = uuid.uuid4().hex[:12]
    db = get_firestore()
    db.collection(COLL_POSTS).document(post_id).set({
        "title": title,
        "slug": slug,
        "content": content,
        "meta_description": meta_description,
        "status": status,
        "created_at": fs_admin.SERVER_TIMESTAMP,
        "updated_at": fs_admin.SERVER_TIMESTAMP,
        "published_at": None,
    })
    return post_id


def get_post_by_slug(slug: str) -> dict | None:
    """Fetch a published post by slug."""
    db = get_firestore()
    docs = (
        db.collection(COLL_POSTS)
        .where(filter=firestore.FieldFilter("slug", "==", slug))
        .where(filter=firestore.FieldFilter("status", "==", "published"))
        .limit(1)
        .stream()
    )
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        return d
    return None


def get_post_by_id(post_id: str) -> dict | None:
    """Fetch a post by ID."""
    db = get_firestore()
    doc = db.collection(COLL_POSTS).document(post_id).get()
    if not doc.exists:
        return None
    d = doc.to_dict()
    d["id"] = doc.id
    return d


def list_posts(limit: int = 20, status: str = "published") -> list[dict]:
    """List posts, newest first."""
    db = get_firestore()
    query = db.collection(COLL_POSTS)
    if status:
        query = query.where(filter=firestore.FieldFilter("status", "==", status))
    query = query.order_by("published_at", direction="DESCENDING").limit(limit)
    
    results = []
    for doc in query.stream():
        d = doc.to_dict()
        d["id"] = doc.id
        results.append(d)
    return results


def update_post(post_id: str, fields: dict):
    """Update post fields."""
    fields["updated_at"] = fs_admin.SERVER_TIMESTAMP
    db = get_firestore()
    db.collection(COLL_POSTS).document(post_id).update(fields)


def publish_post(post_id: str):
    """Publish a draft post."""
    db = get_firestore()
    db.collection(COLL_POSTS).document(post_id).update({
        "status": "published",
        "published_at": fs_admin.SERVER_TIMESTAMP,
        "updated_at": fs_admin.SERVER_TIMESTAMP,
    })


def delete_post(post_id: str):
    """Delete a post."""
    db = get_firestore()
    db.collection(COLL_POSTS).document(post_id).delete()


def get_all_slugs() -> list[str]:
    """Get all published post slugs for sitemap."""
    posts = list_posts(limit=500, status="published")
    return [p["slug"] for p in posts if p.get("slug")]