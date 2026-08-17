"""
API views — Fonnte-compatible WhatsApp Gateway endpoints.
"""

import json
import logging
import uuid
from datetime import datetime
from django.http import JsonResponse
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from .models import Account, Device, Message, Contact, MessageTemplate, AutoReply, IncomingMessage
from .auth import device_auth, account_auth, get_device_from_token, get_account_from_token
from .utils import (
    normalize_phone, to_jid, apply_variables, parse_delay, parse_targets,
    call_worker, generate_token,
)


# ============================================================
# HEALTH
# ============================================================
@csrf_exempt
@require_http_methods(["GET"])
def health(request):
    return JsonResponse({"status": "ok", "service": "wa_gateway"})


# ============================================================
# DEVICE CONNECTION
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def get_qr(request):
    """
    POST /qr
    Get QR code or pairing code to link a WhatsApp device.
    Body: { "type": "qr" | "code" | "qr-passkey", "whatsapp": "91XXXXXXXXXX" }
    Auth: device token
    """
    device = get_device_from_token(request)
    if not device:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    if device.status == "connect":
        return JsonResponse({"status": False, "reason": "device already connect"})

    body = {}
    if request.body:
        body = json.loads(request.body)

    conn_type = body.get("type", "qr")
    whatsapp = body.get("whatsapp", device.phone_number)

    try:
        result = call_worker("/qr", data={
            "deviceId": str(device.id),
            "phoneNumber": device.phone_number,
            "type": conn_type,
            "whatsapp": whatsapp,
        }, token=device.device_token)
        return JsonResponse(result)
    except Exception as e:
        logger.error("Worker error: %s", e)
        return JsonResponse({"status": False, "reason": "worker unreachable"})


@csrf_exempt
@require_http_methods(["POST"])
def disconnect_device(request):
    """
    POST /disconnect
    Disconnect the linked WhatsApp device.
    Auth: device token
    """
    device = get_device_from_token(request)
    if not device:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    try:
        call_worker("/disconnect", data={"deviceId": str(device.id)}, token=device.device_token)
    except Exception:
        pass

    device.status = "disconnect"
    device.save()
    return JsonResponse({"status": True, "reason": "device disconnected"})


@csrf_exempt
@require_http_methods(["POST"])
def delete_device(request):
    """
    POST /delete-device
    Disconnect and permanently delete a device.
    Auth: device token
    """
    device = get_device_from_token(request)
    if not device:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    try:
        call_worker("/disconnect", data={"deviceId": str(device.id)}, token=device.device_token)
    except Exception:
        pass

    device.delete()
    return JsonResponse({"status": True, "reason": "device deleted"})


# ============================================================
# SEND MESSAGE
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def send_message(request):
    """
    POST /send
    Send a WhatsApp message (single or bulk).

    Required: target (comma-separated numbers, supports |variables)
    Optional: message, url, file, schedule, delay, countryCode,
              location, typing, followup, inboxid, preview, etc.

    Auth: device token
    """
    device = get_device_from_token(request)
    if not device:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    if device.status != "connect":
        return JsonResponse({"status": False, "reason": "device not connected — scan QR first"})

    # Parse body from either JSON or form-data
    body = {}
    if request.content_type and "application/json" in request.content_type:
        body = json.loads(request.body) if request.body else {}
    else:
        body = request.POST.dict()

    target_str = body.get("target", "")
    if not target_str:
        return JsonResponse({"status": False, "reason": "target required"})

    message_text = body.get("message", "")
    delay = body.get("delay", "0")
    schedule = body.get("schedule", "0")
    country_code = body.get("countryCode", settings.DEFAULT_COUNTRY_CODE)
    typing = body.get("typing", "false") == "true"
    followup = body.get("followup", "0")
    inboxid = body.get("inboxid", "0")
    preview = body.get("preview", "true") == "true"

    # Attachment checks
    url = body.get("url", "")
    file = request.FILES.get("file")
    if (url or file) and not device.has_attachment_access:
        return JsonResponse({
            "status": False,
            "reason": "attachment requires super/advanced/ultra package"
        })

    # Quota check
    targets = parse_targets(target_str)
    if device.quota < len(targets):
        return JsonResponse({"status": False, "reason": "insufficient quota"})

    # Create message records + enqueue to worker
    message_ids = []
    target_numbers = []

    for i, target_info in enumerate(targets):
        phone = target_info["phone"]
        vars_list = target_info["vars"]
        msg_body = apply_variables(message_text, vars_list)
        normalized = normalize_phone(phone, country_code)

        msg = Message.objects.create(
            device=device,
            target=normalized,
            body=msg_body,
            status="pending" if int(schedule) > 0 else "process",
            scheduled_at=datetime.fromtimestamp(int(schedule)) if int(schedule) > 0 else None,
        )
        message_ids.append(str(msg.id))
        target_numbers.append(normalized)

        # Enqueue to Node.js worker
        worker_payload = {
            "deviceId": str(device.id),
            "phoneNumber": device.phone_number,
            "jid": to_jid(phone, country_code),
            "messageId": str(msg.id),
            "message": msg_body,
            "typing": typing,
            "inboxid": inboxid,
            "preview": preview,
            "delay_ms": parse_delay(delay) if int(schedule) == 0 else 0,
            "schedule": int(schedule),
            "followup": int(followup),
            "url": url,
        }

        if file:
            # In production: upload file to S3, pass URL to worker
            worker_payload["fileUrl"] = "uploaded_file_url_placeholder"

        try:
            worker_result = call_worker("/enqueue-send", data=worker_payload, token=device.device_token)
            if worker_result and not worker_result.get("status"):
                msg.status = "failed"
                msg.save()
                return JsonResponse({"status": False, "reason": worker_result.get("reason", "send failed")}, status=400)
        except Exception as e:
            msg.status = "failed"
            msg.save()
            logger.error("Worker unreachable: %s", e)
            return JsonResponse({"status": False, "reason": "worker unreachable"})

    # Decrement quota
    device.quota -= len(targets)
    device.messages_sent += len(targets)
    device.save()

    return JsonResponse({
        "status": True,
        "id": message_ids,
        "target": target_numbers,
        "process": "process",
    })


