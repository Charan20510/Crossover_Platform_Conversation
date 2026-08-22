
from .models import Account

def get_account(request):
    try:
        return request.user.account
    except Account.DoesNotExist:
        return Account.objects.create(
            user=request.user,
            name=request.user.get_full_name() or request.user.username,
            email=request.user.email or f"{request.user.username}@local",
        )
