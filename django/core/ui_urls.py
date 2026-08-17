"""
Unified section URL routing — mounted at /app/ (the landing section).
"""

from django.urls import path
from . import ui_views

app_name = "core"

urlpatterns = [
    path("",              ui_views.overview,           name="overview"),
    path("all-inbox/",    ui_views.all_inbox,          name="all_inbox"),
    path("notifications/", ui_views.notifications_feed, name="notifications"),
]
