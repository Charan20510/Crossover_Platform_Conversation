"""
API URL routing — Fonnte-compatible endpoints.
"""

from django.urls import path
from . import views, mail_views

urlpatterns = [
    # Health
    path("health", views.health, name="health"),

    # Device connection
    path("qr", views.get_qr, name="get_qr"),
    path("disconnect", views.disconnect_device, name="disconnect"),

    # Send messages
    path("send", views.send_message, name="send"),

    # Validate numbers
    path("validate", views.validate_number, name="validate"),

    # Device info
    path("device", views.device_profile, name="device_profile"),

    # Device management (account-level)
    path("add-device", views.add_device, name="add_device"),
    path("delete-device", views.delete_device, name="delete_device"),

    # Message management
    path("delete-message", views.delete_message, name="delete_message"),
    path("reschedule", views.reschedule, name="reschedule"),

    # Typing indicator
    path("typing", views.typing, name="typing"),

    # Internal: webhook receiver (called by Node.js worker)
    path("webhook/incoming", views.webhook_receiver, name="webhook_receiver"),

    # Dashboard
    path("dashboard", views.dashboard, name="dashboard"),

    # Mail (mirrors the WhatsApp endpoints above)
    path("mail/connect", mail_views.mail_connect, name="mail_connect"),
    path("mail/send", mail_views.mail_send, name="mail_send"),
    path("mail/sync", mail_views.mail_sync, name="mail_sync"),
    path("mail/account", mail_views.add_mail_account, name="add_mail_account"),
    path("mail/delete-account", mail_views.delete_mail_account, name="delete_mail_account"),
    path("webhook/mail", mail_views.mail_webhook_receiver, name="mail_webhook_receiver"),
]
