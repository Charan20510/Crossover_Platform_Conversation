"""
Social API views — same conventions as whatsapp/views.py and mail/views.py.

Auth: `Authorization: <social_token>` header (social account token), except
/social/account which uses the account token (mirrors /add-device, /mail/account).

Platform-specific work lives in adapters/<platform>.py, looked up via
ADAPTERS by slug — this module stays platform-agnostic.
"""

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


# ============================================================
# ADD SOCIAL ACCOUNT (account-level)
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def add_social_account(request):
    """POST /social/account — Auth: account token.
    Body: { "platform": "telegram", "name": "...", "credentials": {...} }
    `credentials` shape is platform-specific (see each adapters/<platform>.py)."""
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
    """POST /social/delete-account — Auth: account token. Body: {"token": "..."}"""
    account = get_account_from_token(request)
    if not account:
        return JsonResponse({"status": False, "reason": "account token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    token = body.get("token", "")
    deleted, _ = SocialAccount.objects.filter(account=account, social_token=token).delete()
    return JsonResponse({"status": deleted > 0})


# ============================================================
# SEND
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def send_social_message(request):
    """POST /social/send — Auth: social token.
    Body: { "target": "<chat id / channel / recipient>", "body": "..." }"""
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


# ============================================================
# WEBHOOK (called by the platform, not by the API user)
# ============================================================
@csrf_exempt
@require_http_methods(["POST", "GET"])
def social_webhook(request, platform, token):
    """/webhook/social/<platform>/<social_token>/ — receives inbound events.

    The social_token is embedded in the URL we register with the platform
    (setWebhook / Events API subscription URL), so the account is resolved
    directly from the path — no guessing from payload shape needed.

    GET is for platforms that verify the endpoint with a challenge param
    (Slack Events API, Meta) before sending real events.
    """
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

    # Slack's URL verification handshake arrives as a POST with "challenge".
    if payload.get("type") == "url_verification":
        return JsonResponse({"challenge": payload.get("challenge", "")})

    parsed = adapter.handle_webhook(social_account, payload)
    if not parsed:
        return JsonResponse({"status": True})  # nothing to store (e.g. non-message update)

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
