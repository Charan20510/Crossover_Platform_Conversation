
from django.urls import path
from . import views

urlpatterns = [
    path("social/account", views.add_social_account, name="add_social_account"),
    path("social/delete-account", views.delete_social_account, name="delete_social_account"),
    path("social/send", views.send_social_message, name="send_social_message"),
    path("webhook/social/<str:platform>/<str:token>/", views.social_webhook, name="social_webhook"),
]
