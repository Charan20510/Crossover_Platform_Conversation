"""
WhatsApp browser UI views. Moved from api/ui_views.py.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from accounts.utils import get_account
from .models import Message, IncomingMessage, MessageTemplate, AutoReply


@login_required
def dashboard(request):
    account = get_account(request)
    devices = account.devices.all()

    total_sent = sum(d.messages_sent for d in devices)
    connected = sum(1 for d in devices if d.status == "connect")

    device_ids = [d.id for d in devices]
    recent_incoming = (
        IncomingMessage.objects
        .filter(device_id__in=device_ids)
        .order_by("-received_at")[:5]
    )

    pending_count = Message.objects.filter(device__account=account, status="pending").count()
    failed_count = Message.objects.filter(device__account=account, status="failed").count()

    return render(request, "whatsapp/dashboard.html", {
        "account": account,
        "devices": devices,
        "total_sent": total_sent,
        "connected": connected,
        "pending_count": pending_count,
        "failed_count": failed_count,
        "recent_incoming": recent_incoming,
    })


@login_required
def devices_view(request):
    account = get_account(request)
    devices = account.devices.order_by("-created_at")
    return render(request, "whatsapp/devices.html", {
        "account": account,
        "devices": devices,
    })


@login_required
def send_view(request):
    account = get_account(request)
    devices = account.devices.filter(status="connect")
    all_devices = account.devices.all()
    return render(request, "whatsapp/send.html", {
        "account": account,
        "devices": devices,
        "all_devices": all_devices,
    })


@login_required
def messages_view(request):
    account = get_account(request)
    device_filter = request.GET.get("device", "")
    status_filter = request.GET.get("status", "")

    qs = Message.objects.filter(device__account=account).order_by("-created_at")
    if device_filter:
        qs = qs.filter(device_id=device_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, "whatsapp/messages.html", {
        "account": account,
        "messages": qs[:200],
        "devices": account.devices.all(),
        "device_filter": device_filter,
        "status_filter": status_filter,
    })


@login_required
def inbox_view(request):
    from django.utils import timezone as dj_timezone

    account = get_account(request)
    device_filter = request.GET.get("device", "")
    device_ids = list(account.devices.values_list("id", flat=True))

    qs = IncomingMessage.objects.filter(device_id__in=device_ids).order_by("-received_at")
    if device_filter:
        qs = qs.filter(device_id=device_filter)

    # Mark seen
    request.session["inbox_seen_at"] = dj_timezone.now().isoformat()

    return render(request, "whatsapp/inbox.html", {
        "account": account,
        "messages": qs[:200],
        "devices": account.devices.all(),
        "device_filter": device_filter,
    })


@login_required
def templates_view(request):
    account = get_account(request)
    device_id = request.GET.get("device") or request.POST.get("device")
    devices = account.devices.all()
    selected_device = None
    if device_id:
        selected_device = devices.filter(id=device_id).first()

    if request.method == "POST" and selected_device:
        action = request.POST.get("action")
        if action == "delete":
            MessageTemplate.objects.filter(
                id=request.POST.get("tpl_id"), device__account=account
            ).delete()
        elif action in ("create", "edit"):
            name = request.POST.get("name", "").strip()
            content = request.POST.get("content", "").strip()
            tpl_id = request.POST.get("tpl_id")
            if name and content:
                if action == "edit" and tpl_id:
                    MessageTemplate.objects.filter(
                        id=tpl_id, device=selected_device
                    ).update(name=name, content=content)
                else:
                    MessageTemplate.objects.create(
                        device=selected_device, name=name, content=content
                    )
        return redirect(request.get_full_path())

    tpls = (
        MessageTemplate.objects.filter(device=selected_device).order_by("name")
        if selected_device else []
    )
    return render(request, "whatsapp/templates.html", {
        "account": account,
        "devices": devices,
        "selected_device": selected_device,
        "templates": tpls,
    })


@login_required
def autoreplies_view(request):
    account = get_account(request)
    device_id = request.GET.get("device") or request.POST.get("device")
    devices = account.devices.all()
    selected_device = None
    if device_id:
        selected_device = devices.filter(id=device_id).first()

    if request.method == "POST" and selected_device:
        action = request.POST.get("action")
        if action == "delete":
            AutoReply.objects.filter(
                id=request.POST.get("rule_id"), device__account=account
            ).delete()
        elif action in ("create", "edit"):
            keyword = request.POST.get("keyword", "").strip()
            reply = request.POST.get("reply", "").strip()
            is_default = request.POST.get("is_default") == "on"
            rule_id = request.POST.get("rule_id")
            if reply:
                if action == "edit" and rule_id:
                    AutoReply.objects.filter(
                        id=rule_id, device=selected_device
                    ).update(keyword=keyword, reply=reply, is_default=is_default)
                else:
                    AutoReply.objects.create(
                        device=selected_device,
                        keyword=keyword, reply=reply, is_default=is_default,
                    )
        return redirect(request.get_full_path())

    rules = (
        AutoReply.objects.filter(device=selected_device).order_by("keyword")
        if selected_device else []
    )
    return render(request, "whatsapp/autoreplies.html", {
        "account": account,
        "devices": devices,
        "selected_device": selected_device,
        "rules": rules,
    })
