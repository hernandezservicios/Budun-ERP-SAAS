"""
Única vía sancionada para gestionar la `ApiKey` de un tenant. El
secreto en texto plano SOLO existe como valor de retorno de
`generate_api_key`/`rotate_api_key` — nunca se guarda, nunca se
recupera después (ni siquiera un superusuario puede verlo de nuevo)."""

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.audit.models import AuditLog

from .crypto import generate_secret, hash_secret
from .models import ApiKey
from .scopes import is_valid_scope_list

PREFIJO = "bk_"


class InvalidApiKeyOperation(ValidationError):
    """Scopes inválidos, ya existe una clave activa, clave no
    encontrada, etc."""


def _audit(tenant, *, action, user, api_key, **extra):
    """`apps.api` depende directamente de `apps.audit` (ambas del mismo
    commit/fase — a diferencia de `apps.permissions`/`apps.payroll`,
    que se construyeron ANTES de que `apps.audit` existiera y por eso
    usan import diferido). Aun así, la auditoría nunca debe poder
    romper la gestión de la clave: se envuelve en `try/except`."""
    try:
        from apps.audit.services import log_event

        log_event(
            tenant, user=user, action=action, domain="api",
            object_type="api_key", object_id=api_key.key_prefix, **extra,
        )
    except Exception:  # noqa: BLE001 — la auditoría nunca debe romper la operación.
        pass


def get_api_key(tenant):
    return ApiKey.all_objects.filter(tenant=tenant).first()


def generate_api_key(tenant, *, user, scopes):
    """Crea la (única) `ApiKey` del tenant. Si ya existe una, se
    rechaza — usa `rotate_api_key` para reemplazarla."""
    if not is_valid_scope_list(scopes):
        raise InvalidApiKeyOperation("Uno o más scopes no son válidos.")
    if ApiKey.all_objects.filter(tenant=tenant).exists():
        raise InvalidApiKeyOperation("Este tenant ya tiene una clave de API — usa rotar en vez de generar.")

    secreto = generate_secret()
    prefijo = f"{PREFIJO}{secreto[:8]}"
    api_key = ApiKey.all_objects.create(
        tenant=tenant, key_prefix=prefijo, key_hash=hash_secret(secreto), scopes=list(scopes), created_by=user,
    )
    _audit(tenant, action=AuditLog.Action.API_KEY_CREATED, user=user, api_key=api_key, after={"scopes": scopes})
    return api_key, secreto


def rotate_api_key(api_key, *, user):
    """Reemplaza el hash de la MISMA fila — invalida la clave anterior
    de inmediato, nunca hay dos claves activas a la vez."""
    secreto = generate_secret()
    api_key.key_prefix = f"{PREFIJO}{secreto[:8]}"
    api_key.key_hash = hash_secret(secreto)
    api_key.status = ApiKey.Status.ACTIVE
    api_key.rotated_at = timezone.now()
    api_key.save(update_fields=["key_prefix", "key_hash", "status", "rotated_at"])
    _audit(api_key.tenant, action=AuditLog.Action.API_KEY_ROTATED, user=user, api_key=api_key)
    return api_key, secreto


def revoke_api_key(api_key, *, user):
    api_key.status = ApiKey.Status.REVOKED
    api_key.revoked_at = timezone.now()
    api_key.revoked_by = user
    api_key.save(update_fields=["status", "revoked_at", "revoked_by"])
    _audit(api_key.tenant, action=AuditLog.Action.API_KEY_REVOKED, user=user, api_key=api_key)
    return api_key


def set_api_key_scopes(api_key, *, scopes, user):
    if not is_valid_scope_list(scopes):
        raise InvalidApiKeyOperation("Uno o más scopes no son válidos.")
    antes = list(api_key.scopes)
    api_key.scopes = list(scopes)
    api_key.save(update_fields=["scopes"])
    _audit(api_key.tenant, action=AuditLog.Action.GENERIC, user=user, api_key=api_key, before={"scopes": antes}, after={"scopes": scopes})
    return api_key


def authenticate_api_key(secreto):
    """Resuelve una `ApiKey` ACTIVE y no expirada a partir del secreto
    completo recibido en la request — nunca al revés (nunca se busca
    por prefijo/tenant enviado por el cliente). Devuelve `None` si no
    hay coincidencia, está revocada o expiró."""
    if not secreto:
        return None
    api_key = ApiKey.all_objects.filter(key_hash=hash_secret(secreto), status=ApiKey.Status.ACTIVE).first()
    if api_key is None:
        return None
    if api_key.expires_at is not None and api_key.expires_at <= timezone.now():
        return None
    return api_key


def touch_last_used(api_key):
    ApiKey.all_objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())


def test_connection(api_key, *, user):
    """"Probar Conexión": una API Key ACTIVE y no expirada siempre se
    considera CONECTADO — es una prueba de la propia clave, no de un
    servicio externo (no hay tal cosa aquí: el "servicio" es este
    mismo backend)."""
    ahora = timezone.now()
    if api_key.status != ApiKey.Status.ACTIVE:
        resultado_ok, error = False, "La clave está revocada."
    elif api_key.expires_at is not None and api_key.expires_at <= ahora:
        resultado_ok, error = False, "La clave expiró."
    else:
        resultado_ok, error = True, ""
    api_key.last_tested_at = ahora
    api_key.last_test_ok = resultado_ok
    api_key.last_test_error = error
    api_key.save(update_fields=["last_tested_at", "last_test_ok", "last_test_error"])
    _audit(api_key.tenant, action=AuditLog.Action.API_ACCESS, user=user, api_key=api_key, metadata={"prueba_conexion": True, "resultado": resultado_ok})
    return resultado_ok, error
