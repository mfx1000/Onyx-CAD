"""
Billing and subscription management via Polar.sh.

Plan limits (concurrent active projects):
  Free:   3 active projects,  no sharing
  Pro:    10 active projects, sharing enabled
  Growth: 50 active projects, sharing enabled

Storage: Firestore (user_subscriptions collection + models collection).
"""
import os
import hmac
import hashlib
import base64
import requests

from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_admin import firestore
from core.firebase_init import get_firestore
from core.db import get_subscription, create_subscription, update_subscription
from core.firebase_init import get_user_email

# ── Config ───────────────────────────────────────────────────────────────────

POLAR_API_KEY = os.environ.get("POLAR_API_KEY", "")
POLAR_WEBHOOK_SECRET = os.environ.get("POLAR_WEBHOOK_SECRET", "")

POLAR_PRODUCT_IDS = {
    "pro": os.environ.get("POLAR_PRODUCT_PRO", ""),
    "growth": os.environ.get("POLAR_PRODUCT_GROWTH", ""),
}

PRODUCT_ID_TO_PLAN = {v: k for k, v in POLAR_PRODUCT_IDS.items() if v}

PLAN_LIMITS = {
    "free": 3,
    "pro": 10,
    "growth": 50,
}

# Max upload file size per plan (in bytes)
UPLOAD_LIMITS = {
    "free":   5  * 1024 * 1024,   # 5 MB
    "pro":    40 * 1024 * 1024,   # 40 MB
    "growth": 120 * 1024 * 1024,  # 120 MB
}

MAX_UPLOAD_SIZE = max(UPLOAD_LIMITS.values())  # 120 MB — Flask hard ceiling

if os.environ.get("POLAR_SANDBOX", "").lower() == "true":
    POLAR_API_BASE = "https://sandbox-api.polar.sh/v1"
else:
    POLAR_API_BASE = "https://api.polar.sh/v1"


# ── Active project counting ──────────────────────────────────────────────────

def count_active_projects(user_id: str) -> int:
    """Count non-archived models for a user."""
    db = get_firestore()
    docs = (
        db.collection("models")
        .where(filter=FieldFilter("user_id", "==", user_id))
        .where(filter=FieldFilter("is_archived", "==", False))
        .stream()
    )
    return sum(1 for _ in docs)


# ── Plan helpers ─────────────────────────────────────────────────────────────

def get_user_plan(user_id: str) -> dict:
    """
    Returns {'plan': 'free'|'pro'|'growth', 'active_projects': N, 'limit': N}.
    """
    sub = get_subscription(user_id)
    if sub is None:
        email = get_user_email(user_id)
        create_subscription(user_id, "free", email=email)
        plan = "free"
    else:
        plan = sub.get("plan", "free")
        # Backfill email if missing
        if not sub.get("email"):
            email = get_user_email(user_id)
            if email:
                update_subscription(user_id, {"email": email})

    active = count_active_projects(user_id)
    limit = PLAN_LIMITS.get(plan, 3)

    return {
        "plan": plan,
        "active_projects": active,
        "limit": limit,
    }


def check_can_upload(user_id: str) -> tuple[bool, str]:
    """
    Check if user can create a new project.
    
    Quota is enforced here during PROJECT CREATION.
    The limit is based on the user's plan (Free=3, Pro=10, Growth=50).
    """
    info = get_user_plan(user_id)
    
    # Enforce quota during project creation
    if info["active_projects"] >= info["limit"]:
        return (
            False,
            f"Active project limit reached ({info['active_projects']}/{info['limit']}). "
            f"Archive a project to free a slot, or upgrade your plan.",
        )
    return True, ""


def check_can_share(user_id: str) -> bool:
    info = get_user_plan(user_id)
    return info["plan"] in ("pro", "growth")


def get_upload_limit(user_id: str) -> int:
    """Return the max upload file size in bytes for the user's plan."""
    info = get_user_plan(user_id)
    return UPLOAD_LIMITS.get(info["plan"], UPLOAD_LIMITS["free"])


# ── Polar API integration ────────────────────────────────────────────────────

def create_checkout_session(user_id: str, plan: str) -> str:
    product_id = POLAR_PRODUCT_IDS.get(plan)
    if not product_id:
        raise ValueError(f"Unknown plan: {plan}")

    email = get_user_email(user_id)

    # Check if user has an existing subscription
    existing_sub = get_subscription(user_id)
    current_plan = existing_sub.get("plan", "free") if existing_sub else "free"
    polar_sub_id = existing_sub.get("polar_subscription_id") if existing_sub else None

    checkout_payload = {
        "products": [product_id],
        "success_url": os.environ.get("BILLING_SUCCESS_URL", "http://localhost:5555/app?payment=success"),
        "metadata": {"user_id": user_id},
        "external_customer_id": user_id,
        "customer_email": email or None,
    }

    # Free → paid upgrade: use subscription_id to upgrade existing subscription
    if current_plan == "free" and polar_sub_id:
        checkout_payload["subscription_id"] = polar_sub_id

    # Paid → paid upgrade (e.g. Pro → Growth):
    # Polar only allows subscription_id for free subscriptions.
    # For paid upgrades, don't send subscription_id or external_customer_id
    # (otherwise Polar rejects with AlreadyActiveSubscriptionError).
    # Also don't send customer_email as Polar matches customers by email too.
    # Mark it as an upgrade so the webhook can cancel the old subscription.
    elif current_plan in ("pro", "growth") and polar_sub_id:
        del checkout_payload["external_customer_id"]
        del checkout_payload["customer_email"]
        checkout_payload["metadata"]["upgrade_from"] = current_plan
        checkout_payload["metadata"]["old_polar_subscription_id"] = polar_sub_id

    resp = requests.post(
        f"{POLAR_API_BASE}/checkouts/",
        headers={
            "Authorization": f"Bearer {POLAR_API_KEY}",
            "Content-Type": "application/json",
        },
        json=checkout_payload,
        timeout=15,
    )

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Polar checkout failed ({resp.status_code}): {resp.text}")

    return resp.json().get("url", "")


