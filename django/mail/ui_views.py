"""
Mail browser UI views. Moved from api/ui_views.py.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.utils import get_account
from .models import Email, IncomingEmail


@login_required
def mail_dashboard(request):
    account = get_account(request)
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

    return render(request, "mail/dashboard.html", {
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
    account = get_account(request)
    mail_accounts = account.mail_accounts.order_by("-created_at")
    return render(request, "mail/accounts.html", {
        "account": account,
        "mail_accounts": mail_accounts,
    })


@login_required
def mail_compose_view(request):
    account = get_account(request)
    mail_accounts = account.mail_accounts.filter(status="connect")
    all_mail_accounts = account.mail_accounts.all()
    return render(request, "mail/compose.html", {
        "account": account,
        "mail_accounts": mail_accounts,
        "all_mail_accounts": all_mail_accounts,
    })


@login_required
def mail_sent_view(request):
    account = get_account(request)
    mail_filter = request.GET.get("mail_account", "")
    status_filter = request.GET.get("status", "")

    qs = Email.objects.filter(mail_account__account=account).order_by("-created_at")
    if mail_filter:
        qs = qs.filter(mail_account_id=mail_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, "mail/sent.html", {
        "account": account,
        "emails": qs[:200],
        "mail_accounts": account.mail_accounts.all(),
        "mail_filter": mail_filter,
        "status_filter": status_filter,
    })


@login_required
def mail_inbox_view(request):
    account = get_account(request)
    mail_filter = request.GET.get("mail_account", "")
    mail_ids = list(account.mail_accounts.values_list("id", flat=True))

    qs = IncomingEmail.objects.filter(mail_account_id__in=mail_ids).order_by("-received_at")
    if mail_filter:
        qs = qs.filter(mail_account_id=mail_filter)

    return render(request, "mail/inbox.html", {
        "account": account,
        "emails": qs[:200],
        "mail_accounts": account.mail_accounts.all(),
        "mail_filter": mail_filter,
    })
