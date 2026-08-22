"""
Django admin configuration — social.
"""

from django.contrib import admin
from .models import SocialAccount, SocialMessage


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "platform", "status", "account", "last_sync_at")
    list_filter = ("platform", "status")
    search_fields = ("name",)
    exclude = ("credentials_enc",)


@admin.register(SocialMessage)
class SocialMessageAdmin(admin.ModelAdmin):
    list_display = ("social_account", "direction", "target", "status", "created_at")
    list_filter = ("direction", "status")
    search_fields = ("target", "body")
