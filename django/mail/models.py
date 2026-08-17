"""
Mail models — MailAccount, Email, IncomingEmail. Moved from api/models.py;
table names (api_mailaccount, ...) are unchanged so no DDL runs.
"""

import uuid
import secrets
from django.db import models
from django.utils import timezone

from accounts.models import Account
from core.choices import CONNECTION_STATUS_CHOICES, SEND_STATUS_CHOICES
from core.utils import decrypt_secret, encrypt_secret


class MailAccount(models.Model):
    """A mailbox linked to this gateway (IMAP + SMTP). One account -> many mailboxes."""

    STATUS_CHOICES = CONNECTION_STATUS_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="mail_accounts")
    mail_token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    name = models.CharField(max_length=30)
    email_address = models.EmailField()
    imap_host = models.CharField(max_length=255)
    imap_port = models.IntegerField(default=993)
    imap_secure = models.BooleanField(default=True)
    smtp_host = models.CharField(max_length=255)
    smtp_port = models.IntegerField(default=587)
    smtp_secure = models.BooleanField(default=False)
    username = models.CharField(max_length=255)
    password_enc = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="disconnect")
    emails_sent = models.IntegerField(default=0)
    last_sync_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "api_mailaccount"

    @property
    def password(self):
        return decrypt_secret(self.password_enc) if self.password_enc else ""

    @password.setter
    def password(self, raw):
        self.password_enc = encrypt_secret(raw)

    def __str__(self):
        return f"{self.name} ({self.email_address})"


class Email(models.Model):
    """Outbound emails."""

    STATUS_CHOICES = SEND_STATUS_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mail_account = models.ForeignKey(MailAccount, on_delete=models.CASCADE, related_name="emails")
    to_addr = models.CharField(max_length=500)
    cc = models.CharField(max_length=500, blank=True)
    bcc = models.CharField(max_length=500, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="process")
    message_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    scheduled_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "api_email"

    def __str__(self):
        return f"->{self.to_addr} [{self.status}]"


class IncomingEmail(models.Model):
    """Inbound emails fetched via IMAP sync."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mail_account = models.ForeignKey(MailAccount, on_delete=models.CASCADE, related_name="incoming_emails")
    uid = models.CharField(max_length=50, blank=True)
    message_id = models.CharField(max_length=255, db_index=True)
    sender = models.CharField(max_length=255)
    sender_name = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    body_text = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    folder = models.CharField(max_length=100, default="INBOX")
    is_read = models.BooleanField(default=False)
    has_attachments = models.BooleanField(default=False)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "api_incomingemail"
        unique_together = ("mail_account", "message_id")

    def __str__(self):
        return f"{self.sender}: {self.subject[:30]}..."
