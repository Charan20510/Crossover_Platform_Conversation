"""
WhatsApp browser UI URL routing — mounted at /app/whatsapp/.
"""

from django.urls import path
from django.views.generic import RedirectView

from . import ui_views

app_name = "whatsapp"

urlpatterns = [
    path("",             ui_views.dashboard,       name="dashboard"),
    path("devices/",     ui_views.devices_view,    name="devices"),
    path("send/",        ui_views.send_view,       name="send"),
    path("chats/",       ui_views.chats_view,      name="chats"),
    path("chats/feed/",  ui_views.chats_feed,      name="chats_feed"),
    path("chats/upload/", ui_views.chat_upload,    name="chat_upload"),
    path("chats/sync/",   ui_views.chats_sync,     name="chats_sync"),
    path("chats/<str:contact>/", ui_views.chats_view, name="chat_detail"),
    path("templates/",   ui_views.templates_view,  name="templates"),
    path("autoreplies/", ui_views.autoreplies_view, name="autoreplies"),

    # superseded — Chats absorbed the Inbox page; keep the URL name alive,
    # core.context_processors resolves it for the topbar bell.
    path("inbox/", RedirectView.as_view(pattern_name="whatsapp:chats"), name="inbox"),
]