def create_customer_portal_url(user_id: str) -> str:
    """Create a Polar customer session and return the portal URL."""
    return_url = os.environ.get("BILLING_PORTAL_RETURN_URL", "http://localhost:5555/app")

    resp = requests.post(
        f"{POLAR_API_BASE}/customer-sessions/",
        headers={
            "Authorization": f"Bearer {POLAR_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "external_customer_id": user_id,
            "return_url": return_url,
        },
        timeout=15,
    )

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Polar portal session failed ({resp.status_code}): {resp.text}")

    return resp.json().get("customer_portal_url", "")


def verify_webhook_signature(payload: bytes, headers) -> bool:
    """
    Verify webhook signature using Standard Webhooks spec.
    See: https://www.standardwebhooks.com/
    """
    if not POLAR_WEBHOOK_SECRET:
        return False

    webhook_id = headers.get("webhook-id", "")
    webhook_timestamp = headers.get("webhook-timestamp", "")
    webhook_signature = headers.get("webhook-signature", "")

    if not all([webhook_id, webhook_timestamp, webhook_signature]):
        return False

    # Build the message to sign
    message = f"{webhook_id}.{webhook_timestamp}.{payload.decode('utf-8')}"

    # Decode the base64 secret
    try:
        secret_bytes = base64.b64decode(POLAR_WEBHOOK_SECRET)
    except Exception:
        secret_bytes = POLAR_WEBHOOK_SECRET.encode()

    # Compute expected signature
    expected = hmac.new(secret_bytes, message.encode(), hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode()

    # Check if any of the provided signatures match
    for sig in webhook_signature.split(" "):
        if hmac.compare_digest(sig.strip(), f"v1,{expected_b64}"):
            return True

    return False


def cancel_polar_subscription(polar_sub_id: str):
    """Cancel a subscription on Polar via API (immediate cancellation)."""
    if not polar_sub_id:
        return
    try:
        resp = requests.delete(
            f"{POLAR_API_BASE}/subscriptions/{polar_sub_id}",
            headers={"Authorization": f"Bearer {POLAR_API_KEY}"},
            timeout=15,
        )
        if resp.status_code in (200, 204):
            print(f"[BILLING] Cancelled old Polar subscription: {polar_sub_id[:12]}...")
        else:
            print(f"[BILLING] Failed to cancel subscription ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"[BILLING] Error cancelling subscription: {e}")


def handle_webhook_event(event: dict):
    event_type = event.get("type", "")
    data = event.get("data", {})

    # Idempotency check: skip if we've already processed this event
    event_id = event.get("id", "")
    if event_id:
        db = get_firestore()
        processed_ref = db.collection("webhook_events").document(event_id)
        if processed_ref.get().exists:
            print(f"[WEBHOOK] Event {event_id} already processed, skipping")
            return
        # Mark as processed before handling (to prevent race conditions)
        processed_ref.set({
            "event_type": event_type,
            "processed_at": firestore.SERVER_TIMESTAMP,
        })

    user_id = None

    # Try metadata first (set during checkout creation)
    meta = data.get("metadata", {})
    user_id = meta.get("user_id")

    # Fallback to external_customer_id (set during checkout creation)
    if not user_id:
        user_id = data.get("external_customer_id")

    # Fallback to customer_metadata (deprecated, for backwards compat)
    if not user_id:
        customer_meta = data.get("customer_metadata", {})
        user_id = customer_meta.get("user_id")

    if not user_id:
        print(f"[WEBHOOK] No user_id found in event {event_type}")
        return

    polar_sub_id = data.get("id", "")

    if event_type in ("subscription.created", "subscription.updated"):
        product_id = data.get("product_id", "")
        plan = PRODUCT_ID_TO_PLAN.get(product_id, "free")
        status = data.get("status", "")
        if status in ("active", "trialing"):
            update_subscription(user_id, {"plan": plan, "polar_subscription_id": polar_sub_id})
            print(f"[WEBHOOK] {event_type}: user={user_id[:8]} plan={plan}")

            # Handle paid-to-paid upgrade: cancel the old subscription
            old_sub_id = meta.get("old_polar_subscription_id")
            if old_sub_id and old_sub_id != polar_sub_id:
                cancel_polar_subscription(old_sub_id)

        elif status in ("canceled", "expired", "past_due"):
            # Only downgrade if this is the user's CURRENT subscription
            current_sub = get_subscription(user_id)
            current_polar_id = current_sub.get("polar_subscription_id") if current_sub else None
            if current_polar_id == polar_sub_id:
                update_subscription(user_id, {"plan": "free", "polar_subscription_id": None})
                print(f"[WEBHOOK] {event_type} (status={status}): user={user_id[:8]} -> free")
            else:
                print(f"[WEBHOOK] {event_type} (status={status}): old subscription cancelled, ignoring")

    elif event_type == "subscription.canceled":
        # Only downgrade if this is the user's CURRENT subscription
        current_sub = get_subscription(user_id)
        current_polar_id = current_sub.get("polar_subscription_id") if current_sub else None
        if current_polar_id == polar_sub_id:
            update_subscription(user_id, {"plan": "free", "polar_subscription_id": None})
            print(f"[WEBHOOK] subscription.canceled: user={user_id[:8]} -> free")
        else:
            print(f"[WEBHOOK] subscription.canceled: old subscription cancelled, ignoring")
    else:
        print(f"[WEBHOOK] Unhandled event type: {event_type}")
