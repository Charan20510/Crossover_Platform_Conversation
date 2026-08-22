
import uuid
from datetime import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST

from accounts.utils import get_account
from core.utils import contact_key, to_jid, call_worker
from .models import Message, IncomingMessage, MessageTemplate, AutoReply, Contact

MAX_UPLOAD_BYTES = 16 * 1024 * 1024

def chat_rows(account, device_id=None, limit=None, started_only=True):
    inbox = IncomingMessage.objects.filter(device__account=account)
    sent = Message.objects.filter(device__account=account)
    if device_id:
        inbox = inbox.filter(device_id=device_id)
        sent = sent.filter(device_id=device_id)

    started = (
        {contact_key(t) for t in sent.values_list("target", flat=True)}
        if started_only else None
    )

    rows = {}

    def touch(contact, when, body, direction, name="", device=None):
        if not contact or (started is not None and contact not in started):
            return
        row = rows.setdefault(contact, {
            "contact": contact, "name": "", "last_at": None,
            "last_body": "", "last_direction": direction,
            "inbound_count": 0, "device_id": None, "device_name": "",
        })
        if name and not row["name"]:
            row["name"] = name
        if device is not None and not row["device_id"]:
            row["device_id"], row["device_name"] = device
        if row["last_at"] is None or (when and when > row["last_at"]):
            row["last_at"] = when
            row["last_body"] = body
            row["last_direction"] = direction

    for m in inbox.order_by("-received_at").values(
        "contact", "sender", "message", "name", "received_at", "device_id", "device__name"
    ):
        c = m["contact"] or contact_key(m["sender"])
        touch(c, m["received_at"], m["message"], "in", m["name"],
              (m["device_id"], m["device__name"]))
        if c in rows:
            rows[c]["inbound_count"] += 1

    for m in sent.order_by("-created_at").values(
        "target", "body", "created_at", "device_id", "device__name"
    ):
        touch(contact_key(m["target"]), m["created_at"], m["body"], "out",
              device=(m["device_id"], m["device__name"]))

    saved_names = dict(
        Contact.objects.filter(device__account=account, phone__in=rows.keys())
        .exclude(name="").values_list("phone", "name")
    )
    for c, name in saved_names.items():
        rows[c]["name"] = name

    ordered = sorted(rows.values(), key=lambda r: r["last_at"], reverse=True)
    return ordered[:limit] if limit else ordered

def day_label(dt):
    local = dj_timezone.localtime(dt).date() if dj_timezone.is_aware(dt) else dt.date()
    today = dj_timezone.localdate()
    delta = (today - local).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    return local.strftime("%d %b %Y")

def thread_messages(account, contact, after=None, device_id=None):
    contact = contact_key(contact)
    inbox = IncomingMessage.objects.filter(device__account=account, contact=contact)
    sent = Message.objects.filter(device__account=account, target=contact)
    if device_id:
        inbox = inbox.filter(device_id=device_id)
        sent = sent.filter(device_id=device_id)
    if after:
        inbox = inbox.filter(received_at__gt=after)
        sent = sent.filter(created_at__gt=after)

    items = [
        {"id": str(m["id"]), "direction": "in", "body": m["message"],
         "at": m["received_at"], "status": "",
         "attachment_url": m["attachment_url"] or "", "filename": ""}
        for m in inbox.values("id", "message", "received_at", "attachment_url")
    ] + [
        {"id": str(m["id"]), "direction": "out", "body": m["body"],
         "at": m["created_at"], "status": m["status"],
         "attachment_url": m["attachment_url"] or "", "filename": m["filename"] or ""}
        for m in sent.values("id", "body", "created_at", "status", "attachment_url", "filename")
    ]
    items.sort(key=lambda i: i["at"])
    for i in items:
        i["day"] = day_label(i["at"]) if i["at"] else ""
    return items

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
def chats_view(request, contact=None):
    account = get_account(request)
    contact = contact_key(contact) if contact else ""

    devices = list(account.devices.all())
    device_filter = request.GET.get("device", "")
    show_all = request.GET.get("all") == "1"
    selected_device = next((d for d in devices if str(d.id) == device_filter), None) if device_filter else None
    filter_id = selected_device.id if selected_device else None

    chats = chat_rows(account, device_id=filter_id, started_only=not show_all)

    request.session["inbox_seen_at"] = dj_timezone.now().isoformat()

    connected = list(account.devices.filter(status="connect"))
    active = next((c for c in chats if c["contact"] == contact), None)
    if selected_device and selected_device.status == "connect":
        device = selected_device
    else:
        device = next((d for d in connected if active and str(d.id) == str(active["device_id"])), None)
        device = device or (connected[0] if connected else None)

    return render(request, "whatsapp/chats.html", {
        "account": account,
        "chats": chats,
        "active": active,
        "contact": contact,
        "thread": thread_messages(account, contact, device_id=filter_id) if contact else [],
        "send_token": device.device_token if device else "",
        "send_device": device,
        "can_attach": bool(device and device.has_attachment_access),
        "devices": devices,
        "selected_device": selected_device,
        "device_filter": device_filter,
        "show_all": show_all,
    })

