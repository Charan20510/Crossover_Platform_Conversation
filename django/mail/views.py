
import json
import logging
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import MailAccount, Email, IncomingEmail
from .auth import get_mail_account_from_token
from accounts.auth import get_account_from_token
from core.utils import call_mail_worker

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def mail_connect(request):
    mail_account = get_mail_account_from_token(request)
    if not mail_account:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    try:
        result = call_mail_worker("/connect", data={
            "accountId": str(mail_account.id),
            "imapHost": mail_account.imap_host,
            "imapPort": mail_account.imap_port,
            "imapSecure": mail_account.imap_secure,
            "username": mail_account.username,
            "password": mail_account.password,
        }, token=mail_account.mail_token)
    except Exception as e:
        logger.error("Mail worker unreachable: %s", e)
        return JsonResponse({"status": False, "reason": "mail worker unreachable"})

    mail_account.status = "connect" if result.get("status") else "disconnect"
    mail_account.save(update_fields=["status"])
    return JsonResponse(result)

@csrf_exempt
@require_http_methods(["POST"])
def mail_send(request):
    mail_account = get_mail_account_from_token(request)
    if not mail_account:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    to_addr = body.get("to", "")
    if not to_addr:
        return JsonResponse({"status": False, "reason": "to required"})

    subject = body.get("subject", "")
    text = body.get("text", "")
    html = body.get("html", "")
    cc = body.get("cc", "")
    bcc = body.get("bcc", "")

    email = Email.objects.create(
        mail_account=mail_account,
        to_addr=to_addr,
        cc=cc,
        bcc=bcc,
        subject=subject,
        body=text or html,
        status="process",
    )

    try:
        result = call_mail_worker("/send", data={
            "from": mail_account.email_address,
            "to": to_addr,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "text": text,
            "html": html,
            "smtpHost": mail_account.smtp_host,
            "smtpPort": mail_account.smtp_port,
            "smtpSecure": mail_account.smtp_secure,
            "username": mail_account.username,
            "password": mail_account.password,
        }, token=mail_account.mail_token)
    except Exception as e:
        email.status = "failed"
        email.save(update_fields=["status"])
        logger.error("Mail worker unreachable: %s", e)
        return JsonResponse({"status": False, "reason": "mail worker unreachable"})

    if result.get("status"):
        from django.utils import timezone as dj_timezone
        email.status = "sent"
        email.message_id = result.get("messageId", "")
        email.sent_at = dj_timezone.now()
        email.save(update_fields=["status", "message_id", "sent_at"])
        mail_account.emails_sent += 1
        mail_account.save(update_fields=["emails_sent"])
        return JsonResponse({"status": True, "id": str(email.id), "messageId": email.message_id})

    email.status = "failed"
    email.save(update_fields=["status"])
    return JsonResponse({"status": False, "reason": result.get("reason", "send failed")})

@csrf_exempt
@require_http_methods(["POST"])
def mail_sync(request):
    mail_account = get_mail_account_from_token(request)
    if not mail_account:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    folder = body.get("folder", "INBOX")
    limit = body.get("limit", 50)

    try:
        result = call_mail_worker("/fetch", data={
            "accountId": str(mail_account.id),
            "folder": folder,
            "limit": limit,
            "imapHost": mail_account.imap_host,
            "imapPort": mail_account.imap_port,
            "imapSecure": mail_account.imap_secure,
            "username": mail_account.username,
            "password": mail_account.password,
        }, token=mail_account.mail_token)
    except Exception as e:
        logger.error("Mail worker unreachable: %s", e)
        return JsonResponse({"status": False, "reason": "mail worker unreachable"})

    if not result.get("status"):
        return JsonResponse(result)

    from django.utils import timezone as dj_timezone
    new_count = 0
    for em in result.get("emails", []):
        uid = str(em.get("uid") or "")
        if not uid:
            continue
        _, created = IncomingEmail.objects.update_or_create(
            mail_account=mail_account,
            folder=folder,
            uid=uid,
            defaults={
                "message_id": str(em.get("messageId") or "")[:255],
                "sender": em.get("from", ""),
                "sender_name": em.get("fromName", ""),
                "subject": em.get("subject", ""),
                "body_text": em.get("text", ""),
                "body_html": em.get("html", ""),
                "is_read": em.get("isRead", False),
                "has_attachments": em.get("hasAttachments", False),
                "received_at": em.get("date") and datetime.fromisoformat(em["date"].replace("Z", "+00:00")) or dj_timezone.now(),
            },
        )
        if created:
            new_count += 1

    mail_account.last_sync_at = dj_timezone.now()
    mail_account.save(update_fields=["last_sync_at"])

    return JsonResponse({"status": True, "fetched": result.get("count", 0), "new": new_count})

@csrf_exempt
@require_http_methods(["POST"])
def add_mail_account(request):
    account = get_account_from_token(request)
    if not account:
        return JsonResponse({"status": False, "reason": "account token invalid"}, status=401)

    body = json.loads(request.body) if request.body else {}
    name = body.get("name", "")
    email_address = body.get("email_address", "")
    username = body.get("username") or email_address
    password = body.get("password", "")
    imap_host = body.get("imap_host", "")
    smtp_host = body.get("smtp_host", "")

    if not (name and email_address and username and password and imap_host and smtp_host):
        return JsonResponse({"status": False, "reason": "name, email_address, username, password, imap_host, smtp_host required"})

    mail_account = MailAccount(
        account=account,
        name=name[:30],
        email_address=email_address,
        username=username,
        imap_host=imap_host,
        imap_port=int(body.get("imap_port", 993)),
        imap_secure=bool(body.get("imap_secure", True)),
        smtp_host=smtp_host,
        smtp_port=int(body.get("smtp_port", 587)),
        smtp_secure=bool(body.get("smtp_secure", False)),
    )
    mail_account.password = password
    mail_account.save()

    return JsonResponse({
        "status": True,
        "name": mail_account.name,
        "email_address": mail_account.email_address,
        "token": mail_account.mail_token,
    })

@csrf_exempt
@require_http_methods(["POST"])
def delete_mail_account(request):
    mail_account = get_mail_account_from_token(request)
    if not mail_account:
        return JsonResponse({"status": False, "reason": "token invalid"}, status=401)

    mail_account.delete()
    return JsonResponse({"status": True, "reason": "mail account deleted"})

@csrf_exempt
@require_http_methods(["POST"])
def mail_webhook_receiver(request):
    body = json.loads(request.body) if request.body else {}
    event_type = body.get("event", "")
    account_id = body.get("accountId", "")

    try:
        mail_account = MailAccount.objects.get(id=account_id)
    except MailAccount.DoesNotExist:
        return JsonResponse({"status": False, "reason": "mail account not found"})

    if event_type == "account_status":
        status = body.get("status", "disconnect")
        mail_account.status = "connect" if status == "connect" else "disconnect"
        mail_account.save(update_fields=["status"])

    elif event_type == "incoming_email":
        IncomingEmail.objects.update_or_create(
            mail_account=mail_account,
            folder=body.get("folder") or "INBOX",
            uid=str(body.get("uid") or body.get("messageId") or "")[:50],
            defaults={
                "message_id": str(body.get("messageId") or "")[:255],
                "sender": body.get("from", ""),
                "subject": body.get("subject", ""),
                "body_text": body.get("text", ""),
                "body_html": body.get("html", ""),
                "has_attachments": body.get("hasAttachments", False),
            },
        )

    return JsonResponse({"status": True})
