
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import SocialAccount, SocialMessage, PLATFORM_CHOICES
from .auth import get_social_account_from_token
from .adapters import get_adapter
from accounts.auth import get_account_from_token

logger = logging.getLogger(__name__)

VALID_PLATFORMS = {slug for slug, _ in PLATFORM_CHOICES}

@csrf_exempt
@require_http_methods(["POST"])
def add_social_account(request):
    account = get_account_from_token(request)
    if not account:
        return JsonResponse({"status": False, "reason": "account token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    platform = body.get("platform", "")
    name = body.get("name", "")
    credentials = body.get("credentials", {})

    if platform not in VALID_PLATFORMS:
        return JsonResponse({"status": False, "reason": f"platform must be one of {sorted(VALID_PLATFORMS)}"})
    if not name:
        return JsonResponse({"status": False, "reason": "name required"})

    adapter = get_adapter(platform)
    if not adapter:
        return JsonResponse({"status": False, "reason": f"{platform} adapter not implemented yet"})

    social_account = SocialAccount(account=account, platform=platform, name=name[:30])
    social_account.credentials = credentials
    social_account.save()

    result = adapter.connect(social_account)
    if not result.get("status"):
        social_account.delete()
        return JsonResponse(result)

    return JsonResponse({
        "status": True,
        "platform": platform,
        "name": social_account.name,
        "token": social_account.social_token,
        **{k: v for k, v in result.items() if k != "status"},
    })

@csrf_exempt
@require_http_methods(["POST"])
def delete_social_account(request):
    account = get_account_from_token(request)
    if not account:
        return JsonResponse({"status": False, "reason": "account token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    token = body.get("token", "")
    deleted, _ = SocialAccount.objects.filter(account=account, social_token=token).delete()
    return JsonResponse({"status": deleted > 0})

@csrf_exempt
@require_http_methods(["POST"])
def send_social_message(request):
    social_account = get_social_account_from_token(request)
    if not social_account:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    adapter = get_adapter(social_account.platform)
    if not adapter:
        return JsonResponse({"status": False, "reason": "adapter not implemented"})

    body = json.loads(request.body) if request.body else {}
    target = body.get("target", "")
    text = body.get("body", "")
    if not target or not text:
        return JsonResponse({"status": False, "reason": "target and body required"})

    result = adapter.send(social_account, target, text)
    if not result.get("status"):
        return JsonResponse(result)

    msg = SocialMessage.objects.create(
        social_account=social_account,
        direction="out",
        external_id=result.get("id", ""),
        target=target,
        body=text,
        status="sent",
    )
    return JsonResponse({"status": True, "id": str(msg.id), "external_id": result.get("id", "")})

@csrf_exempt
@require_http_methods(["POST", "GET"])
def social_webhook(request, platform, token):
    adapter = get_adapter(platform)
    if not adapter:
        return JsonResponse({"status": False, "reason": "unknown platform"}, status=404)

    try:
        social_account = SocialAccount.objects.get(social_token=token, platform=platform)
    except SocialAccount.DoesNotExist:
        return JsonResponse({"status": False, "reason": "unknown account"}, status=404)

    if request.method == "GET":
        challenge = request.GET.get("hub.challenge") or request.GET.get("challenge")
        if challenge:
            from django.http import HttpResponse
            return HttpResponse(challenge)
        return JsonResponse({"status": True})

    payload = json.loads(request.body) if request.body else {}

    if payload.get("type") == "url_verification":
        return JsonResponse({"challenge": payload.get("challenge", "")})

    parsed = adapter.handle_webhook(social_account, payload)
    if not parsed:
        return JsonResponse({"status": True})

    SocialMessage.objects.update_or_create(
        social_account=social_account,
        external_id=parsed["external_id"],
        defaults={
            "direction": "in",
            "target": parsed.get("target", ""),
            "body": parsed.get("body", ""),
            "status": parsed.get("status", "delivered"),
            "payload": payload,
        },
    )

    return JsonResponse({"status": True})
