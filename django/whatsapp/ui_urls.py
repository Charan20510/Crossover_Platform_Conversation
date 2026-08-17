"""
WhatsApp browser UI URL routing — mounted at /app/whatsapp/.
"""

from django.urls import path
from . import ui_views

app_name = "whatsapp"

urlpatterns = [
    path("",             ui_views.dashboard,       name="dashboard"),
    path("devices/",     ui_views.devices_view,    name="devices"),
    path("send/",        ui_views.send_view,       name="send"),
    path("messages/",    ui_views.messages_view,   name="messages"),
    path("inbox/",       ui_views.inbox_view,      name="inbox"),
    path("templates/",   ui_views.templates_view,  name="templates"),
    path("autoreplies/", ui_views.autoreplies_view, name="autoreplies"),
]
