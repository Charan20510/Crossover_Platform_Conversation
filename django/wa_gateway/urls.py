"""
URL configuration for wa_gateway project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
from django.views.generic import RedirectView


def health(request):
    return JsonResponse({"status": "ok", "service": "wa_gateway"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health),

    # Browser UI (session-based, account-scoped). Section-prefixed apps must
    # come before the bare "app/" include (core: unified section, the landing
    # page) so their own patterns get first crack at matching.
    path("app/accounts/", include("accounts.ui_urls")),
    path("app/whatsapp/", include("whatsapp.ui_urls")),
    path("app/mail/",     include("mail.ui_urls")),
    path("app/",          include("core.ui_urls")),

    # Redirect bare root to the UI
    re_path(r"^$", RedirectView.as_view(url="/app/", permanent=False)),

    # Fonnte-compatible token API — paths unchanged from the pre-refactor
    # single api.urls module. Included twice (at /api/ and at root, like
    # Fonnte) under distinct namespaces so the two copies never fight over
    # the same reverse() name — nothing currently reverses these by name,
    # but this keeps that true instead of leaving it to luck.
    path("api/", include(("whatsapp.api_urls", "whatsapp_api"), namespace="whatsapp_api_prefixed")),
    path("api/", include(("mail.api_urls", "mail_api"), namespace="mail_api_prefixed")),
    path("api/", include(("social.api_urls", "social_api"), namespace="social_api_prefixed")),
    path("",     include(("whatsapp.api_urls", "whatsapp_api"), namespace="whatsapp_api")),
    path("",     include(("mail.api_urls", "mail_api"), namespace="mail_api")),
    path("",     include(("social.api_urls", "social_api"), namespace="social_api")),
]

if settings.DEBUG:
    # Prod should serve MEDIA_URL via the web server / a real storage backend.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
