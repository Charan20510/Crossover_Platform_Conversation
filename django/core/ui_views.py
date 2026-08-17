"""
Cross-channel UI views — unified overview, all-inbox, and the notification
bell feed. These are the only views that read both whatsapp and mail models,
which is why they live in core rather than in either feature app (keeps the
dependency direction one-way: whatsapp/mail never import each other or core's
UI code, only core imports them).
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from accounts.utils import get_account
from whatsapp.models import Message, IncomingMessage
from mail.models import Email, IncomingEmail


@login_required
def overview(request):
    account = get_account(request)
    devices = account.devices.all()
    mail_accounts = account.mail_accounts.all()

    wa_sent = sum(d.messages_sent for d in devices)
    mail_sent = sum(m.emails_sent for m in mail_accounts)
    wa_connected = sum(1 for d in devices if d.status == "connect")
    mail_connected = sum(1 for m in mail_accounts if m.status == "connect")

    pending_count = (
        Message.objects.filter(device__account=account, status="pending").count()
        + Email.objects.filter(mail_account__account=account, status="pending").count()
    )
    failed_count = (
        Message.objects.filter(device__account=account, status="failed").count()
        + Email.objects.filter(mail_account__account=account, status="failed").count()
    )

    device_ids = [d.id for d in devices]
    mail_ids = [m.id for m in mail_accounts]

    wa_feed = list(
        IncomingMessage.objects.filter(device_id__in=device_ids)
        .order_by("-received_at")[:5]
        .values("sender", "message", "received_at", "name")
    )
    for item in wa_feed:
        item["channel"] = "whatsapp"

    mail_feed = list(
        IncomingEmail.objects.filter(mail_account_id__in=mail_ids)
        .order_by("-received_at")[:5]
        .values("sender", "subject", "received_at", "sender_name")
    )
    for item in mail_feed:
        item["channel"] = "mail"
        item["message"] = item.pop("subject")
        item["name"] = item.pop("sender_name")

    recent_activity = sorted(
        wa_feed + mail_feed, key=lambda i: i["received_at"], reverse=True
    )[:8]

    return render(request, "core/overview.html", {
        "account": account,
        "devices": devices,
        "mail_accounts": mail_accounts,
        "wa_sent": wa_sent,
        "mail_sent": mail_sent,
        "wa_connected": wa_connected,
        "mail_connected": mail_connected,
        "pending_count": pending_count,
        "failed_count": failed_count,
        "recent_activity": recent_activity,
    })


@login_required
def all_inbox(request):
    """Merged WhatsApp + mail inbox — the Unified section's inbox page."""
    account = get_account(request)
    device_ids = list(account.devices.values_list("id", flat=True))
    mail_ids = list(account.mail_accounts.values_list("id", flat=True))

    wa_items = list(
        IncomingMessage.objects.filter(device_id__in=device_ids)
        .order_by("-received_at")[:100]
        .values("sender", "message", "received_at", "name")
    )
    for item in wa_items:
        item["channel"] = "whatsapp"

    mail_items = list(
        IncomingEmail.objects.filter(mail_account_id__in=mail_ids)
        .order_by("-received_at")[:100]
        .values("sender", "subject", "received_at", "sender_name")
    )
    for item in mail_items:
        item["channel"] = "mail"
        item["message"] = item.pop("subject")
        item["name"] = item.pop("sender_name")

    items = sorted(wa_items + mail_items, key=lambda i: i["received_at"], reverse=True)[:200]

    return render(request, "core/all_inbox.html", {
        "account": account,
        "items": items,
    })


@login_required
def notifications_feed(request):
    account = get_account(request)
    seen_at_str = request.session.get("inbox_seen_at")
    device_ids = list(account.devices.values_list("id", flat=True))
    mail_ids = list(account.mail_accounts.values_list("id", flat=True))

    qs = IncomingMessage.objects.filter(device_id__in=device_ids)
    mail_qs = IncomingEmail.objects.filter(mail_account_id__in=mail_ids)
    if seen_at_str:
        try:
            from datetime import datetime
            seen_at = datetime.fromisoformat(seen_at_str)
            qs = qs.filter(received_at__gt=seen_at)
            mail_qs = mail_qs.filter(received_at__gt=seen_at)
        except ValueError:
            pass

    count = qs.count() + mail_qs.count()
    latest = list(
        qs.order_by("-received_at")
        .values("sender", "message", "received_at", "name")[:5]
    )
    for item in latest:
        item["received_at"] = item["received_at"].isoformat() if item["received_at"] else None

    mail_latest = list(
        mail_qs.order_by("-received_at")
        .values("sender", "subject", "received_at", "sender_name")[:5]
    )
    for item in mail_latest:
        item["received_at"] = item["received_at"].isoformat() if item["received_at"] else None
        item["message"] = item.pop("subject")
        item["name"] = item.pop("sender_name")

    latest = sorted(latest + mail_latest, key=lambda i: i["received_at"] or "", reverse=True)[:5]

    return JsonResponse({"count": count, "latest": latest})
