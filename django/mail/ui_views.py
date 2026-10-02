
import base64
import io
import json
import logging
from datetime import datetime, timezone as dt_timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid, parseaddr

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.utils import get_account
from core.utils import call_mail_worker
from .models import Email, IncomingEmail, MailAccount

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 50
PAGE_SIZES = (25, 50, 100)
SYSTEM_FOLDERS = ("inbox", "drafts", "sent", "junk", "trash", "archive")
POLL_SYNC_LIMIT = 20
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_TOTAL_BYTES = 25 * 1024 * 1024

def _mailbox(request, mailbox_id=None):
    account = get_account(request)
    qs = account.mail_accounts.order_by("created_at")
    mailbox_id = mailbox_id or request.GET.get("mail_account") or request.session.get("mail_account_id")
    if mailbox_id:
        box = qs.filter(id=mailbox_id).first()
        if box:
            request.session["mail_account_id"] = str(box.id)
            return box
    return qs.first()

def _creds(box):
    return {
        "accountId": str(box.id),
        "imapHost": box.imap_host,
        "imapPort": box.imap_port,
        "imapSecure": box.imap_secure,
        "smtpHost": box.smtp_host,
        "smtpPort": box.smtp_port,
        "smtpSecure": box.smtp_secure,
        "username": box.username,
        "password": box.password,
    }

def _worker(box, path, **extra):
    try:
        return call_mail_worker(path, data={**_creds(box), **extra}, token=box.mail_token)
    except Exception as e:
        logger.error("mail worker %s failed: %s", path, e)
        return {"status": False, "reason": "mail worker unreachable"}

def _page_size(request):
    size = request.session.get("mail_page_size") or DEFAULT_PAGE_SIZE
    return size if size in PAGE_SIZES else DEFAULT_PAGE_SIZE

def _parse_date(value):
    if not value:
        return timezone.now()
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return timezone.now()
    return dt if dt.tzinfo else dt.replace(tzinfo=dt_timezone.utc)

LIST_FIELDS = (
    "id", "uid", "folder", "sender", "sender_name", "subject", "to_addrs", "cc",
    "is_read", "is_starred", "is_answered", "is_draft", "has_attachments",
    "size", "thread_key", "received_at", "message_id",
)

def _row(values):
    return {
        "id": str(values["id"]),
        "uid": values["uid"],
        "folder": values["folder"],
        "sender": values["sender"],
        "sender_name": values["sender_name"] or values["sender"],
        "subject": values["subject"] or "(no subject)",
        "to": values["to_addrs"],
        "cc": values["cc"],
        "is_read": values["is_read"],
        "is_starred": values["is_starred"],
        "is_answered": values["is_answered"],
        "is_draft": values["is_draft"],
        "has_attachments": values["has_attachments"],
        "size": values["size"],
        "thread_key": values["thread_key"],
        "date": values["received_at"].isoformat(),
        "thread_count": values.get("thread_count", 1),
    }

def messages_page(box, folder, page=1, per_page=DEFAULT_PAGE_SIZE, search="", threads=False,
                   unread_only=False):
    qs = IncomingEmail.objects.filter(mail_account=box, folder=folder)
    if search:
        qs = qs.filter(
            Q(subject__icontains=search) | Q(sender__icontains=search)
            | Q(sender_name__icontains=search) | Q(body_text__icontains=search)
        )
    if unread_only:
        qs = qs.filter(is_read=False)
    qs = qs.order_by("-received_at")

    if threads:
        collapsed, counts = [], {}
        for values in qs.values(*LIST_FIELDS):
            key = values["thread_key"] or str(values["id"])
            if key in counts:
                counts[key] += 1
                continue
            counts[key] = 1
            collapsed.append(values)
        for values in collapsed:
            values["thread_count"] = counts[values["thread_key"] or str(values["id"])]
        items = collapsed
    else:
        items = qs.values(*LIST_FIELDS)

    paginator = Paginator(items, per_page)
    page_obj = paginator.get_page(page)
    return [_row(v) for v in page_obj.object_list], page_obj

