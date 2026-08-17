"""
Deprecated shim — the real models now live in accounts/whatsapp/mail.

Kept only so api/views.py, api/mail_views.py, api/ui_views.py, api/admin.py
and api/management/commands/createsuperuserauto.py keep importing correctly
until Phase 3 rewrites them to import from the new apps directly. Importing a
model class here does not re-register it under the "api" app_label — that
happens once, at class-definition time, in the module that actually defines it.
"""

from accounts.models import Account  # noqa: F401
from whatsapp.models import (  # noqa: F401
    AutoReply,
    Contact,
    Device,
    IncomingMessage,
    Message,
    MessageTemplate,
)
from mail.models import Email, IncomingEmail, MailAccount  # noqa: F401
