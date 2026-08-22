"""
Mail client tests — the non-obvious logic only: pagination bounds, thread
grouping, the (folder, uid) dedup key, and the Delete = Trash / expunge rule.

The worker is never contacted: every test patches `mail.ui_views.call_mail_worker`,
which is the single seam all IMAP/SMTP traffic goes through.
"""

import base64
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account
from .models import IncomingEmail, MailAccount, thread_key_for


def make_email(box, uid, subject="Hello", folder="INBOX", **kwargs):
    return IncomingEmail.objects.create(
        mail_account=box, uid=str(uid), folder=folder,
        message_id=f"<{uid}@test>", sender="alice@example.com",
        sender_name="Alice", subject=subject,
        received_at=timezone.now(), **kwargs)


class MailTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("mailer", password="pw12345678")
        self.account = Account.objects.create(user=self.user, name="Mailer", email="m@example.com")
        self.box = MailAccount(
            account=self.account, name="Work", email_address="me@example.com",
            imap_host="imap.example.com", smtp_host="smtp.example.com",
            username="me@example.com",
            folder_map={"inbox": "INBOX", "trash": "Trash", "sent": "Sent"},
        )
        self.box.password = "secret"
        self.box.save()
        self.client.force_login(self.user)

    def post_json(self, name, payload):
        return self.client.post(reverse(name), data=json.dumps(payload),
                                content_type="application/json")


class ThreadKeyTests(TestCase):
    def test_reply_prefixes_stripped(self):
        for subject in ("Re: Budget", "RE: budget", "Fwd: Re: Budget", "Re[2]: Budget"):
            self.assertEqual(thread_key_for(subject), "budget", subject)

    def test_plain_subject_survives(self):
        self.assertEqual(thread_key_for("Quarterly Budget"), "quarterly budget")

    def test_empty_subject(self):
        self.assertEqual(thread_key_for(""), "")


class ModelTests(MailTestBase):
    def test_thread_key_computed_on_save(self):
        em = make_email(self.box, 1, subject="Re: Budget")
        self.assertEqual(em.thread_key, "budget")
        em.subject = "Fwd: Other"
        em.save()
        self.assertEqual(IncomingEmail.objects.get(pk=em.pk).thread_key, "other")

    def test_same_uid_in_two_folders_is_allowed(self):
        make_email(self.box, 7, folder="INBOX")
        make_email(self.box, 7, folder="Sent")
        self.assertEqual(IncomingEmail.objects.filter(uid="7").count(), 2)

    def test_duplicate_uid_in_one_folder_rejected(self):
        make_email(self.box, 7, folder="INBOX")
        with self.assertRaises(IntegrityError):
            make_email(self.box, 7, folder="INBOX")


class PaginationTests(MailTestBase):
    def setUp(self):
        super().setUp()
        for i in range(120):
            make_email(self.box, i, subject=f"Message {i}")

    def _list(self, **params):
        return self.client.get(reverse("mail:list"), params).json()

    def test_first_page_is_full_and_summary_matches(self):
        data = self._list(folder="INBOX", page=1)
        self.assertEqual(len(data["messages"]), 50)
        self.assertEqual(data["total"], 120)
        self.assertEqual(data["pages"], 3)
        self.assertEqual(data["summary"], "Messages 1 to 50 of 120")

    def test_last_page_is_partial(self):
        data = self._list(folder="INBOX", page=3)
        self.assertEqual(len(data["messages"]), 20)
        self.assertEqual(data["summary"], "Messages 101 to 120 of 120")

    def test_out_of_range_page_clamps_to_last(self):
        data = self._list(folder="INBOX", page=99)
        self.assertEqual(data["page"], 3)
        self.assertEqual(len(data["messages"]), 20)

    def test_empty_folder(self):
        data = self._list(folder="Junk")
        self.assertEqual(data["messages"], [])
        self.assertEqual(data["summary"], "No messages")

    def test_search_filters(self):
        data = self._list(folder="INBOX", q="Message 42")
        self.assertEqual(data["total"], 1)