def folder_list(box):
    counts = {
        row["folder"]: row
        for row in IncomingEmail.objects.filter(mail_account=box)
        .values("folder")
        .annotate(total=Count("id"), unread=Count("id", filter=Q(is_read=False)))
    }
    fmap = box.folder_map or {}
    out, seen = [], set()
    for kind in SYSTEM_FOLDERS:
        path = fmap.get(kind) or ("INBOX" if kind == "inbox" else kind.capitalize())
        if kind == "archive" and "archive" not in fmap:
            continue
        seen.add(path)
        row = counts.get(path, {})
        out.append({
            "kind": kind, "name": kind.capitalize() if kind != "inbox" else "Inbox",
            "path": path, "total": row.get("total", 0), "unread": row.get("unread", 0),
        })
    for path, extra in ((p, c) for p, c in counts.items() if p not in seen):
        out.append({"kind": "other", "name": path.split("/")[-1], "path": path,
                    "total": extra.get("total", 0), "unread": extra.get("unread", 0)})
    return out

def _body(request):
    return json.loads(request.body) if request.body else {}

def _selected(request, ids):
    account = get_account(request)
    return list(IncomingEmail.objects.filter(
        id__in=[i for i in ids if i], mail_account__account=account))

def _upsert(box, folder, em):
    uid = str(em.get("uid") or "")
    if not uid:
        return False
    _, created = IncomingEmail.objects.update_or_create(
        mail_account=box, folder=folder, uid=uid,
        defaults={
            "message_id": (em.get("messageId") or "")[:255],
            "sender": (em.get("from") or "")[:255],
            "sender_name": (em.get("fromName") or "")[:255],
            "subject": (em.get("subject") or "")[:500],
            "body_text": em.get("text") or "",
            "body_html": em.get("html") or "",
            "to_addrs": (em.get("to") or "")[:500],
            "cc": (em.get("cc") or "")[:500],
            "is_read": bool(em.get("isRead")),
            "is_starred": bool(em.get("isStarred")),
            "is_answered": bool(em.get("isAnswered")),
            "is_draft": bool(em.get("isDraft")),
            "has_attachments": bool(em.get("hasAttachments")),
            "attachments": em.get("attachments") or [],
            "size": em.get("size") or 0,
            "in_reply_to": (em.get("inReplyTo") or "")[:255],
            "references": em.get("references") or "",
            "received_at": _parse_date(em.get("date")),
        },
    )
    return created

def _sync(box, folder, limit=DEFAULT_PAGE_SIZE, offset=0, search=""):
    result = _worker(box, "/fetch", folder=folder, limit=limit, offset=offset,
                     search=search, notify=False)
    if not result.get("status"):
        return result
    result["new"] = sum(1 for em in result.get("emails", []) if _upsert(box, folder, em))
    box.last_sync_at = timezone.now()
    box.save(update_fields=["last_sync_at"])
    return result

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
def mail_client(request):
    box = _mailbox(request)
    folder = request.GET.get("folder") or "INBOX"
    return render(request, "mail/client.html", {
        "account": get_account(request),
        "mailbox": box,
        "mailboxes": get_account(request).mail_accounts.order_by("created_at"),
        "folders": folder_list(box) if box else [],
        "folder": folder,
        "page_size": _page_size(request),
        "nav_page": "mail",
    })

