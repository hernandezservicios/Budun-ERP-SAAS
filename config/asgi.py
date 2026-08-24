"""
Configuración ASGI (no usada activamente en el stack oficial del proyecto,
que sirve por WSGI/Gunicorn; se mantiene por compatibilidad con el
scaffold estándar de Django).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
