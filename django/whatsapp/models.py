
import uuid
import secrets
from django.db import models
from django.utils import timezone

from accounts.models import Account
from core.choices import CONNECTION_STATUS_CHOICES, SEND_STATUS_CHOICES

class Device(models.Model):

    PACKAGE_CHOICES = [
        ("free", "Free"),
        ("regular", "Regular"),
        ("regular_pro", "Regular Pro"),
        ("master", "Master"),
        ("super", "Super"),
        ("advanced", "Advanced"),
        ("ultra", "Ultra"),
    ]

    STATUS_CHOICES = CONNECTION_STATUS_CHOICES

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

    class Meta:
        db_table = "api_device"

    @property
    def has_attachment_access(self):
        return self.package in ("super", "advanced", "ultra")

    def __str__(self):
        return f"{self.name} ({self.phone_number})"

class Contact(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="contacts")
    phone = models.CharField(max_length=20)
    name = models.CharField(max_length=255, blank=True)
    extra_data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "api_contact"
        unique_together = ("device", "phone")

    def __str__(self):
        return f"{self.name or self.phone}"

class Message(models.Model):

    STATUS_CHOICES = SEND_STATUS_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="messages")
    target = models.CharField(max_length=20, db_index=True)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="process")
    state = models.CharField(max_length=20, blank=True, null=True)
    whatsapp_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    attachment_url = models.URLField(blank=True, null=True)
    filename = models.CharField(max_length=255, blank=True)
    scheduled_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "api_message"

    def __str__(self):
        return f"->{self.target} [{self.status}]"

class MessageTemplate(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="templates")
    name = models.CharField(max_length=100)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "api_messagetemplate"

    def __str__(self):
        return self.name

class AutoReply(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="auto_replies")
    keyword = models.CharField(max_length=255)
    reply = models.TextField()
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "api_autoreply"

    def __str__(self):
        return f"{self.keyword} -> {self.reply[:30]}..."

class IncomingMessage(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="incoming_messages")
    sender = models.CharField(max_length=64)
    contact = models.CharField(max_length=32, db_index=True, blank=True)
    message = models.TextField()
    name = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    attachment_url = models.URLField(blank=True, null=True)
    inbox_id = models.CharField(max_length=100, blank=True, null=True)
    timestamp = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "api_incomingmessage"
        indexes = [models.Index(fields=["device", "-received_at"], name="wa_incoming_dev_recv_idx")]

    def __str__(self):
        return f"{self.sender}: {self.message[:30]}..."
