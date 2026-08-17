"""
Mail browser UI URL routing — mounted at /app/mail/.
"""

from django.urls import path
from . import ui_views

app_name = "mail"

urlpatterns = [
    path("",           ui_views.mail_dashboard,      name="dashboard"),
    path("accounts/",  ui_views.mail_accounts_view,  name="accounts"),
    path("compose/",   ui_views.mail_compose_view,   name="compose"),
    path("sent/",      ui_views.mail_sent_view,      name="sent"),
    path("inbox/",     ui_views.mail_inbox_view,     name="inbox"),
]