@login_required
def chats_feed(request):
    account = get_account(request)
    contact = request.GET.get("contact", "")
    device_filter = request.GET.get("device", "")
    show_all = request.GET.get("all") == "1"
    selected_device = account.devices.filter(id=device_filter).first() if device_filter else None
    filter_id = selected_device.id if selected_device else None
    after = None
    if request.GET.get("after"):
        try:
            after = datetime.fromisoformat(request.GET["after"])
        except ValueError:
            after = None

    def chat_url(row):
        url = reverse("whatsapp:chat_detail", args=[row["contact"]])
        params = []
        if device_filter:
            params.append(f"device={device_filter}")
        if show_all:
            params.append("all=1")
        return f"{url}?{'&'.join(params)}" if params else url

    chats = [
        {**r, "last_at": r["last_at"].isoformat() if r["last_at"] else None,
         "device_id": str(r["device_id"]) if r["device_id"] else "",
         "url": chat_url(r)}
        for r in chat_rows(account, device_id=filter_id, started_only=not show_all)
    ]
    messages = []
    if contact:
        messages = [
            {**m, "at": m["at"].isoformat() if m["at"] else None}
            for m in thread_messages(account, contact, after=after, device_id=filter_id)
        ]
    return JsonResponse({"chats": chats, "messages": messages})

@login_required
@require_POST
def chat_upload(request):
    account = get_account(request)
    device_id = request.POST.get("device")
    device = account.devices.filter(id=device_id).first() if device_id else None
    if not device:
        return JsonResponse({"status": False, "reason": "device required"}, status=400)
    if not device.has_attachment_access:
        return JsonResponse({
            "status": False,
            "reason": "attachment requires super/advanced/ultra package",
        }, status=403)

    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"status": False, "reason": "file required"}, status=400)
    if f.size > MAX_UPLOAD_BYTES:
        return JsonResponse({"status": False, "reason": "file too large (max 16MB)"}, status=400)

    ext = f.name.rsplit(".", 1)[-1] if "." in f.name else ""
    stored_name = f"whatsapp/{uuid.uuid4()}.{ext}" if ext else f"whatsapp/{uuid.uuid4()}"
    path = default_storage.save(stored_name, f)
    url = request.build_absolute_uri("/" + settings.MEDIA_URL + path)

    return JsonResponse({"status": True, "url": url, "filename": f.name})

@login_required
@require_POST
def chats_sync(request):
    account = get_account(request)
    device_id = request.POST.get("device")
    device = account.devices.filter(id=device_id).first() if device_id else None
    if not device:
        return JsonResponse({"status": False, "reason": "device required"}, status=400)
    if device.status != "connect":
        return JsonResponse({"status": False, "reason": "device not connected"}, status=400)

    contacts = [r["contact"] for r in chat_rows(account, device_id=device.id, limit=30)]

    anchors = []
    for contact in contacts:
        oldest_in = (
            IncomingMessage.objects.filter(device=device, contact=contact)
            .exclude(inbox_id__isnull=True).exclude(inbox_id="")
            .order_by("received_at").values("sender", "inbox_id", "received_at").first()
        )
        oldest_out = (
            Message.objects.filter(device=device, target=contact)
            .exclude(whatsapp_id__isnull=True).exclude(whatsapp_id="")
            .order_by("created_at").values("target", "whatsapp_id", "created_at").first()
        )
        candidates = []
        if oldest_in:
            candidates.append({
                "jid": oldest_in["sender"], "id": oldest_in["inbox_id"], "fromMe": False,
                "at": oldest_in["received_at"],
            })
        if oldest_out:
            candidates.append({
                "jid": to_jid(oldest_out["target"]), "id": oldest_out["whatsapp_id"], "fromMe": True,
                "at": oldest_out["created_at"],
            })
        if not candidates:
            continue
        anchor = min(candidates, key=lambda c: c["at"])
        anchors.append({
            "jid": anchor["jid"], "id": anchor["id"], "fromMe": anchor["fromMe"],
            "timestamp": int(anchor["at"].timestamp()),
        })

    if not anchors:
        return JsonResponse({"status": True, "chats": 0})

    try:
        call_worker("/sync-history", data={
            "deviceId": str(device.id), "anchors": anchors,
        }, token=device.device_token)
    except Exception:
        return JsonResponse({"status": False, "reason": "worker unreachable"}, status=502)

    return JsonResponse({"status": True, "chats": len(anchors)})

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