@login_required
def mail_list(request):
    box = _mailbox(request)
    if not box:
        return JsonResponse({"status": False, "reason": "no mailbox configured"})
    folder = request.GET.get("folder") or "INBOX"
    rows, page_obj = messages_page(
        box, folder,
        page=request.GET.get("page") or 1,
        per_page=_page_size(request),
        search=(request.GET.get("q") or "").strip(),
        threads=request.GET.get("threads") in ("1", "true"),
        unread_only=request.GET.get("unread") in ("1", "true"),
    )
    total = page_obj.paginator.count
    return JsonResponse({
        "status": True,
        "folder": folder,
        "messages": rows,
        "page": page_obj.number,
        "pages": page_obj.paginator.num_pages,
        "total": total,
        "start": page_obj.start_index(),
        "end": page_obj.end_index(),
        "summary": (f"Messages {page_obj.start_index()} to {page_obj.end_index()} of {total}"
                    if total else "No messages"),
        "folders": folder_list(box),
    })

@login_required
def mail_message(request, pk):
    account = get_account(request)
    em = get_object_or_404(IncomingEmail, pk=pk, mail_account__account=account)

    if not em.is_read:
        _worker(em.mail_account, "/flag", folder=em.folder, uids=[em.uid], flags=["\\Seen"], add=True)
        em.is_read = True
        em.save(update_fields=["is_read"])

    return JsonResponse({
        "status": True,
        "message": {
            **_row({f: getattr(em, f) for f in LIST_FIELDS}),
            "body_text": em.body_text,
            "body_html": em.body_html,
            "attachments": em.attachments or [],
            "message_id": em.message_id,
            "in_reply_to": em.in_reply_to,
            "references": em.references,
        },
    })

@login_required
def mail_thread(request, pk):
    account = get_account(request)
    em = get_object_or_404(IncomingEmail, pk=pk, mail_account__account=account)
    if em.thread_key:
        qs = IncomingEmail.objects.filter(
            mail_account=em.mail_account, folder=em.folder, thread_key=em.thread_key)
    else:
        qs = IncomingEmail.objects.filter(pk=em.pk)
    rows = qs.order_by("-received_at").values(*LIST_FIELDS)
    return JsonResponse({"status": True, "messages": [_row(v) for v in rows]})

@login_required
def mail_attachment(request, pk, index):
    account = get_account(request)
    em = get_object_or_404(IncomingEmail, pk=pk, mail_account__account=account)
    attachments = em.attachments or []
    if index < 0 or index >= len(attachments):
        raise Http404("attachment not found")
    meta = attachments[index]

    if not meta.get("partId"):
        return JsonResponse(
            {"status": False, "reason": "attachment metadata predates part tracking — re-sync this folder"},
            status=409)
    if (meta.get("size") or 0) > MAX_ATTACHMENT_BYTES:
        return JsonResponse({"status": False, "reason": "attachment too large"}, status=413)

    result = _worker(em.mail_account, "/attachment", folder=em.folder, uid=em.uid,
                     partId=meta["partId"], maxBytes=MAX_ATTACHMENT_BYTES)
    if not result.get("status"):
        return JsonResponse({"status": False, "reason": result.get("reason", "download failed")}, status=502)

    try:
        data = base64.b64decode(result.get("contentB64") or "")
    except Exception:
        return JsonResponse({"status": False, "reason": "corrupt attachment data"}, status=502)

    return FileResponse(
        io.BytesIO(data), as_attachment=True,
        filename=meta.get("filename") or "attachment",
        content_type=meta.get("contentType") or "application/octet-stream")

@login_required
@require_POST
def mail_sync_folder(request):
    box = _mailbox(request)
    if not box:
        return JsonResponse({"status": False, "reason": "no mailbox configured"})
    body = _body(request)
    result = _sync(box, body.get("folder") or "INBOX",
                   limit=int(body.get("limit") or _page_size(request)),
                   offset=int(body.get("offset") or 0),
                   search=body.get("search") or "")
    if not result.get("status"):
        return JsonResponse(result)
    return JsonResponse({"status": True, "new": result.get("new", 0),
                         "fetched": result.get("count", 0), "total": result.get("total", 0)})

