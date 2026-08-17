"""
Legacy app — migration history only. Do not add models, views or urls here;
the real code lives in core/accounts/whatsapp/mail. This app stays installed
solely so its 27 migrations remain the source of DDL for a fresh database.
"""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    verbose_name = "Legacy (migration history only)"
