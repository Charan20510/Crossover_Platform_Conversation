"""
Database models for the WhatsApp Gateway API.
"""

import uuid
import secrets
from django.conf import settings
from django.db import models
from django.utils import timezone


class Account(models.Model):
    """A customer account (multi-tenant). One account can manage many devices.

    Linked one-to-one with a Django auth User — the User holds the
    username/password credentials, the Account holds the API token and profile.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    account_token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.name} ({self.email})"


class Device(models.Model):
    """A WhatsApp number linked to this gateway. One account -> many devices."""

    PACKAGE_CHOICES = [
        ("free", "Free"),
        ("regular", "Regular"),
        ("regular_pro", "Regular Pro"),
        ("master", "Master"),
        ("super", "Super"),
        ("advanced", "Advanced"),
        ("ultra", "Ultra"),
    ]

    STATUS_CHOICES = [
        ("connect", "Connected"),
        ("disconnect", "Disconnected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="devices")
    device_token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    name = models.CharField(max_length=30)
    phone_number = models.CharField(max_length=15, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="disconnect")
    package = models.CharField(max_length=15, choices=PACKAGE_CHOICES, default="free")
    quota = models.IntegerField(default=1000)
    messages_sent = models.IntegerField(default=0)
    webhook_url = models.URLField(blank=True, null=True)
    autoread = models.BooleanField(default=False)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def has_attachment_access(self):
        """Only super/advanced/ultra packages can send attachments."""
        return self.package in ("super", "advanced", "ultra")

    def __str__(self):
        return f"{self.name} ({self.phone_number})"


class Contact(models.Model):
    """Saved contacts for a device."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="contacts")
    phone = models.CharField(max_length=20)
    name = models.CharField(max_length=255, blank=True)
    extra_data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("device", "phone")

    def __str__(self):
        return f"{self.name or self.phone}"


class Message(models.Model):
    """Outbound messages (single or bulk)."""

    STATUS_CHOICES = [
        ("process", "Processing"),
        ("pending", "Pending / Scheduled"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("read", "Read"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="messages")
    target = models.CharField(max_length=20)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="process")
    state = models.CharField(max_length=20, blank=True, null=True)
    whatsapp_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    scheduled_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"->{self.target} [{self.status}]"


class MessageTemplate(models.Model):
    """Reusable message templates."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="templates")
    name = models.CharField(max_length=100)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name


class AutoReply(models.Model):
    """Keyword-based auto-reply rules."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="auto_replies")
    keyword = models.CharField(max_length=255)
    reply = models.TextField()
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.keyword} -> {self.reply[:30]}..."


class IncomingMessage(models.Model):
    """Inbound messages received from WhatsApp."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="incoming_messages")
    sender = models.CharField(max_length=20)
    message = models.TextField()
    name = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    attachment_url = models.URLField(blank=True, null=True)
    inbox_id = models.CharField(max_length=100, blank=True, null=True)
    timestamp = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.sender}: {self.message[:30]}..."


class MailAccount(models.Model):
    """A mailbox linked to this gateway (IMAP + SMTP). One account -> many mailboxes."""

    STATUS_CHOICES = Device.STATUS_CHOICES

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

    @property
    def password(self):
        from .utils import decrypt_secret
        return decrypt_secret(self.password_enc) if self.password_enc else ""

    @password.setter
    def password(self, raw):
        from .utils import encrypt_secret
        self.password_enc = encrypt_secret(raw)

    def __str__(self):
        return f"{self.name} ({self.email_address})"


class Email(models.Model):
    """Outbound emails."""

    STATUS_CHOICES = Message.STATUS_CHOICES

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
        unique_together = ("mail_account", "message_id")

    def __str__(self):
        return f"{self.sender}: {self.subject[:30]}..."
