"""
Browser UI URL routing — all under /app/ prefix.
"""

from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import ui_views

app_name = "ui"

# ── Password reset (Django's built-in, secure token flow) ────────────────────
password_reset_urls = [
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="ui/password_reset_form.html",
            email_template_name="ui/password_reset_email.html",
            subject_template_name="ui/password_reset_subject.txt",
            success_url=reverse_lazy("ui:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="ui/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="ui/password_reset_confirm.html",
            success_url=reverse_lazy("ui:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="ui/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]

urlpatterns = [
    path("signup/",       ui_views.signup_view,       name="signup"),
    path("login/",        ui_views.login_view,         name="login"),
    path("logout/",       ui_views.logout_view,        name="logout"),
    path("profile/",      ui_views.profile_view,       name="profile"),
    *password_reset_urls,
    path("",              ui_views.dashboard,          name="dashboard"),
    path("devices/",      ui_views.devices_view,       name="devices"),
    path("send/",         ui_views.send_view,          name="send"),
    path("messages/",     ui_views.messages_view,      name="messages"),
    path("inbox/",        ui_views.inbox_view,         name="inbox"),
    path("templates/",    ui_views.templates_view,     name="templates"),
    path("autoreplies/",  ui_views.autoreplies_view,   name="autoreplies"),
    path("notifications/",ui_views.notifications_feed, name="notifications"),

    # Unified + mail dashboards
    path("unified/",         ui_views.unified_dashboard,  name="unified_dashboard"),
    path("mail/",             ui_views.mail_dashboard,     name="mail_dashboard"),
    path("mail/accounts/",    ui_views.mail_accounts_view, name="mail_accounts"),
    path("mail/compose/",     ui_views.mail_compose_view,  name="mail_compose"),
    path("mail/sent/",        ui_views.mail_sent_view,     name="mail_sent"),
    path("mail/inbox/",       ui_views.mail_inbox_view,    name="mail_inbox"),
]
