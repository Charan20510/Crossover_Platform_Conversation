
from django.urls import path
from django.views.generic import RedirectView

from . import ui_views

app_name = "mail"

urlpatterns = [
    path("",             ui_views.mail_dashboard, name="dashboard"),

    path("client/",           ui_views.mail_client,       name="client"),
    path("list/",             ui_views.mail_list,         name="list"),
    path("message/<uuid:pk>/", ui_views.mail_message,     name="message"),
    path("message/<uuid:pk>/thread/",     ui_views.mail_thread,     name="thread"),
    path("message/<uuid:pk>/attachment/<int:index>/", ui_views.mail_attachment, name="attachment"),
    path("sync/",             ui_views.mail_sync_folder,  name="sync_folder"),
    path("sync/folders/",     ui_views.mail_sync_folders, name="sync_folders"),
    path("flag/",             ui_views.mail_flag,         name="flag"),
    path("move/",             ui_views.mail_move,         name="move"),
    path("delete/",           ui_views.mail_delete,       name="delete"),
    path("send/",             ui_views.mail_send,         name="send"),
    path("draft/",            ui_views.mail_draft,        name="draft"),
    path("poll/",             ui_views.mail_poll,         name="poll"),
    path("contacts/",         ui_views.mail_contacts,     name="contacts"),
    path("settings/",         ui_views.mail_settings,     name="settings"),

    path("inbox/",    RedirectView.as_view(pattern_name="mail:client"),   name="inbox"),
    path("sent/",     RedirectView.as_view(pattern_name="mail:client"),   name="sent"),
    path("compose/",  RedirectView.as_view(pattern_name="mail:client"),   name="compose"),
    path("accounts/", RedirectView.as_view(pattern_name="mail:settings"), name="accounts"),
]