@login_required
@require_POST
def mail_sync_folders(request):
    box = _mailbox(request)
    if not box:
        return JsonResponse({"status": False, "reason": "no mailbox configured"})
    result = _worker(box, "/folders")
    if not result.get("status"):
        return JsonResponse(result)

    fmap = {}
    for f in result.get("folders", []):
        path = f.get("path") or f.get("name")
        special = (f.get("specialUse") or "").lstrip("\\").lower()
        flags = [str(x).lstrip("\\").lower() for x in (f.get("flags") or [])]
        for kind in SYSTEM_FOLDERS:
            if kind == special or kind in flags or (path or "").lower() == kind:
                fmap.setdefault(kind, path)
    fmap.setdefault("inbox", "INBOX")
    box.folder_map = fmap
    box.save(update_fields=["folder_map"])
    return JsonResponse({"status": True, "folder_map": fmap,
                         "server_folders": result.get("folders", []),
                         "folders": folder_list(box)})

@login_required
def mail_poll(request):
    box = _mailbox(request)
    if not box:
        return JsonResponse({"status": False, "reason": "no mailbox configured"})
    folder = request.GET.get("folder") or "INBOX"
    result = _sync(box, folder, limit=POLL_SYNC_LIMIT)
    return JsonResponse({
        "status": bool(result.get("status")),
        "new": result.get("new", 0),
        "folders": folder_list(box),
    })

FLAG_FIELDS = {
    "seen": ("\\Seen", "is_read"),
    "flagged": ("\\Flagged", "is_starred"),
    "answered": ("\\Answered", "is_answered"),
}

@login_required
@require_POST
def mail_flag(request):
    body = _body(request)
    flag = body.get("flag", "seen")
    if flag not in FLAG_FIELDS:
        return JsonResponse({"status": False, "reason": "unknown flag"})
    add = bool(body.get("value", True))
    imap_flag, field = FLAG_FIELDS[flag]

    messages = _selected(request, body.get("ids") or [])
    if not messages:
        return JsonResponse({"status": False, "reason": "nothing selected"})

    for (box, folder), group in _grouped(messages).items():
        _worker(box, "/flag", folder=folder, uids=[m.uid for m in group],
                flags=[imap_flag], add=add)
        for m in group:
            setattr(m, field, add)
            m.save(update_fields=[field])
    return JsonResponse({"status": True, "count": len(messages)})

def _grouped(messages):
    groups = {}
    for m in messages:
        groups.setdefault((m.mail_account, m.folder), []).append(m)
    return groups

@login_required
@require_POST
def mail_move(request):
    body = _body(request)
    messages = _selected(request, body.get("ids") or [])
    destination = body.get("destination") or ""
    if not messages or not destination:
        return JsonResponse({"status": False, "reason": "ids and destination required"})
    return JsonResponse(_move(messages, destination))

def _move(messages, destination):
    moved, errors = 0, []
    for (box, folder), group in _grouped(messages).items():
        target = box.folder_path(destination, destination) if destination in SYSTEM_FOLDERS else destination
        if target == folder:
            continue
        result = _worker(box, "/move", folder=folder, uids=[m.uid for m in group],
                         destination=target)
        if not result.get("status"):
            errors.append(result.get("reason", "move failed"))
            continue
        IncomingEmail.objects.filter(id__in=[m.id for m in group]).delete()
        moved += len(group)
    return {"status": not errors, "moved": moved,
            **({"reason": "; ".join(errors)} if errors else {})}

