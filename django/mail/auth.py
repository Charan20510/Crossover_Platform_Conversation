"""
Mail-token authentication for the mail token API.
"""

from core.auth import bearer_token
from .models import MailAccount


def get_mail_account_from_token(request):
    """Extract mail account token from Authorization header."""
    token = bearer_token(request)
    if not token:
        return None
    try:
        return MailAccount.objects.get(mail_token=token)
    except MailAccount.DoesNotExist:
        return None
