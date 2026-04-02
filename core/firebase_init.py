"""
Firebase Admin SDK initialization.
Provides: auth verification + Firestore client.
"""
import os
import logging
import threading
import firebase_admin
from firebase_admin import credentials, firestore, auth
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_initialized = False
_init_lock = threading.Lock()


def init_firebase():
    """Initialize Firebase Admin SDK (idempotent, thread-safe)."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return

        # Option 1: Load from base64-encoded env var (for production/Railway)
        cred_b64 = os.environ.get("FIREBASE_CREDENTIALS_JSON")
        if cred_b64:
            import json
            import base64
            cred_bytes = base64.b64decode(cred_b64)
            cred_dict = json.loads(cred_bytes)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            _initialized = True
            logger.info("Firebase Admin SDK initialized from env var (project: %s)", firebase_admin.get_app().project_id)
            return

        # Option 2: Load from file path (for local development)
        cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", "./firebase-credentials.json")
        if not os.path.exists(cred_path):
            raise FileNotFoundError(
                f"Firebase credentials not found at {cred_path}. "
                "Set FIREBASE_CREDENTIALS_JSON env var or download credentials file."
            )
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        _initialized = True
        logger.info("Firebase Admin SDK initialized from file (project: %s)", firebase_admin.get_app().project_id)


def get_firestore():
    """Return the Firestore client (initializes Firebase if needed)."""
    init_firebase()
    return firestore.client()


def verify_token(token: str) -> str | None:
    """
    Verify a Firebase ID token and return the user's UID.
    Returns None if the token is invalid or expired.
    """
    try:
        init_firebase()
        decoded = auth.verify_id_token(token, check_revoked=False, clock_skew_seconds=30)
        return decoded.get("uid")
    except Exception as e:
        logger.error("Token verification failed [%s]: %s", type(e).__name__, e)
        return None


def get_user_email(uid: str) -> str:
    """Get user email from Firebase Auth."""
    try:
        init_firebase()
        user = auth.get_user(uid)
        return user.email or ""
    except Exception:
        return ""