# ============================================================
# VALIDATE NUMBER
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def validate_number(request):
    """
    POST /validate
    Check if numbers are registered on WhatsApp.
    Body: { "target": "91xxx,91yyy", "countryCode": "91" }
    Auth: device token
    """
    device = get_device_from_token(request)
    if not device:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    target_str = body.get("target", "")
    country_code = body.get("countryCode", settings.DEFAULT_COUNTRY_CODE)

    if not target_str:
        return JsonResponse({"status": False, "reason": "target required"})

    targets = [t.strip() for t in target_str.split(",")][:500]

    try:
        result = call_worker("/validate", data={
            "deviceId": str(device.id),
            "numbers": [normalize_phone(t, country_code) for t in targets],
        }, token=device.device_token)
        return JsonResponse(result)
    except Exception as e:
        logger.error("Worker error: %s", e)
        return JsonResponse({"status": False, "reason": "worker unreachable"})


# ============================================================
# DEVICE PROFILE
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def device_profile(request):
    """
    POST /device
    Get device information (status, quota, package).
    Auth: device token
    """
    device = get_device_from_token(request)
    if not device:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    return JsonResponse({
        "status": True,
        "device": device.phone_number,
        "device_status": device.status,
        "expired": device.expires_at.strftime("%d %B %Y") if device.expires_at else "never",
        "messages": device.messages_sent,
        "name": device.name,
        "package": device.package,
        "quota": device.quota,
    })


