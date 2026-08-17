"""
Account model — a customer account (multi-tenant), one per Django auth User.
Moved from api/models.py; table name (api_account) is unchanged so no DDL runs.
"""

import uuid
import secrets
from django.conf import settings
from django.db import models
from django.utils import timezone


class Account(models.Model):
    """A customer account (multi-tenant). One account can manage many devices
    and many mailboxes.

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

    class Meta:
        db_table = "api_account"

    def __str__(self):
        return f"{self.name} ({self.email})"