class ThreadGroupingTests(MailTestBase):
    def setUp(self):
        super().setUp()
        make_email(self.box, 1, subject="Budget")
        make_email(self.box, 2, subject="Re: Budget")
        make_email(self.box, 3, subject="Fwd: Budget")
        make_email(self.box, 4, subject="Lunch")

    def test_flat_list_shows_every_message(self):
        data = self.client.get(reverse("mail:list"), {"folder": "INBOX"}).json()
        self.assertEqual(data["total"], 4)

    def test_threads_collapse_by_normalized_subject(self):
        data = self.client.get(reverse("mail:list"), {"folder": "INBOX", "threads": "1"}).json()
        self.assertEqual(data["total"], 2)
        counts = {m["thread_key"]: m["thread_count"] for m in data["messages"]}
        self.assertEqual(counts, {"budget": 3, "lunch": 1})

    def test_newest_message_represents_the_thread(self):
        data = self.client.get(reverse("mail:list"), {"folder": "INBOX", "threads": "1"}).json()
        newest = [m for m in data["messages"] if m["thread_key"] == "budget"][0]
        self.assertEqual(newest["uid"], "3")


class DeleteRuleTests(MailTestBase):
    """Delete moves to Trash everywhere; inside Trash it really expunges."""

    def test_delete_from_inbox_moves_to_trash(self):
        em = make_email(self.box, 1, folder="INBOX")
        with patch("mail.ui_views.call_mail_worker", return_value={"status": True}) as worker:
            res = self.post_json("mail:delete", {"ids": [str(em.id)]})
        self.assertTrue(res.json()["status"])
        self.assertEqual(res.json()["moved"], 1)
        self.assertEqual(res.json()["expunged"], 0)
        path, = [c.args[0] for c in worker.call_args_list]
        self.assertEqual(path, "/move")
        self.assertEqual(worker.call_args.kwargs["data"]["destination"], "Trash")
        # local row is dropped — UIDs are not preserved across folders
        self.assertFalse(IncomingEmail.objects.filter(id=em.id).exists())

    def test_delete_inside_trash_expunges(self):
        em = make_email(self.box, 2, folder="Trash")
        with patch("mail.ui_views.call_mail_worker", return_value={"status": True}) as worker:
            res = self.post_json("mail:delete", {"ids": [str(em.id)]})
        self.assertEqual(res.json()["expunged"], 1)
        self.assertEqual(res.json()["moved"], 0)
        self.assertEqual([c.args[0] for c in worker.call_args_list], ["/delete"])
        self.assertFalse(IncomingEmail.objects.filter(id=em.id).exists())

    def test_failed_worker_keeps_the_row(self):
        em = make_email(self.box, 3, folder="INBOX")
        with patch("mail.ui_views.call_mail_worker", return_value={"status": False, "reason": "nope"}):
            res = self.post_json("mail:delete", {"ids": [str(em.id)]})
        self.assertFalse(res.json()["status"])
        self.assertTrue(IncomingEmail.objects.filter(id=em.id).exists())

    def test_other_accounts_messages_are_not_touched(self):
        other = User.objects.create_user("other", password="pw12345678")
        other_account = Account.objects.create(user=other, name="O", email="o@example.com")
        other_box = MailAccount(account=other_account, name="B", email_address="b@example.com",
                                imap_host="i", smtp_host="s", username="b")
        other_box.password = "x"
        other_box.save()
        em = make_email(other_box, 9, folder="INBOX")
        with patch("mail.ui_views.call_mail_worker", return_value={"status": True}):
            res = self.post_json("mail:delete", {"ids": [str(em.id)]})
        self.assertFalse(res.json()["status"])
        self.assertTrue(IncomingEmail.objects.filter(id=em.id).exists())


