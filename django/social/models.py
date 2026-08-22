"""
Social channel models — one pair of tables shared by every platform adapter
(Telegram, Slack, LinkedIn, ...), mirroring mail.MailAccount / IncomingEmail.
"""

import uuid
import secrets
from django.db import models
from django.utils import timezone

from accounts.models import Account
from core.choices import CONNECTION_STATUS_CHOICES, SEND_STATUS_CHOICES
from core.utils import decrypt_secret, encrypt_secret

PLATFORM_CHOICES = [
    ("telegram", "Telegram"),
    ("slack", "Slack"),
    ("linkedin", "LinkedIn"),
    ("facebook", "Facebook"),
    ("instagram", "Instagram"),
    ("gbp", "Google Business Profile"),
    ("x", "X (Twitter)"),
]


class SocialAccount(models.Model):
    """One connected channel account (e.g. one Telegram bot, one Slack
    workspace). credentials_enc holds whatever the adapter needs (bot token,
    OAuth tokens, ...) as encrypted JSON — never a fixed column set, since
    each platform's auth shape differs."""

    STATUS_CHOICES = CONNECTION_STATUS_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="social_accounts")
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    social_token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    name = models.CharField(max_length=30)
    credentials_enc = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="disconnect")
    last_sync_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "social_account"
        indexes = [models.Index(fields=["platform"])]

    @property
    def credentials(self):
        import json
        raw = decrypt_secret(self.credentials_enc) if self.credentials_enc else ""
        return json.loads(raw) if raw else {}

    @credentials.setter
    def credentials(self, data):
        import json
        self.credentials_enc = encrypt_secret(json.dumps(data or {}))

    def __str__(self):
        return f"{self.get_platform_display()}: {self.name}"


class SocialMessage(models.Model):
    """One inbound or outbound message/post on any channel."""

    STATUS_CHOICES = SEND_STATUS_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    social_account = models.ForeignKey(SocialAccount, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=[("in", "Inbound"), ("out", "Outbound")])
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    target = models.CharField(max_length=255, blank=True)  # chat id / channel / recipient
    body = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="process")
    payload = models.JSONField(default=dict, blank=True)  # raw platform payload
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "social_message"
        constraints = [
            models.UniqueConstraint(
                fields=["social_account", "external_id"],
                condition=~models.Q(external_id=""),
                name="uniq_social_account_external_id",
            )
        ]

    def __str__(self):
        return f"{self.direction} {self.social_account.platform}:{self.target} [{self.status}]"
