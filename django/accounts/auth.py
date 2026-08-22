
from core.auth import bearer_token
from .models import Account

def get_account_from_token(request):
    token = bearer_token(request)
    if not token:
        return None
    try:
        return Account.objects.get(account_token=token)
    except Account.DoesNotExist:
        return None