@login_required
@require_POST
def mail_delete(request):
    messages = _selected(request, _body(request).get("ids") or [])
    if not messages:
        return JsonResponse({"status": False, "reason": "nothing selected"})

    expunged, errors = 0, []
    to_trash = []
    for (box, folder), group in _grouped(messages).items():
        if folder == box.folder_path("trash", "Trash"):
            result = _worker(box, "/delete", folder=folder, uids=[m.uid for m in group])
            if not result.get("status"):
                errors.append(result.get("reason", "expunge failed"))
                continue
            IncomingEmail.objects.filter(id__in=[m.id for m in group]).delete()
            expunged += len(group)
        else:
            to_trash.extend(group)

    moved = 0
    if to_trash:
        result = _move(to_trash, "trash")
        moved = result.get("moved", 0)
        if not result.get("status"):
            errors.append(result.get("reason", "move to trash failed"))

    return JsonResponse({"status": not errors, "moved": moved, "expunged": expunged,
                         **({"reason": "; ".join(errors)} if errors else {})})

def _quote(original, mode):
    if not original:
        return ""
    when = timezone.localtime(original.received_at).strftime("%Y-%m-%d %H:%M")
    who = original.sender_name or original.sender
    text = original.body_text or ""
    if mode == "forward":
        header = (f"\n\n-------- Forwarded message --------\n"
                  f"Subject: {original.subject}\nDate: {when}\n"
                  f"From: {original.sender}\nTo: {original.to_addrs}\n\n")
        return header + text
    quoted = "\n".join(f"> {line}" for line in text.splitlines())
    return f"\n\nOn {when}, {who} wrote:\n{quoted}"

def _subject_for(original, mode):
    subject = original.subject if original else ""
    if mode in ("reply", "reply_all"):
        return subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if mode == "forward":
        return f"Fwd: {subject}" if not subject.lower().startswith(("fwd:", "fw:")) else subject
    return subject

def _addr_list(*values):
    out = []
    for value in values:
        for part in str(value or "").replace(";", ",").split(","):
            addr = parseaddr(part)[1].strip()
            if addr and addr.lower() not in {a.lower() for a in out}:
                out.append(addr)
    return out

def _attachments(body):
    out, total = [], 0
    for item in body.get("attachments") or []:
        filename = item.get("filename") or "attachment"
        b64 = item.get("content_b64") or ""
        try:
            data = base64.b64decode(b64, validate=True)
        except Exception:
            raise ValueError(f"invalid attachment data: {filename}")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"attachment too large: {filename}")
        total += len(data)
        if total > MAX_ATTACHMENTS_TOTAL_BYTES:
            raise ValueError("attachments exceed the total size limit")
        out.append({
            "filename": filename,
            "contentType": item.get("contentType") or "application/octet-stream",
            "content_b64": b64,
            "data": data,
        })
    return out

def _draft_fields(request, body):
    account = get_account(request)
    mode = body.get("mode") or "new"
    original = None
    if body.get("reply_to"):
        original = IncomingEmail.objects.filter(
            id=body["reply_to"], mail_account__account=account).first()

    to = body.get("to")
    cc = body.get("cc", "")
    if original and to is None:
        to = original.sender
        if mode == "reply_all":
            cc = ", ".join(_addr_list(original.to_addrs, original.cc))
    subject = body.get("subject")
    if subject is None:
        subject = _subject_for(original, mode)
    text = body.get("text") or ""
    if body.get("quote", True) and original and mode in ("reply", "reply_all", "forward"):
        text += _quote(original, mode)
    html = body.get("html") or ""

    refs = ""
    in_reply_to = ""
    if original and mode in ("reply", "reply_all") and original.message_id:
        in_reply_to = original.message_id
        refs = " ".join(filter(None, [original.references, original.message_id]))
    return {
        "to": ", ".join(_addr_list(to)),
        "cc": ", ".join(_addr_list(cc)),
        "bcc": ", ".join(_addr_list(body.get("bcc", ""))),
        "subject": subject or "",
        "text": text,
        "html": html,
        "in_reply_to": in_reply_to,
        "references": refs,
        "original": original,
        "mode": mode,
        "attachments": _attachments(body),
    }