class FlagAndMessageTests(MailTestBase):
    def test_opening_a_message_marks_it_seen(self):
        em = make_email(self.box, 1, is_read=False)
        with patch("mail.ui_views.call_mail_worker", return_value={"status": True}) as worker:
            data = self.client.get(reverse("mail:message", args=[em.id])).json()
        self.assertTrue(data["status"])
        self.assertTrue(IncomingEmail.objects.get(pk=em.pk).is_read)
        self.assertEqual(worker.call_args.kwargs["data"]["flags"], ["\\Seen"])

    def test_flag_unread_round_trips(self):
        em = make_email(self.box, 1, is_read=True)
        with patch("mail.ui_views.call_mail_worker", return_value={"status": True}) as worker:
            res = self.post_json("mail:flag", {"ids": [str(em.id)], "flag": "seen", "value": False})
        self.assertTrue(res.json()["status"])
        self.assertFalse(IncomingEmail.objects.get(pk=em.pk).is_read)
        self.assertIs(worker.call_args.kwargs["data"]["add"], False)


class SyncTests(MailTestBase):
    WORKER_EMAIL = {
        "uid": 12, "messageId": "<a@b>", "subject": "Re: Hello", "from": "bob@example.com",
        "fromName": "Bob", "to": "me@example.com", "cc": "", "date": "2026-01-01T10:00:00Z",
        "isRead": False, "isStarred": True, "hasAttachments": True,
        "attachments": [{"filename": "x.pdf", "size": 10, "contentType": "application/pdf"}],
        "text": "hi", "html": "", "size": 500,
    }

    def test_sync_upserts_on_folder_uid(self):
        worker_result = {"status": True, "count": 1, "total": 1, "emails": [self.WORKER_EMAIL]}
        with patch("mail.ui_views.call_mail_worker", return_value=worker_result):
            first = self.post_json("mail:sync_folder", {"folder": "INBOX"}).json()
            second = self.post_json("mail:sync_folder", {"folder": "INBOX"}).json()
        self.assertEqual(first["new"], 1)
        self.assertEqual(second["new"], 0)  # same (folder, uid) -> update, not insert
        self.assertEqual(IncomingEmail.objects.count(), 1)
        em = IncomingEmail.objects.get()
        self.assertEqual(em.thread_key, "hello")
        self.assertTrue(em.is_starred)
        self.assertEqual(em.attachments[0]["filename"], "x.pdf")

    def test_sync_folders_builds_folder_map(self):
        worker_result = {"status": True, "folders": [
            {"path": "INBOX", "specialUse": "\\Inbox", "flags": []},
            {"path": "[Gmail]/Trash", "specialUse": "\\Trash", "flags": []},
            {"path": "[Gmail]/Sent Mail", "specialUse": "\\Sent", "flags": []},
        ]}
        with patch("mail.ui_views.call_mail_worker", return_value=worker_result):
            data = self.post_json("mail:sync_folders", {}).json()
        self.box.refresh_from_db()
        self.assertEqual(self.box.folder_map["trash"], "[Gmail]/Trash")
        self.assertEqual(self.box.folder_path("sent"), "[Gmail]/Sent Mail")
        self.assertTrue(data["status"])


class SendTests(MailTestBase):
    def test_reply_builds_threading_headers_and_appends_to_sent(self):
        original = make_email(self.box, 1, subject="Budget", body_text="the numbers")
        original.references = "<root@x>"
        original.save()

        calls = []

        def fake_worker(path, method="POST", data=None, token=None):
            calls.append((path, data))
            return {"status": True, "messageId": "<new@x>"}

        with patch("mail.ui_views.call_mail_worker", side_effect=fake_worker):
            res = self.post_json("mail:send", {
                "mode": "reply", "reply_to": str(original.id), "text": "thanks",
            })
        self.assertTrue(res.json()["status"])
        paths = [p for p, _ in calls]
        self.assertEqual(paths[:3], ["/send", "/append", "/flag"])

        send = dict(calls[0][1])
        self.assertEqual(send["to"], "alice@example.com")
        self.assertEqual(send["subject"], "Re: Budget")
        self.assertEqual(send["inReplyTo"], "<1@test>")
        self.assertIn("<root@x>", send["references"])
        self.assertIn("> ", send["text"])  # quoted original

        append = dict(calls[1][1])
        self.assertEqual(append["folder"], "Sent")
        self.assertIn("In-Reply-To: <1@test>", append["raw"])

        self.assertTrue(IncomingEmail.objects.get(pk=original.pk).is_answered)

    def test_send_requires_a_recipient(self):
        res = self.post_json("mail:send", {"to": "", "text": "x"})
        self.assertFalse(res.json()["status"])


