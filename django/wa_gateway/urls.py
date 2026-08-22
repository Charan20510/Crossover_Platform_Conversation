
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

    path("app/accounts/", include("accounts.ui_urls")),
    path("app/whatsapp/", include("whatsapp.ui_urls")),
    path("app/mail/",     include("mail.ui_urls")),
    path("app/",          include("core.ui_urls")),

    re_path(r"^$", RedirectView.as_view(url="/app/", permanent=False)),

    path("api/", include(("whatsapp.api_urls", "whatsapp_api"), namespace="whatsapp_api_prefixed")),
    path("api/", include(("mail.api_urls", "mail_api"), namespace="mail_api_prefixed")),
    path("api/", include(("social.api_urls", "social_api"), namespace="social_api_prefixed")),
    path("",     include(("whatsapp.api_urls", "whatsapp_api"), namespace="whatsapp_api")),
    path("",     include(("mail.api_urls", "mail_api"), namespace="mail_api")),
    path("",     include(("social.api_urls", "social_api"), namespace="social_api")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
