"""Tests for the chat grouping/merge logic — the only non-trivial bit here."""

import json
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account
from django.contrib.auth.models import User

from .models import Device, IncomingMessage, Message, Contact
from .ui_views import chat_rows, thread_messages


class ChatSelectorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u1", password="x")
        self.account = Account.objects.create(user=self.user, name="Acct")
        self.device = Device.objects.create(
            account=self.account, name="D1", phone_number="919000000000", status="connect"
        )
        self.t0 = timezone.now() - timedelta(hours=5)

    def _in(self, digits, body, minutes, name="", jid=True):
        sender = f"{digits}@s.whatsapp.net" if jid else digits
        return IncomingMessage.objects.create(
            device=self.device, sender=sender, contact=digits, message=body, name=name,
            timestamp=self.t0 + timedelta(minutes=minutes),
            received_at=self.t0 + timedelta(minutes=minutes),
        )

    def _out(self, digits, body, minutes):
        return Message.objects.create(
            device=self.device, target=digits, body=body,
            created_at=self.t0 + timedelta(minutes=minutes),
        )

    def test_one_row_per_contact_ordered_by_recency(self):
        self._in("919876543210", "hi", 1)
        self._in("919876543210", "you there?", 2)
        self._in("919111111111", "hello", 10)
        self._out("919876543210", "started", 0)
        self._out("919111111111", "started", 0)

        rows = chat_rows(self.account)
        self.assertEqual([r["contact"] for r in rows], ["919111111111", "919876543210"])
        self.assertEqual(rows[1]["last_body"], "you there?")
        self.assertEqual(rows[1]["inbound_count"], 2)

    def test_outbound_only_conversation_appears(self):
        self._out("919222222222", "ping", 3)
        rows = chat_rows(self.account)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["last_direction"], "out")
        self.assertEqual(rows[0]["last_body"], "ping")

    def test_jid_and_digits_group_to_one_contact(self):
        # sender stored without the JID suffix and contact left blank (pre-backfill row)
        IncomingMessage.objects.create(
            device=self.device, sender="919876543210", message="raw digits",
            received_at=self.t0 + timedelta(minutes=1),
        )
        self._in("919876543210", "with jid", 2)
        self._out("919876543210", "reply", 3)

        rows = chat_rows(self.account)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["contact"], "919876543210")

    def test_thread_merges_both_directions_in_time_order(self):
        self._in("919876543210", "first", 1)
        self._out("919876543210", "second", 2)
        self._in("919876543210", "third", 3)

        msgs = thread_messages(self.account, "919876543210@s.whatsapp.net")
        self.assertEqual([m["body"] for m in msgs], ["first", "second", "third"])
        self.assertEqual([m["direction"] for m in msgs], ["in", "out", "in"])

    def test_thread_after_filter(self):
        self._in("919876543210", "old", 1)
        self._in("919876543210", "new", 5)
        msgs = thread_messages(
            self.account, "919876543210", after=self.t0 + timedelta(minutes=3)
        )
        self.assertEqual([m["body"] for m in msgs], ["new"])

    def test_chat_list_uncapped_one_row_per_contact(self):
        # Chats absorbed Inbox — the old 10-contact cap is gone, one row per
        # contact regardless of how many are active.
        for i in range(15):
            digits = f"9190000000{i:02d}"
            self._in(digits, f"msg {i}", i)
            self._in(digits, f"msg {i} again", i)
            self._out(digits, "started", 0)

        rows = chat_rows(self.account)
        contacts = [r["contact"] for r in rows]
        self.assertEqual(len(rows), 15)
        self.assertEqual(len(set(contacts)), 15)
        # newest first
        self.assertEqual(contacts[0], "9190000000" + "14")

    def test_saved_contact_name_outranks_push_name(self):
        self._in("919876543210", "hi", 1, name="WA Push Name")
        self._out("919876543210", "started", 0)
        Contact.objects.create(device=self.device, phone="919876543210", name="Mom")

        rows = chat_rows(self.account)
        self.assertEqual(rows[0]["name"], "Mom")

    def test_inbound_only_contact_hidden_by_default(self):
        self._in("919876543210", "stranger says hi", 1)
        rows = chat_rows(self.account)
        self.assertEqual(rows, [])

    def test_inbound_only_contact_shown_with_started_only_false(self):
        self._in("919876543210", "stranger says hi", 1)
        rows = chat_rows(self.account, started_only=False)
        self.assertEqual([r["contact"] for r in rows], ["919876543210"])

    def test_device_filter(self):
        other = Device.objects.create(
            account=self.account, name="D2", phone_number="919000000001"
        )
        self._in("919876543210", "on d1", 1)
        self._out("919876543210", "started", 0)
        IncomingMessage.objects.create(
            device=other, sender="919555555555@s.whatsapp.net", contact="919555555555",
            message="on d2", received_at=self.t0 + timedelta(minutes=2),
        )
        Message.objects.create(
            device=other, target="919555555555", body="started",
            created_at=self.t0 + timedelta(minutes=0),
        )
        rows = chat_rows(self.account, device_id=str(other.id))
        self.assertEqual([r["contact"] for r in rows], ["919555555555"])


class ChatViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u2", password="pw12345!")
        self.account = Account.objects.create(user=self.user, name="Acct2")
        self.device = Device.objects.create(
            account=self.account, name="D1", phone_number="919000000009", status="connect"
        )
        IncomingMessage.objects.create(
            device=self.device, sender="919876543210@s.whatsapp.net",
            contact="919876543210", message="hey",
        )
        Message.objects.create(device=self.device, target="919876543210", body="started")
        self.client.force_login(self.user)

    def test_chats_view_marks_inbox_seen(self):
        res = self.client.get(reverse("whatsapp:chats"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("inbox_seen_at", self.client.session)

    def test_chat_detail_renders_thread_and_token(self):
        res = self.client.get(reverse("whatsapp:chat_detail", args=["919876543210"]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "hey")
        self.assertContains(res, self.device.device_token)

    def test_chats_feed_json(self):
        res = self.client.get(reverse("whatsapp:chats_feed"), {"contact": "919876543210"})
        data = res.json()
        self.assertEqual(len(data["chats"]), 1)
        self.assertEqual(data["messages"][0]["body"], "hey")

    def test_chats_feed_rows_carry_server_built_url(self):
        res = self.client.get(reverse("whatsapp:chats_feed"))
        data = res.json()
        self.assertEqual(
            data["chats"][0]["url"],
            reverse("whatsapp:chat_detail", args=["919876543210"]),
        )

    def test_inbox_redirects_to_chats(self):
        res = self.client.get(reverse("whatsapp:inbox"))
        self.assertRedirects(res, reverse("whatsapp:chats"))


class ChatUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u3", password="pw12345!")
        self.account = Account.objects.create(user=self.user, name="Acct3")
        self.client.force_login(self.user)

    def _device(self, package="free"):
        return Device.objects.create(
            account=self.account, name="D1",
            phone_number=f"9190000{Device.objects.count():04d}",
            status="connect", package=package,
        )

    def test_upload_rejected_without_attachment_access(self):
        device = self._device(package="free")
        f = SimpleUploadedFile("a.txt", b"hello", content_type="text/plain")
        res = self.client.post(
            reverse("whatsapp:chat_upload"), {"device": str(device.id), "file": f}
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.json()["status"])

    def test_upload_accepted_for_super_package(self):
        device = self._device(package="super")
        f = SimpleUploadedFile("a.txt", b"hello", content_type="text/plain")
        res = self.client.post(
            reverse("whatsapp:chat_upload"), {"device": str(device.id), "file": f}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["status"])
        self.assertTrue(data["url"].startswith("http"))
        self.assertEqual(data["filename"], "a.txt")


class HistorySyncWebhookTests(TestCase):
    """webhook_receiver's history_sync / direction-aware incoming_message handling."""

    def setUp(self):
        self.user = User.objects.create_user("u4", password="pw12345!")
        self.account = Account.objects.create(user=self.user, name="Acct4")
        self.device = Device.objects.create(
            account=self.account, name="D1", phone_number="919000000099", status="connect"
        )

    def _post(self, payload):
        return self.client.post(
            reverse("whatsapp_api:webhook_receiver"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_history_sync_creates_inbound_and_outbound(self):
        ts = int(timezone.now().timestamp())
        payload = {
            "event": "history_sync",
            "deviceId": str(self.device.id),
            "messages": [
                {"jid": "919876543210@s.whatsapp.net", "direction": "in", "id": "WAIN1",
                 "message": "hi there", "name": "Alice", "timestamp": ts},
                {"jid": "919876543210@s.whatsapp.net", "direction": "out", "id": "WAOUT1",
                 "message": "hey back", "timestamp": ts + 1},
            ],
        }
        res = self._post(payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["status"])

        inbound = IncomingMessage.objects.get(inbox_id="WAIN1")
        self.assertEqual(inbound.contact, "919876543210")
        self.assertEqual(inbound.message, "hi there")

        outbound = Message.objects.get(whatsapp_id="WAOUT1")
        self.assertEqual(outbound.target, "919876543210")
        self.assertEqual(outbound.body, "hey back")
        self.assertEqual(outbound.status, "sent")

    def test_history_sync_is_idempotent(self):
        ts = int(timezone.now().timestamp())
        payload = {
            "event": "history_sync",
            "deviceId": str(self.device.id),
            "messages": [
                {"jid": "919876543210@s.whatsapp.net", "direction": "in", "id": "WAIN2",
                 "message": "once", "timestamp": ts},
            ],
        }
        self._post(payload)
        self._post(payload)  # replay — must not duplicate
        self.assertEqual(IncomingMessage.objects.filter(inbox_id="WAIN2").count(), 1)

    def test_incoming_message_direction_out_routes_to_message(self):
        # Live event for a message the user sent from their phone (fromMe).
        payload = {
            "event": "incoming_message", "deviceId": str(self.device.id),
            "sender": "919876543210@s.whatsapp.net", "direction": "out",
            "message": "from my phone", "inboxid": "WALIVE1",
            "timestamp": int(timezone.now().timestamp()),
        }
        self._post(payload)
        self.assertTrue(Message.objects.filter(whatsapp_id="WALIVE1", body="from my phone").exists())
        self.assertFalse(IncomingMessage.objects.filter(inbox_id="WALIVE1").exists())

    def test_contacts_sync_creates_and_updates_contact(self):
        payload = {
            "event": "contacts_sync",
            "deviceId": str(self.device.id),
            "contacts": [
                {"jid": "919876543210@s.whatsapp.net", "name": "Alice"},
                {"jid": "919111111111@s.whatsapp.net", "name": ""},  # no usable name — skipped
            ],
        }
        self._post(payload)
        contact = Contact.objects.get(device=self.device, phone="919876543210")
        self.assertEqual(contact.name, "Alice")
        self.assertFalse(Contact.objects.filter(device=self.device, phone="919111111111").exists())

        # a later sync updates the same row rather than duplicating it
        payload["contacts"] = [{"jid": "919876543210@s.whatsapp.net", "name": "Alice W."}]
        self._post(payload)
        self.assertEqual(
            Contact.objects.filter(device=self.device, phone="919876543210").count(), 1
        )
        self.assertEqual(
            Contact.objects.get(device=self.device, phone="919876543210").name, "Alice W."
        )


class ChatsSyncViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u5", password="pw12345!")
        self.account = Account.objects.create(user=self.user, name="Acct5", email="u5@example.com")
        self.other_account = Account.objects.create(
            user=User.objects.create_user("u5b", password="pw12345!"),
            name="Other", email="u5b@example.com",
        )
        self.device = Device.objects.create(
            account=self.account, name="D1", phone_number="919000000098", status="connect"
        )
        self.client.force_login(self.user)

    def test_sync_rejects_device_not_owned_by_account(self):
        foreign_device = Device.objects.create(
            account=self.other_account, name="D2", phone_number="919000000097", status="connect"
        )
        res = self.client.post(reverse("whatsapp:chats_sync"), {"device": str(foreign_device.id)})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.json()["status"])

    def test_sync_rejects_missing_device(self):
        res = self.client.post(reverse("whatsapp:chats_sync"), {})
        self.assertEqual(res.status_code, 400)

    def test_sync_rejects_disconnected_device(self):
        self.device.status = "disconnect"
        self.device.save()
        res = self.client.post(reverse("whatsapp:chats_sync"), {"device": str(self.device.id)})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["reason"], "device not connected")

    def test_sync_with_no_local_history_returns_zero_chats(self):
        res = self.client.post(reverse("whatsapp:chats_sync"), {"device": str(self.device.id)})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["chats"], 0)


class ChatsViewDeviceFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u6", password="pw12345!")
        self.account = Account.objects.create(user=self.user, name="Acct6")
        self.d1 = Device.objects.create(
            account=self.account, name="D1", phone_number="919000000096", status="connect"
        )
        self.d2 = Device.objects.create(
            account=self.account, name="D2", phone_number="919000000095", status="connect"
        )
        IncomingMessage.objects.create(
            device=self.d1, sender="919876543210@s.whatsapp.net",
            contact="919876543210", message="on d1",
        )
        IncomingMessage.objects.create(
            device=self.d2, sender="919555555555@s.whatsapp.net",
            contact="919555555555", message="on d2",
        )
        earlier = timezone.now() - timedelta(hours=1)
        Message.objects.create(device=self.d1, target="919876543210", body="started", created_at=earlier)
        Message.objects.create(device=self.d2, target="919555555555", body="started", created_at=earlier)
        self.client.force_login(self.user)

    def test_device_filter_excludes_other_device_chats(self):
        res = self.client.get(reverse("whatsapp:chats"), {"device": str(self.d2.id)})
        self.assertContains(res, "on d2")
        self.assertNotContains(res, "on d1")
