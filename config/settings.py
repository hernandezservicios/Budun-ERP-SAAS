"""
Configuración de Django para el proyecto ERP SaaS Multi-Tenant.

Fase: FASE 1 — Project Foundation.
Alcance de esta fase: fundación del proyecto (settings, estructura, templates
base). La conexión real a PostgreSQL, migraciones y verificación en pgAdmin 4
se completan en FASE 2 — PostgreSQL Foundation.

Reglas del proyecto (ver CLAUDE.md):
- Base de datos oficial: PostgreSQL. Nunca SQLite como base principal.
- Sin Docker, sin MySQL/MariaDB.
- Toda la configuración sensible viene de variables de entorno (.env),
  nunca hardcodeada ni commiteada.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv
import os

# --- Rutas base ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Las apps propias del proyecto viven en apps/ (products, inventory, sales,
# pos, tenants, etc. se irán agregando fase a fase). Se añade al path para
# poder referenciarlas por su nombre corto (p. ej. "core") en INSTALLED_APPS.
sys.path.insert(0, str(BASE_DIR / "apps"))

# Carga variables desde .env (no versionado). En desarrollo Windows se crea
# a partir de .env.example siguiendo docs/setup/windows-postgresql-pgadmin-step-by-step.md.
load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name, default=""):
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


# --- Seguridad básica ----------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "DJANGO_SECRET_KEY no está definido. Crea un archivo .env a partir "
        "de .env.example y define una clave secreta real (no la subas a Git)."
    )

DEBUG = _env_bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

CSRF_TRUSTED_ORIGINS = _env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
)

# --- Aplicaciones ---------------------------------------------------------
# Incremental: solo se registran las apps necesarias para esta fase.
# django.contrib.admin se mantiene disponible como herramienta interna de
# staff, pero no es (ni será) la UI principal del producto (ver CLAUDE.md).
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de datos: PostgreSQL siempre (nunca SQLite) --------------------
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.environ.get("DB_NAME", "erp_saas_dev"),
        "USER": os.environ.get("DB_USER", "erp_saas_app"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# --- Validación de contraseñas -------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internacionalización -------------------------------------------------
# Toda la UI visible debe estar en español (ver CLAUDE.md).
LANGUAGE_CODE = "es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Archivos estáticos ----------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Endurecimiento básico de cookies/sesión -----------------------------
# Endurecimiento completo (HSTS, redirect SSL, CSP, etc.) corresponde a
# FASE 18 — Security Hardening. Aquí solo se aplican defaults seguros que no
# dependen de infraestructura de producción todavía no definida.
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Django necesita exponerla a JS por defecto para el header X-CSRFToken.
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
