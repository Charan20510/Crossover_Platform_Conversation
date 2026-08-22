
def bearer_token(request):
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None
    if auth.startswith("Bearer "):
        return auth[7:]
    return auth
