
from core.auth import bearer_token
from .models import MailAccount

def get_mail_account_from_token(request):
    token = bearer_token(request)
    if not token:
        return None
    try:
        return MailAccount.objects.get(mail_token=token)
    except MailAccount.DoesNotExist:
        return None
