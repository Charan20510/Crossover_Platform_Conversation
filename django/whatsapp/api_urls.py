"""
WhatsApp token-API URL routing — Fonnte-compatible endpoints.
Paths are byte-identical to the pre-refactor api/urls.py.
"""

from django.urls import path
from . import views

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
]
