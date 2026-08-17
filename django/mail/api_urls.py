"""
Mail token-API URL routing — mirrors the WhatsApp endpoints.
Paths are byte-identical to the pre-refactor api/urls.py.
"""

from django.urls import path
from . import views

urlpatterns = [
    path("mail/connect", views.mail_connect, name="mail_connect"),
    path("mail/send", views.mail_send, name="mail_send"),
    path("mail/sync", views.mail_sync, name="mail_sync"),
    path("mail/account", views.add_mail_account, name="add_mail_account"),
    path("mail/delete-account", views.delete_mail_account, name="delete_mail_account"),
    path("webhook/mail", views.mail_webhook_receiver, name="mail_webhook_receiver"),
]
