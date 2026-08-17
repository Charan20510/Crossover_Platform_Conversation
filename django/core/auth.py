"""
Shared token-extraction helper for token-based auth (Fonnte-compatible).
Each app's auth.py builds its own get_*_from_token() on top of this.
"""


def bearer_token(request):
    """
    Extract the raw token from the Authorization header.
    Fonnte sends: Authorization: <token> (no Bearer prefix), but
    "Bearer <token>" is also accepted.
    """
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None
    if auth.startswith("Bearer "):
        return auth[7:]
    return auth
