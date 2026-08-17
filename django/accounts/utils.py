"""
Shared account-lookup helper — every UI view needs the logged-in user's
Account, so it lives here rather than being copy-pasted into each app's views.
"""

from .models import Account


def get_account(request):
    """Return the Account for the logged-in user; create one if missing
    (handles superusers who have no Account row yet)."""
    try:
        return request.user.account
    except Account.DoesNotExist:
        return Account.objects.create(
            user=request.user,
            name=request.user.get_full_name() or request.user.username,
            email=request.user.email or f"{request.user.username}@local",
        )