class UnreadFilterTests(MailTestBase):
    """B4 — the unread filter must be applied server-side, before pagination."""

    def setUp(self):
        super().setUp()
        for i in range(5):
            make_email(self.box, i, subject=f"M{i}", is_read=(i % 2 == 0))
        # 3 read (0,2,4), 2 unread (1,3)

    def test_unread_filter_applied_before_pagination(self):
        data = self.client.get(reverse("mail:list"), {"folder": "INBOX", "unread": "1"}).json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["summary"], "Messages 1 to 2 of 2")

    def test_without_the_flag_nothing_is_filtered(self):
        data = self.client.get(reverse("mail:list"), {"folder": "INBOX"}).json()
        self.assertEqual(data["total"], 5)


class ThreadExpansionTests(MailTestBase):
    def test_thread_returns_every_message_sharing_the_key(self):
        make_email(self.box, 1, subject="Budget")
        m2 = make_email(self.box, 2, subject="Re: Budget")
        make_email(self.box, 3, subject="Fwd: Budget")
        make_email(self.box, 4, subject="Lunch")  # different thread
        data = self.client.get(reverse("mail:thread", args=[m2.id])).json()
        self.assertEqual(len(data["messages"]), 3)

    def test_blank_thread_key_does_not_swallow_the_folder(self):
        em = make_email(self.box, 1, subject="")
        make_email(self.box, 2, subject="")  # also has a blank thread_key
        data = self.client.get(reverse("mail:thread", args=[em.id])).json()
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["id"], str(em.id))


