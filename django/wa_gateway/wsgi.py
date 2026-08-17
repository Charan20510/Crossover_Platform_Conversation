"""
WSGI config for wa_gateway project.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wa_gateway.settings")
application = get_wsgi_application()
