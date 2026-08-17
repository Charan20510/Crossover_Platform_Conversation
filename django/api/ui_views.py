"""
Browser UI views — Django auth (username/password), account-scoped.

Auth: django.contrib.auth User linked one-to-one to an Account.
Regular users (is_staff=False) cannot access /admin/ — that's enforced by
Django itself. All write-actions still delegate to the existing @csrf_exempt
API endpoints via fetch() on the client.
"""

import secrets
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import password_validation
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.utils import timezone as dj_timezone

from .models import (
    Account, Device, Message, IncomingMessage, MessageTemplate, AutoReply,
    MailAccount, Email, IncomingEmail,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_account(request):
    """Return the Account for the logged-in user; create one if missing
    (handles superusers who have no Account row yet)."""
    try:
        return request.user.account
    except Account.DoesNotExist:
        return Account.objects.create(
            user=request.user,
            name=request.user.get_full_name() or request.user.username,
            email=request.user.email or f"{request.user.username}@local",
        )


# ── auth views ────────────────────────────────────────────────────────────────

def signup_view(request):
    if request.user.is_authenticated:
        return redirect("ui:dashboard")

    errors = []
    form = {}

    if request.method == "POST":
        form = {k: request.POST.get(k, "").strip() for k in
                ("username", "email", "full_name", "password", "confirm")}

        # --- validate ---
        if not form["username"]:
            errors.append("Username is required.")
        elif User.objects.filter(username=form["username"]).exists():
            errors.append("That username is already taken.")

        if not form["email"]:
            errors.append("Email is required.")
        elif User.objects.filter(email=form["email"]).exists():
            errors.append("An account with this email already exists.")
        elif Account.objects.filter(email=form["email"]).exists():
            errors.append("An account with this email already exists.")

        if form["password"] != form["confirm"]:
            errors.append("Passwords do not match.")
        else:
            try:
                password_validation.validate_password(form["password"])
            except ValidationError as e:
                errors.extend(e.messages)

        if not errors:
            # Create Django user (hashed password, is_staff=False)
            user = User.objects.create_user(
                username=form["username"],
                email=form["email"],
                password=form["password"],
            )
            first, *rest = (form["full_name"].split(" ", 1) + [""])[:2]
            user.first_name = first
            user.last_name = rest[0] if rest else ""
            user.save(update_fields=["first_name", "last_name"])

            # Create linked Account (auto-generates account_token)
            Account.objects.create(
                user=user,
                name=form["full_name"] or form["username"],
                email=form["email"],
            )

            login(request, user)
            return redirect("ui:dashboard")

    return render(request, "ui/signup.html", {"errors": errors, "form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("ui:dashboard")

    error = None
    username_val = ""

    if request.method == "POST":
        username_val = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username_val, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get("next") or request.POST.get("next") or "ui:dashboard"
            # Only redirect to same-site next values
            if next_url.startswith("/"):
                return redirect(next_url)
            return redirect("ui:dashboard")
        else:
            error = "Incorrect username or password."

    return render(request, "ui/login.html", {
        "error": error,
        "username_val": username_val,
        "next": request.GET.get("next", ""),
    })


def logout_view(request):
    logout(request)
    return redirect("ui:login")


# ── profile ───────────────────────────────────────────────────────────────────

@login_required
def profile_view(request):
    account = _get_account(request)
    devices = account.devices.all()
    return render(request, "ui/profile.html", {
        "account": account,
        "user": request.user,
        "devices": devices,
    })


# ── dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    account = _get_account(request)
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

    return render(request, "ui/dashboard.html", {
        "account": account,
        "devices": devices,
        "total_sent": total_sent,
        "connected": connected,
        "pending_count": pending_count,
        "failed_count": failed_count,
        "recent_incoming": recent_incoming,
    })


# ── devices ───────────────────────────────────────────────────────────────────

@login_required
def devices_view(request):
    account = _get_account(request)
    devices = account.devices.order_by("-created_at")
    return render(request, "ui/devices.html", {
        "account": account,
        "devices": devices,
    })


# ── send ──────────────────────────────────────────────────────────────────────

@login_required
def send_view(request):
    account = _get_account(request)
    devices = account.devices.filter(status="connect")
    all_devices = account.devices.all()
    return render(request, "ui/send.html", {
        "account": account,
        "devices": devices,
        "all_devices": all_devices,
    })


# ── messages ──────────────────────────────────────────────────────────────────

@login_required
def messages_view(request):
    account = _get_account(request)
    device_filter = request.GET.get("device", "")
    status_filter = request.GET.get("status", "")

    qs = Message.objects.filter(device__account=account).order_by("-created_at")
    if device_filter:
        qs = qs.filter(device_id=device_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, "ui/messages.html", {
        "account": account,
        "messages": qs[:200],
        "devices": account.devices.all(),
        "device_filter": device_filter,
        "status_filter": status_filter,
    })


# ── inbox ─────────────────────────────────────────────────────────────────────

@login_required
def inbox_view(request):
    account = _get_account(request)
    device_filter = request.GET.get("device", "")
    device_ids = list(account.devices.values_list("id", flat=True))

    qs = IncomingMessage.objects.filter(device_id__in=device_ids).order_by("-received_at")
    if device_filter:
        qs = qs.filter(device_id=device_filter)

    # Mark seen
    request.session["inbox_seen_at"] = dj_timezone.now().isoformat()

    return render(request, "ui/inbox.html", {
        "account": account,
        "messages": qs[:200],
        "devices": account.devices.all(),
        "device_filter": device_filter,
    })


# ── templates ─────────────────────────────────────────────────────────────────

@login_required
def templates_view(request):
    account = _get_account(request)
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
    return render(request, "ui/templates.html", {
        "account": account,
        "devices": devices,
        "selected_device": selected_device,
        "templates": tpls,
    })


# ── auto-replies ──────────────────────────────────────────────────────────────

@login_required
def autoreplies_view(request):
    account = _get_account(request)
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
    return render(request, "ui/autoreplies.html", {
        "account": account,
        "devices": devices,
        "selected_device": selected_device,
        "rules": rules,
    })


# ── notifications feed ────────────────────────────────────────────────────────

@login_required
def notifications_feed(request):
    account = _get_account(request)
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


# ── mail dashboard ────────────────────────────────────────────────────────────

@login_required
def mail_dashboard(request):
    account = _get_account(request)
    mail_accounts = account.mail_accounts.all()

    total_sent = sum(m.emails_sent for m in mail_accounts)
    connected = sum(1 for m in mail_accounts if m.status == "connect")

    mail_ids = [m.id for m in mail_accounts]
    recent_incoming = (
        IncomingEmail.objects
        .filter(mail_account_id__in=mail_ids)
        .order_by("-received_at")[:5]
    )

    pending_count = Email.objects.filter(mail_account__account=account, status="pending").count()
    failed_count = Email.objects.filter(mail_account__account=account, status="failed").count()

    return render(request, "ui/mail_dashboard.html", {
        "account": account,
        "mail_accounts": mail_accounts,
        "total_sent": total_sent,
        "connected": connected,
        "pending_count": pending_count,
        "failed_count": failed_count,
        "recent_incoming": recent_incoming,
    })


@login_required
def mail_accounts_view(request):
    account = _get_account(request)
    mail_accounts = account.mail_accounts.order_by("-created_at")
    return render(request, "ui/mail_accounts.html", {
        "account": account,
        "mail_accounts": mail_accounts,
    })


@login_required
def mail_compose_view(request):
    account = _get_account(request)
    mail_accounts = account.mail_accounts.filter(status="connect")
    all_mail_accounts = account.mail_accounts.all()
    return render(request, "ui/mail_compose.html", {
        "account": account,
        "mail_accounts": mail_accounts,
        "all_mail_accounts": all_mail_accounts,
    })


@login_required
def mail_sent_view(request):
    account = _get_account(request)
    mail_filter = request.GET.get("mail_account", "")
    status_filter = request.GET.get("status", "")

    qs = Email.objects.filter(mail_account__account=account).order_by("-created_at")
    if mail_filter:
        qs = qs.filter(mail_account_id=mail_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, "ui/mail_sent.html", {
        "account": account,
        "emails": qs[:200],
        "mail_accounts": account.mail_accounts.all(),
        "mail_filter": mail_filter,
        "status_filter": status_filter,
    })


@login_required
def mail_inbox_view(request):
    account = _get_account(request)
    mail_filter = request.GET.get("mail_account", "")
    mail_ids = list(account.mail_accounts.values_list("id", flat=True))

    qs = IncomingEmail.objects.filter(mail_account_id__in=mail_ids).order_by("-received_at")
    if mail_filter:
        qs = qs.filter(mail_account_id=mail_filter)

    return render(request, "ui/mail_inbox.html", {
        "account": account,
        "emails": qs[:200],
        "mail_accounts": account.mail_accounts.all(),
        "mail_filter": mail_filter,
    })


# ── unified dashboard ─────────────────────────────────────────────────────────

@login_required
def unified_dashboard(request):
    account = _get_account(request)
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

    return render(request, "ui/unified_dashboard.html", {
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
