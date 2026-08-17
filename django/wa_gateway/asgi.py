"""
ASGI config for wa_gateway project.
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wa_gateway.settings")
application = get_asgi_application()
