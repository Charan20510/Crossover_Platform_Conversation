"""
URL configuration for wa_gateway project.
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
from django.views.generic import RedirectView


def health(request):
    return JsonResponse({"status": "ok", "service": "wa_gateway"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health),
    # Browser UI (session-based, account-scoped)
    path("app/", include("api.ui_urls")),
    # Redirect bare root to the UI dashboard
    re_path(r"^$", RedirectView.as_view(url="/app/", permanent=False)),
    # Fonnte-compatible API endpoints
    path("api/", include("api.urls")),
    path("", include("api.urls")),  # root-level endpoints like Fonnte
]
