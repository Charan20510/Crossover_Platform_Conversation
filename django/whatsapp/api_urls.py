
from django.urls import path
from . import views

urlpatterns = [
    path("health", views.health, name="health"),

    path("qr", views.get_qr, name="get_qr"),
    path("disconnect", views.disconnect_device, name="disconnect"),

    path("send", views.send_message, name="send"),

    path("validate", views.validate_number, name="validate"),

    path("device", views.device_profile, name="device_profile"),

    path("add-device", views.add_device, name="add_device"),
    path("delete-device", views.delete_device, name="delete_device"),

    path("delete-message", views.delete_message, name="delete_message"),
    path("reschedule", views.reschedule, name="reschedule"),

    path("typing", views.typing, name="typing"),

    path("webhook/incoming", views.webhook_receiver, name="webhook_receiver"),
]
