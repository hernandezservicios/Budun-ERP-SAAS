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

from pathlib import Path

from dotenv import load_dotenv
import os

# --- Rutas base ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Las apps propias del proyecto viven en apps/ (products, inventory, sales,
# pos, tenants, etc. se irán agregando fase a fase) y se referencian en
# INSTALLED_APPS con su ruta completa ("apps.<nombre>"). Django deriva
# automáticamente la etiqueta corta ("tenants", "accounts", "core") del
# último segmento de esa ruta, así que AUTH_USER_MODEL, related_name, etc.
# siguen usando el nombre corto. (No se inserta apps/ en sys.path: hacerlo
# junto con apps/__init__.py provoca que Django importe cada módulo por dos
# rutas distintas y el registro de apps deje de reconocerlo.)

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
    "apps.accounts",
    "apps.tenants",
    "apps.core",
    "apps.dashboard",
    "apps.inventory",
    "apps.customers",
    "apps.sales",
    "apps.approvals",
    "apps.pos",
    "apps.purchases",
    "apps.expenses",
    "apps.hr",
    "apps.payroll",
    "apps.accounting",
    "apps.reports",
    "apps.permissions",
    "apps.audit",
    "rest_framework",
    "apps.api",
]

# --- API de Inventario v1 (FASE 15) ---------------------------------------
# `DEFAULT_AUTHENTICATION_CLASSES=[]`: nunca sesión/JWT genérico — cada
# vista de `apps.api` declara explícitamente `ApiKeyAuthentication`
# (ver `apps/api/authentication.py`). `EXCEPTION_HANDLER` propio para el
# sobre de respuesta consistente (`success`/`data`/`meta`/`errors`,
# nunca un traceback interno). `DEFAULT_THROTTLE_RATES["api_key"]` es el
# límite de tasa configurable a nivel de PROYECTO (no por API Key
# individual todavía — extensión futura simple, ver `docs/api-inventory.md`).
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_PAGINATION_CLASS": "apps.api.pagination.ApiV1Pagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.api.responses.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["apps.api.throttling.ApiKeyRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"api_key": "120/min"},
}

# `LocMemCache` — adecuado para un solo proceso (desarrollo y un VPS
# Windows/Linux de un solo proceso); Redis queda deferido hasta que una
# fase futura demuestre necesidad real (ver CLAUDE.md).
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

# Custom User Model (FASE 3). Debe fijarse antes de la primera migración
# real de la app "auth"; ver apps/accounts/models.py para el porqué.
AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Requiere que AuthenticationMiddleware ya haya resuelto request.user.
    "apps.tenants.middleware.TenantMiddleware",
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

# --- Autenticación (FASE 4) -----------------------------------------------
LOGIN_URL = "accounts:login"
# Los redirects "inteligentes" (a onboarding vs. a perfil) se resuelven en
# las vistas (ver apps/accounts/views.py) según request.tenant; estos son
# solo el fallback genérico que exige el framework.
LOGIN_REDIRECT_URL = "accounts:perfil"
LOGOUT_REDIRECT_URL = "core:home"

# Email (FASE 4): en desarrollo se usa el backend de consola (no se envía
# nada real, solo se imprime en la terminal/log). Un proveedor SMTP real
# es una decisión de FASE 21 — Hostinger Deployment.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@erp-saas.local")

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

# --- Archivos subidos por el usuario (FASE 9: documentos de Clientes y
# Proveedores) ------------------------------------------------------------
# Deliberadamente NO se registra `static(MEDIA_URL, document_root=MEDIA_ROOT)`
# en config/urls.py: eso serviría cualquier archivo de `media-private/`
# como estático público sin autenticación ni verificación de tenant. La
# única vía de descarga es una vista protegida (login + tenant + dueño
# del documento verificados), ver `apps/customers/views.py`. `MEDIA_URL`
# solo existe para que Django construya `.file.url` internamente; nunca
# se expone tal cual en una plantilla como enlace de descarga directo.
MEDIA_URL = "media-private/"
MEDIA_ROOT = BASE_DIR / "media-private"

# Límite duro a nivel de Django (además de la validación explícita en
# `apps.customers.file_validation`, que corre antes y da un mensaje más
# claro): ninguna subida completa puede superar ~10 MB en memoria antes
# de volcarse a disco temporal.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

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
