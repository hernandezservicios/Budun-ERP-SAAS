"""
Configuración WSGI para producción (Gunicorn + Nginx/servidor web en
Hostinger VPS — ver FASE 21).
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
