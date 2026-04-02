"""
Flask authentication decorators — Firebase JWT verification.
"""
from functools import wraps
from flask import request, jsonify, g
from core.firebase_init import verify_token


def require_auth(f):
    """
    Reads Authorization: Bearer <token>, verifies the Firebase JWT,
    stores user_id in flask.g.user_id.
    Returns 401 if missing or invalid.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ", 1)[1]
        user_id = verify_token(token)
        if user_id is None:
            return jsonify({"error": "Invalid or expired token"}), 401

        g.user_id = user_id
        return f(*args, **kwargs)

    return decorated


def optional_auth(f):
    """
    Same as @require_auth but does NOT 401 if missing/invalid.
    Sets g.user_id to None instead.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            g.user_id = None
            return f(*args, **kwargs)

        token = auth_header.split(" ", 1)[1]
        g.user_id = verify_token(token)
        return f(*args, **kwargs)

    return decorated
