"""
ChannelAdapter — the interface every platform (Telegram, Slack, LinkedIn, ...)
implements, plus WhatsApp/Mail once they're retro-fitted onto it. Keeps
social/views.py and social/webhooks.py platform-agnostic: they call
`get_adapter(slug)` and use these four methods instead of branching on
platform name.
"""


class ChannelAdapter:
    slug = None                # e.g. "telegram" — matches SocialAccount.platform
    capabilities = frozenset()  # subset of {"send", "read", "post", "dm", "notify"}

    def connect(self, social_account):
        """Verify credentials against the platform. Return a small status dict.
        Should set social_account.status and save it."""
        raise NotImplementedError

    def send(self, social_account, target, body, **kwargs):
        """Send a message/post. Return {"id": <external_id>} on success,
        {"status": False, "reason": ...} on failure."""
        raise NotImplementedError

    def fetch(self, social_account, since=None):
        """Pull-mode channels only (e.g. Google Business Profile): return a
        list of message dicts since the given timestamp."""
        raise NotImplementedError

    def handle_webhook(self, social_account, payload):
        """Push-mode channels only: turn one inbound webhook payload into a
        SocialMessage. social_account may be None if the platform's webhook
        doesn't carry enough to resolve it up front (adapter resolves it)."""
        raise NotImplementedError
