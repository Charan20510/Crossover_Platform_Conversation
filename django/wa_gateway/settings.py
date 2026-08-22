"""
Django settings for wa_gateway project.
Messaging Platform - Django backend (Fonnte clone)
"""

from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-this-in-production-please-use-a-long-random-string"
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "api",       # legacy: migration history only, do not add models here
    "core",
    "accounts",
    "whatsapp",
    "mail",
    "social",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "wa_gateway.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # No project-level templates/ dir — every template now lives in its
        # owning app's templates/<app>/ directory, found via APP_DIRS.
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.nav",
            ],
        },
    },
]

WSGI_APPLICATION = "wa_gateway.wsgi.application"
ASGI_APPLICATION = "wa_gateway.asgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "wa_gateway"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# Fallback to SQLite if no DB configured (dev mode)
if os.environ.get("USE_SQLITE", "false").lower() == "true":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# No project-level static/ dir — every asset now lives in its owning app's
# static/<app>/ directory, found via the AppDirectoriesFinder default.

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# WhatsApp outbound attachment uploads (whatsapp.ui_views). The Baileys worker
# fetches these by URL, so in production MEDIA_URL must be reachable from it.

# Mail attachments cross the Django<->worker boundary as base64 inside the
# JSON body of a single request (see mail/ui_views.py::_attachments); raise
# the default 2.5MB cap so that doesn't 400 in middleware before the view runs.
DATA_UPLOAD_MAX_MEMORY_SIZE = 32 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Auth redirects for @login_required
LOGIN_URL = "/app/accounts/login/"
LOGIN_REDIRECT_URL = "/app/"

# ── Email (password reset) ────────────────────────────────────────────────────
# Dev default: print emails to the console (includes the reset link).
# Override in production via env:
#   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
#   EMAIL_HOST=smtp.example.com  EMAIL_PORT=587  EMAIL_USE_TLS=True
#   EMAIL_HOST_USER=...  EMAIL_HOST_PASSWORD=...
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Messaging Platform <noreply@wa-gateway.local>")

# SMTP settings (only used when EMAIL_BACKEND is set to smtp)
if os.environ.get("EMAIL_HOST"):
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# CORS - restrict to known origins; set DJANGO_CORS_ORIGINS env var in production
_cors_origins = os.environ.get("DJANGO_CORS_ORIGINS", "")
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(",")]
else:
    CORS_ALLOW_ALL_ORIGINS = DEBUG  # open only in dev mode
CORS_ALLOW_CREDENTIALS = False  # don't send cookies cross-origin

# ---- App-specific config ----

# Node worker base URL (the Baileys microservice)
WORKER_BASE_URL = os.environ.get("WORKER_BASE_URL", "http://localhost:3000")

# Node mail worker base URL (ImapFlow + Nodemailer microservice)
MAIL_WORKER_BASE_URL = os.environ.get("MAIL_WORKER_BASE_URL", "http://localhost:3002")

# Rate limits (matching Fonnte)
RATE_LIMIT_PER_SECOND = 10
RATE_LIMIT_PER_MINUTE = 600

# Default country code (India for your use-case)
DEFAULT_COUNTRY_CODE = os.environ.get("DEFAULT_COUNTRY_CODE", "91")

# Message length cap
MAX_MESSAGE_LENGTH = 6000

# ponytail: Django 5.0 + Python 3.14 incompatibility — copy(super()) returns the proxy itself in 3.14
from django.template.context import BaseContext

def _base_context_copy(self):
    duplicate = self.__class__.__new__(self.__class__)
    duplicate.__dict__ = self.__dict__.copy()
    duplicate.dicts = self.dicts[:]
    return duplicate

BaseContext.__copy__ = _base_context_copy