def _raw_message(box, fields, message_id=None):
    msg = EmailMessage()
    msg["From"] = box.email_address
    msg["To"] = fields["to"]
    if fields["cc"]:
        msg["Cc"] = fields["cc"]
    msg["Subject"] = fields["subject"] or "(no subject)"
    msg["Date"] = format_datetime(timezone.now())
    msg["Message-ID"] = message_id or make_msgid()
    if fields["in_reply_to"]:
        msg["In-Reply-To"] = fields["in_reply_to"]
    if fields["references"]:
        msg["References"] = fields["references"]
    msg.set_content(fields["text"] or "")
    if fields.get("html"):
        msg.add_alternative(fields["html"], subtype="html")
    for att in fields.get("attachments") or []:
        content_type = att.get("contentType") or "application/octet-stream"
        maintype, _, subtype = content_type.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(att["data"], maintype=maintype, subtype=subtype,
                           filename=att.get("filename") or "attachment")
    return msg.as_string(), msg["Message-ID"]

@login_required
@require_POST
def mail_send(request):
    box = _mailbox(request, _body(request).get("mail_account"))
    if not box:
        return JsonResponse({"status": False, "reason": "no mailbox configured"})
    body = _body(request)
    try:
        fields = _draft_fields(request, body)
    except ValueError as e:
        return JsonResponse({"status": False, "reason": str(e)})
    if not fields["to"]:
        return JsonResponse({"status": False, "reason": "recipient required"})

    email = Email.objects.create(
        mail_account=box, to_addr=fields["to"][:500], cc=fields["cc"][:500],
        bcc=fields["bcc"][:500], subject=fields["subject"][:500],
        body=fields["text"], status="process",
    )
    result = _worker(box, "/send", **{
        "from": box.email_address, "to": fields["to"], "cc": fields["cc"],
        "bcc": fields["bcc"], "subject": fields["subject"], "text": fields["text"],
        "html": fields["html"],
        "attachments": [
            {"filename": a["filename"], "content": a["content_b64"],
             "encoding": "base64", "contentType": a["contentType"]}
            for a in fields["attachments"]
        ],
        "inReplyTo": fields["in_reply_to"], "references": fields["references"],
    })
    if not result.get("status"):
        email.status = "failed"
        email.save(update_fields=["status"])
        return JsonResponse({"status": False, "reason": result.get("reason", "send failed")})

    email.status = "sent"
    email.message_id = result.get("messageId", "")
    email.sent_at = timezone.now()
    email.save(update_fields=["status", "message_id", "sent_at"])
    box.emails_sent += 1
    box.save(update_fields=["emails_sent"])

    if box.smtp_host.lower().endswith(("gmail.com", "googlemail.com")):
        appended = {"status": True}
    else:
        raw, _ = _raw_message(box, fields, email.message_id or None)
        appended = _worker(box, "/append", folder=box.folder_path("sent", "Sent"),
                           raw=raw, flags=["\\Seen"])

    original = fields["original"]
    if original and fields["mode"] in ("reply", "reply_all"):
        _worker(original.mail_account, "/flag", folder=original.folder,
                uids=[original.uid], flags=["\\Answered"], add=True)
        original.is_answered = True
        original.save(update_fields=["is_answered"])

    if body.get("draft_id"):
        _discard_draft(request, body["draft_id"])

    return JsonResponse({"status": True, "id": str(email.id),
                         "messageId": email.message_id,
                         "sent_appended": bool(appended.get("status"))})

def _discard_draft(request, draft_id):
    messages = _selected(request, [draft_id])
    if not messages:
        return False
    em = messages[0]
    if em.folder != em.mail_account.folder_path("drafts", "Drafts"):
        return False
    _worker(em.mail_account, "/delete", folder=em.folder, uids=[em.uid])
    em.delete()
    return True

