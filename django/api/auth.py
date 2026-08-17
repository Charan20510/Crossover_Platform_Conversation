"""
Authentication helpers — token-based auth matching Fonnte's model.
"""

from functools import wraps
from django.http import JsonResponse
from .models import Device, Account, MailAccount


def get_device_from_token(request):
    """
    Extract device token from Authorization header.
    Fonnte sends: Authorization: <device_token> (no Bearer prefix)
    """
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None

    # Support both "Bearer TOKEN" and "TOKEN" formats
    token = auth
    if auth.startswith("Bearer "):
        token = auth[7:]

    try:
        return Device.objects.get(device_token=token)
    except Device.DoesNotExist:
        return None


def get_account_from_token(request):
    """Extract account token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None

    token = auth
    if auth.startswith("Bearer "):
        token = auth[7:]

    try:
        return Account.objects.get(account_token=token)
    except Account.DoesNotExist:
        return None


def get_mail_account_from_token(request):
    """Extract mail account token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None

    token = auth
    if auth.startswith("Bearer "):
        token = auth[7:]

    try:
        return MailAccount.objects.get(mail_token=token)
    except MailAccount.DoesNotExist:
        return None


def device_auth(view_func):
    """Decorator: require a valid device token."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        device = get_device_from_token(request)
        if not device:
            return JsonResponse(
                {"status": False, "reason": "token invalid"},
                status=401
            )
        request.device = device
        return view_func(request, *args, **kwargs)
    return wrapper


def account_auth(view_func):
    """Decorator: require a valid account token."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        account = get_account_from_token(request)
        if not account:
            return JsonResponse(
                {"status": False, "reason": "account token invalid"},
                status=401
            )
        request.account = account
        return view_func(request, *args, **kwargs)
    return wrapper
