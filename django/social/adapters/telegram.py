"""
Telegram adapter — Bot API over plain HTTPS.

No SDK: the whole surface this project needs (sendMessage, setWebhook, getMe)
is three JSON POSTs, and the project already calls its Node workers with raw
`requests` (see core/utils.py:call_worker). Pulling in python-telegram-bot
would add an async event loop to bridge into Django's sync views for zero
benefit here — skip it unless bot features (inline keyboards, conversation
state, polling mode) are needed later.
"""

import requests

from .base import ChannelAdapter

API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramAdapter(ChannelAdapter):
    slug = "telegram"
    capabilities = frozenset({"send", "dm"})

    def _call(self, token, method, **params):
        url = API_BASE.format(token=token, method=method)
        resp = requests.post(url, json=params, timeout=15)
        return resp.json()

    def connect(self, social_account):
        token = social_account.credentials.get("bot_token", "")
        if not token:
            return {"status": False, "reason": "bot_token required"}
        result = self._call(token, "getMe")
        if not result.get("ok"):
            social_account.status = "disconnect"
            social_account.save(update_fields=["status"])
            return {"status": False, "reason": result.get("description", "invalid bot token")}

        social_account.status = "connect"
        social_account.save(update_fields=["status"])
        return {"status": True, "bot_username": result["result"].get("username")}

    def set_webhook(self, social_account, webhook_url):
        token = social_account.credentials.get("bot_token", "")
        return self._call(token, "setWebhook", url=webhook_url)

    def send(self, social_account, target, body, **kwargs):
        token = social_account.credentials.get("bot_token", "")
        result = self._call(token, "sendMessage", chat_id=target, text=body)
        if not result.get("ok"):
            return {"status": False, "reason": result.get("description", "send failed")}
        return {"status": True, "id": str(result["result"]["message_id"])}

    def handle_webhook(self, social_account, payload):
        """payload is one Telegram Update. Returns a dict shaped for
        SocialMessage.objects.update_or_create(), or None to ignore
        (e.g. non-message updates like edited_message, callback_query)."""
        message = payload.get("message")
        if not message:
            return None
        chat = message.get("chat", {})
        return {
            "external_id": str(message.get("message_id", "")),
            "target": str(chat.get("id", "")),
            "body": message.get("text", ""),
            "status": "delivered",
        }
