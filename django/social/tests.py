
import json
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account
from .adapters import get_adapter
from .adapters.telegram import TelegramAdapter
from .models import SocialAccount, SocialMessage

def make_account(user_account, platform="telegram", token="tok123"):
    sa = SocialAccount(account=user_account, platform=platform, name="Bot")
    sa.credentials = {"bot_token": token}
    sa.save()
    return sa

class AdapterRegistryTests(TestCase):
    def test_telegram_registered(self):
        self.assertIsInstance(get_adapter("telegram"), TelegramAdapter)

    def test_unknown_platform_returns_none(self):
        self.assertIsNone(get_adapter("myspace"))

class TelegramAdapterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("bot-owner", password="pw12345678")
        self.account = Account.objects.create(user=self.user, name="Owner", email="o@example.com")
        self.sa = make_account(self.account)

    @patch("social.adapters.telegram.requests.post")
    def test_connect_success_marks_connected(self, mock_post):
        mock_post.return_value = MagicMock(json=lambda: {"ok": True, "result": {"username": "mybot"}})
        result = TelegramAdapter().connect(self.sa)
        self.sa.refresh_from_db()
        self.assertTrue(result["status"])
        self.assertEqual(self.sa.status, "connect")

    @patch("social.adapters.telegram.requests.post")
    def test_connect_bad_token_marks_disconnected(self, mock_post):
        mock_post.return_value = MagicMock(json=lambda: {"ok": False, "description": "Unauthorized"})
        result = TelegramAdapter().connect(self.sa)
        self.sa.refresh_from_db()
        self.assertFalse(result["status"])
        self.assertEqual(self.sa.status, "disconnect")

    @patch("social.adapters.telegram.requests.post")
    def test_send_returns_external_id(self, mock_post):
        mock_post.return_value = MagicMock(json=lambda: {"ok": True, "result": {"message_id": 42}})
        result = TelegramAdapter().send(self.sa, "555", "hi")
        self.assertEqual(result, {"status": True, "id": "42"})

    def test_webhook_parses_text_message(self):
        payload = {"message": {"message_id": 7, "chat": {"id": 555}, "text": "hello"}}
        parsed = TelegramAdapter().handle_webhook(self.sa, payload)
        self.assertEqual(parsed["external_id"], "7")
        self.assertEqual(parsed["target"], "555")
        self.assertEqual(parsed["body"], "hello")

    def test_webhook_ignores_non_message_updates(self):
        payload = {"edited_message": {"message_id": 7}}
        self.assertIsNone(TelegramAdapter().handle_webhook(self.sa, payload))

class SocialWebhookViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("bot-owner2", password="pw12345678")
        self.account = Account.objects.create(user=self.user, name="Owner2", email="o2@example.com")
        self.sa = make_account(self.account, token="tok456")

    def _post(self, payload):
        url = reverse("social_api:social_webhook", args=["telegram", self.sa.social_token])
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_duplicate_update_is_not_stored_twice(self):
        payload = {"message": {"message_id": 1, "chat": {"id": 9}, "text": "hi"}}
        self._post(payload)
        self._post(payload)
        self.assertEqual(SocialMessage.objects.filter(social_account=self.sa).count(), 1)

    def test_unknown_token_404s(self):
        url = reverse("social_api:social_webhook", args=["telegram", "not-a-real-token"])
        resp = self.client.post(url, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 404)
