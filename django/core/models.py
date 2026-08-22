
import uuid
from django.db import models
from django.utils import timezone

from accounts.models import Account
from core.utils import contact_key

class Contact(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=255, db_index=True)
    company = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    whatsapp = models.CharField(max_length=32, blank=True)
    mobile = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    instagram = models.CharField(max_length=100, blank=True)
    facebook = models.CharField(max_length=100, blank=True)
    x = models.CharField(max_length=100, blank=True)
    linkedin = models.CharField(max_length=200, blank=True)
    slack = models.CharField(max_length=100, blank=True)
    gbp = models.CharField(max_length=200, blank=True)
    telegram = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_contact"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if self.whatsapp:
            self.whatsapp = contact_key(self.whatsapp)
        if self.mobile:
            self.mobile = contact_key(self.mobile)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