# ============================================================
# ADD DEVICE (Account-level)
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def add_device(request):
    """
    POST /add-device
    Create a new device programmatically.
    Body: { "name": "My Device", "device": "91XXXXXXXXXX", "autoread": false }
    Auth: account token
    """
    account = get_account_from_token(request)
    if not account:
        return JsonResponse({"status": False, "reason": "account token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    name = body.get("name", "")
    phone = body.get("device", "")

    if not name or not phone:
        return JsonResponse({"status": False, "reason": "name and device required"})

    # Check free device limit
    free_devices = account.devices.filter(package="free").count()
    if free_devices >= 10:
        return JsonResponse({"status": False, "reason": "too much free device"})

    # Check uniqueness
    if Device.objects.filter(phone_number=phone).exists():
        return JsonResponse({"status": False, "reason": "device already exist"})

    device = Device.objects.create(
        account=account,
        name=name[:30],
        phone_number=phone,
        device_token=generate_token(),
        package="free",
        quota=1000,
        autoread=body.get("autoread", False),
    )

    return JsonResponse({
        "status": True,
        "device": phone,
        "name": device.name,
        "token": device.device_token,
        "autoread": "on" if device.autoread else "off",
        "package": "free",
    })


# ============================================================
# DELETE MESSAGE / RESCHEDULE
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def delete_message(request):
    """POST /delete-message — Cancel a queued message."""
    device = get_device_from_token(request)
    if not device:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    msg_id = body.get("id", "")

    try:
        msg = Message.objects.get(id=msg_id, device=device)
        call_worker("/delete-message", data={
            "deviceId": str(device.id),
            "messageId": str(msg.id),
        }, token=device.device_token)
        msg.status = "failed"
        msg.save()
        return JsonResponse({"status": True, "reason": "message deleted"})
    except Message.DoesNotExist:
        return JsonResponse({"status": False, "reason": "message not found"})


@csrf_exempt
@require_http_methods(["POST"])
def reschedule(request):
    """POST /reschedule — Change schedule/delay of a pending message."""
    device = get_device_from_token(request)
    if not device:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    msg_id = body.get("id", "")
    schedule = body.get("schedule", "0")

    try:
        msg = Message.objects.get(id=msg_id, device=device)
        if int(schedule) > 0:
            msg.scheduled_at = datetime.fromtimestamp(int(schedule))
        msg.save()
        call_worker("/reschedule", data={
            "deviceId": str(device.id),
            "messageId": str(msg.id),
            "schedule": int(schedule),
        }, token=device.device_token)
        return JsonResponse({"status": True, "reason": "message rescheduled"})
    except Message.DoesNotExist:
        return JsonResponse({"status": False, "reason": "message not found"})


# ============================================================
# TYPING INDICATOR
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def typing(request):
    """POST /typing — Trigger a typing indicator."""
    device = get_device_from_token(request)
    if not device:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    target = body.get("target", "")
    duration = body.get("duration", 1)

    try:
        call_worker("/typing", data={
            "deviceId": str(device.id),
            "jid": to_jid(target),
            "duration": int(duration),
        }, token=device.device_token)
        return JsonResponse({"status": True})
    except Exception as e:
        logger.error("Error: %s", e)
        return JsonResponse({"status": False, "reason": "internal error"})


# ============================================================
# WEBHOOK RECEIVER (from Node.js worker)
# ============================================================
@csrf_exempt
@require_http_methods(["POST"])
def webhook_receiver(request):
    """
    Internal endpoint: receives events from the Node.js Baileys worker.
    - Incoming messages
    - Message status updates
    - Device status changes

    This endpoint is called BY the worker, not by the API user.
    """
    body = json.loads(request.body) if request.body else {}
    event_type = body.get("event", "")
    device_id = body.get("deviceId", "")

    try:
        device = Device.objects.get(id=device_id)
    except (Device.DoesNotExist, ValidationError, ValueError):
        return JsonResponse({"status": False, "reason": "device not found"})

    if event_type == "incoming_message":
        # Store inbound message
        IncomingMessage.objects.create(
            device=device,
            sender=body.get("sender", ""),
            message=body.get("message", ""),
            name=body.get("name", ""),
            location=body.get("location"),
            attachment_url=body.get("url"),
            inbox_id=body.get("inboxid"),
            timestamp=datetime.fromtimestamp(body.get("timestamp", 0)) if body.get("timestamp") else None,
        )

        # Forward to user's webhook if configured
        if device.webhook_url:
            forward_webhook(device.webhook_url, body)

        # Check auto-reply rules
        if device.autoread:
            _check_auto_reply(device, body)

    elif event_type == "message_whatsapp_id":
        msg_id = body.get("id", "")
        whatsapp_id = body.get("whatsappId", "")
        if msg_id and whatsapp_id:
            try:
                msg = Message.objects.get(id=msg_id, device=device)
                msg.whatsapp_id = whatsapp_id
                msg.save(update_fields=["whatsapp_id"])
            except (Message.DoesNotExist, Exception):
                pass

    elif event_type == "message_status":
        msg_id = body.get("id", "")
        try:
            msg = Message.objects.get(whatsapp_id=msg_id, device=device)
            msg.status = body.get("status", msg.status)
            msg.state = body.get("state", msg.state)
            msg.save(update_fields=["status", "state"])
        except Message.DoesNotExist:
            pass
        except Exception:
            pass

    elif event_type == "message_status_by_uuid":
        # Used by the worker's 463 retry queue to update status via Django UUID
        msg_id = body.get("id", "")
        try:
            msg = Message.objects.get(id=msg_id, device=device)
            msg.status = body.get("status", msg.status)
            msg.state = body.get("state", msg.state)
            msg.save(update_fields=["status", "state"])
        except (Message.DoesNotExist, Exception):
            pass

        if device.webhook_url:
            forward_webhook(device.webhook_url, body)

    elif event_type == "device_status":
        status = body.get("status", "disconnect")
        device.status = "connect" if status == "connect" else "disconnect"
        device.save()

        if device.webhook_url:
            forward_webhook(device.webhook_url, body)

    return JsonResponse({"status": True})


def forward_webhook(url, payload):
    """Forward webhook payload to user's URL."""
    try:
        import requests
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass


def _check_auto_reply(device, body):
    """Check if an incoming message matches an auto-reply rule."""
    incoming_text = body.get("message", "").lower().strip()
    sender_jid = body.get("sender", "")

    # Check keyword rules
    for rule in device.auto_replies.all():
        if rule.keyword.lower() in incoming_text:
            _send_auto_reply(device, sender_jid, rule.reply)
            return

    # Check default rule
    default_rule = device.auto_replies.filter(is_default=True).first()
    if default_rule:
        _send_auto_reply(device, sender_jid, default_rule.reply)


def _send_auto_reply(device, sender_jid, reply_text):
    """Send an auto-reply through the worker."""
    try:
        call_worker("/enqueue-send", data={
            "deviceId": str(device.id),
            "jid": sender_jid,
            "messageId": str(uuid.uuid4()),
            "message": reply_text,
            "delay_ms": 0,
            "schedule": 0,
            "followup": 0,
            "typing": True,
            "inboxid": "0",
            "preview": True,
            "url": "",
        }, token=device.device_token)
    except Exception:
        pass


# ============================================================
# DASHBOARD (simple HTML)
# ============================================================
@csrf_exempt
@require_http_methods(["GET"])
def dashboard(request):
    """Simple dashboard showing devices and status."""
    from django.shortcuts import render
    accounts = Account.objects.all()
    devices = Device.objects.all()

    return render(request, "dashboard.html", {
        "accounts": accounts,
        "devices": devices,
    })
