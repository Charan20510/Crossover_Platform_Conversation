
from core.auth import bearer_token
from .models import SocialAccount

def get_social_account_from_token(request):
    token = bearer_token(request)
    if not token:
        return None
    try:
        return SocialAccount.objects.get(social_token=token)
    except SocialAccount.DoesNotExist:
        return None