@login_required
@require_POST
def mail_draft(request):
    box = _mailbox(request, _body(request).get("mail_account"))
    if not box:
        return JsonResponse({"status": False, "reason": "no mailbox configured"})
    body = _body(request)
    try:
        fields = _draft_fields(request, body)
    except ValueError as e:
        return JsonResponse({"status": False, "reason": str(e)})
    raw, _ = _raw_message(box, fields)
    result = _worker(box, "/append", folder=box.folder_path("drafts", "Drafts"),
                     raw=raw, flags=["\\Draft", "\\Seen"])
    if result.get("status") and body.get("draft_id"):
        _discard_draft(request, body["draft_id"])
    return JsonResponse(result)

@login_required
def mail_contacts(request):
    account = get_account(request)
    q = (request.GET.get("q") or "").strip()
    qs = IncomingEmail.objects.filter(mail_account__account=account).exclude(sender="")
    if q:
        qs = qs.filter(Q(sender__icontains=q) | Q(sender_name__icontains=q))
    rows = (qs.values("sender")
              .annotate(name=Max("sender_name"), messages=Count("id"), last=Max("received_at"))
              .order_by("-messages")[:500])
    contacts = [{"email": r["sender"], "name": r["name"] or r["sender"],
                 "messages": r["messages"], "last": r["last"]} for r in rows]

    if request.GET.get("format") == "json":
        return JsonResponse({"status": True, "contacts": [
            {**c, "last": c["last"].isoformat() if c["last"] else None} for c in contacts]})
    box = _mailbox(request)
    return render(request, "mail/contacts.html", {
        "account": account, "mailbox": box, "contacts": contacts, "q": q,
        "folders": folder_list(box) if box else [], "nav_page": "contacts",
    })

@login_required
def mail_settings(request):
    account = get_account(request)
    if request.method == "POST":
        return _settings_action(request, account)
    box = _mailbox(request)
    return render(request, "mail/settings.html", {
        "account": account,
        "mailbox": box,
        "mailboxes": account.mail_accounts.order_by("created_at"),
        "folders": folder_list(box) if box else [],
        "page_size": _page_size(request),
        "page_sizes": PAGE_SIZES,
        "nav_page": "settings",
    })

def _settings_action(request, account):
    body = _body(request)
    action = body.get("action", "")

    if action == "page_size":
        size = int(body.get("page_size") or DEFAULT_PAGE_SIZE)
        request.session["mail_page_size"] = size if size in PAGE_SIZES else DEFAULT_PAGE_SIZE
        return JsonResponse({"status": True, "page_size": request.session["mail_page_size"]})

    if action == "add":
        required = ("name", "email_address", "password", "imap_host", "smtp_host")
        missing = [f for f in required if not body.get(f)]
        if missing:
            return JsonResponse({"status": False, "reason": f"missing: {', '.join(missing)}"})
        box = MailAccount(
            account=account,
            name=body["name"][:30],
            email_address=body["email_address"],
            username=body.get("username") or body["email_address"],
            imap_host=body["imap_host"],
            imap_port=int(body.get("imap_port") or 993),
            imap_secure=bool(body.get("imap_secure", True)),
            smtp_host=body["smtp_host"],
            smtp_port=int(body.get("smtp_port") or 587),
            smtp_secure=bool(body.get("smtp_secure", False)),
        )
        box.password = body["password"]
        box.save()
        request.session["mail_account_id"] = str(box.id)
        return JsonResponse({"status": True, "id": str(box.id)})

    box = account.mail_accounts.filter(id=body.get("mail_account")).first()
    if not box:
        return JsonResponse({"status": False, "reason": "mailbox not found"})

    if action == "connect":
        result = _worker(box, "/connect")
        box.status = "connect" if result.get("status") else "disconnect"
        box.save(update_fields=["status"])
        return JsonResponse(result)

    if action == "delete":
        box.delete()
        request.session.pop("mail_account_id", None)
        return JsonResponse({"status": True})

    if action == "select":
        request.session["mail_account_id"] = str(box.id)
        return JsonResponse({"status": True})

    return JsonResponse({"status": False, "reason": "unknown action"})
