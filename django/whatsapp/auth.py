
from core.auth import bearer_token
from .models import Device

def get_device_from_token(request):
    token = bearer_token(request)
    if not token:
        return None
    try:
        return Device.objects.get(device_token=token)
    except Device.DoesNotExist:
        return None