class AttachmentDownloadTests(MailTestBase):
    def test_download_uses_our_stored_metadata_not_the_workers_echo(self):
        em = make_email(self.box, 1, attachments=[
            {"filename": "real.pdf", "size": 10, "contentType": "application/pdf", "partId": "2"}])
        content = base64.b64encode(b"hello world").decode()
        with patch("mail.ui_views.call_mail_worker", return_value={
            "status": True, "filename": "worker-lies.exe",
            "contentType": "application/x-msdownload", "contentB64": content,
        }) as worker:
            res = self.client.get(reverse("mail:attachment", args=[em.id, 0]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertIn("real.pdf", res["Content-Disposition"])
        self.assertEqual(b"".join(res.streaming_content), b"hello world")
        worker.assert_called_once()

    def test_missing_partid_returns_409_re_sync_hint(self):
        em = make_email(self.box, 1, attachments=[
            {"filename": "old.pdf", "size": 10, "contentType": "application/pdf"}])  # no partId
        with patch("mail.ui_views.call_mail_worker") as worker:
            res = self.client.get(reverse("mail:attachment", args=[em.id, 0]))
        self.assertEqual(res.status_code, 409)
        worker.assert_not_called()

    def test_oversize_attachment_rejected_before_worker_is_called(self):
        em = make_email(self.box, 1, attachments=[
            {"filename": "big.zip", "size": 999999999, "contentType": "application/zip", "partId": "2"}])
        with patch("mail.ui_views.call_mail_worker") as worker:
            res = self.client.get(reverse("mail:attachment", args=[em.id, 0]))
        self.assertEqual(res.status_code, 413)
        worker.assert_not_called()

    def test_out_of_range_index_404s(self):
        em = make_email(self.box, 1, attachments=[])
        res = self.client.get(reverse("mail:attachment", args=[em.id, 0]))
        self.assertEqual(res.status_code, 404)

    def test_cross_account_message_404s_without_calling_worker(self):
        other = User.objects.create_user("otherdl", password="pw12345678")
        other_account = Account.objects.create(user=other, name="O2", email="o2@example.com")
        other_box = MailAccount(account=other_account, name="B2", email_address="b2@example.com",
                                imap_host="i", smtp_host="s", username="b2")
        other_box.password = "x"
        other_box.save()
        em = make_email(other_box, 9, attachments=[
            {"filename": "x.pdf", "size": 10, "contentType": "application/pdf", "partId": "2"}])
        with patch("mail.ui_views.call_mail_worker") as worker:
            res = self.client.get(reverse("mail:attachment", args=[em.id, 0]))
        self.assertEqual(res.status_code, 404)
        worker.assert_not_called()


class AttachmentUploadTests(MailTestBase):
    def test_oversize_attachment_rejected_before_worker_is_called(self):
        big = base64.b64encode(b"x" * (11 * 1024 * 1024)).decode()
        with patch("mail.ui_views.call_mail_worker") as worker:
            res = self.post_json("mail:send", {
                "to": "x@example.com", "text": "hi",
                "attachments": [{"filename": "big.bin", "contentType": "application/octet-stream",
                                 "content_b64": big}],
            })
        self.assertFalse(res.json()["status"])
        worker.assert_not_called()

    def test_send_attaches_to_both_the_smtp_call_and_the_sent_copy(self):
        content = base64.b64encode(b"hello").decode()
        calls = []

        def fake_worker(path, method="POST", data=None, token=None):
            calls.append((path, data))
            return {"status": True, "messageId": "<new@x>"}

        with patch("mail.ui_views.call_mail_worker", side_effect=fake_worker):
            res = self.post_json("mail:send", {
                "to": "x@example.com", "text": "hi",
                "attachments": [{"filename": "a.txt", "contentType": "text/plain", "content_b64": content}],
            })
        self.assertTrue(res.json()["status"])
        send = dict(calls[0][1])
        self.assertEqual(send["attachments"][0]["filename"], "a.txt")
        self.assertEqual(send["attachments"][0]["content"], content)
        append = dict(calls[1][1])
        self.assertIn("a.txt", append["raw"])  # attached into the IMAP Sent copy too


class DraftRoundTripTests(MailTestBase):
    def test_resaving_a_draft_appends_then_deletes_the_old_one(self):
        old = make_email(self.box, 1, folder="Drafts", subject="Old draft")
        calls = []

        def fake_worker(path, method="POST", data=None, token=None):
            calls.append((path, data))
            return {"status": True, "uid": 99}

        with patch("mail.ui_views.call_mail_worker", side_effect=fake_worker):
            res = self.post_json("mail:draft", {
                "to": "x@example.com", "text": "updated", "draft_id": str(old.id),
            })
        self.assertTrue(res.json()["status"])
        self.assertEqual([p for p, _ in calls], ["/append", "/delete"])
        self.assertFalse(IncomingEmail.objects.filter(id=old.id).exists())

    def test_failed_append_leaves_the_old_draft_untouched(self):
        old = make_email(self.box, 1, folder="Drafts", subject="Old draft")
        with patch("mail.ui_views.call_mail_worker",
                   return_value={"status": False, "reason": "nope"}) as worker:
            res = self.post_json("mail:draft", {
                "to": "x@example.com", "text": "updated", "draft_id": str(old.id),
            })
        self.assertFalse(res.json()["status"])
        self.assertTrue(IncomingEmail.objects.filter(id=old.id).exists())
        self.assertEqual([c.args[0] for c in worker.call_args_list], ["/append"])


class AccessTests(MailTestBase):
    def test_views_require_login(self):
        self.client.logout()
        for name in ("mail:client", "mail:list", "mail:contacts", "mail:settings"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302, name)

    def test_client_page_renders(self):
        res = self.client.get(reverse("mail:client"))
        self.assertContains(res, "rc-shell")
        self.assertTemplateUsed(res, "mail/base_mail.html")

    def test_contacts_are_derived_from_senders(self):
        make_email(self.box, 1)
        make_email(self.box, 2)
        data = self.client.get(reverse("mail:contacts"), {"format": "json"}).json()
        self.assertEqual(data["contacts"], [
            {"email": "alice@example.com", "name": "Alice", "messages": 2,
             "last": data["contacts"][0]["last"]}])
