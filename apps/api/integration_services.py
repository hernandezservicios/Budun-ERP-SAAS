"""
Única vía sancionada para gestionar `Integration` (ampliación final de
FASE 15 — ver `docs/integrations.md`). Espejo estructural de
`apps.api.services` (que gestiona `ApiKey`) — mismos principios: el
secreto en texto plano nunca se guarda, `all_objects` filtrando
siempre `tenant` explícito, cada operación auditada."""

import secrets

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_event

from .crypto import generate_secret, hash_secret
from .models import Integration
from .scopes import is_valid_catalog_scope_list

APP_KEY_PREFIX = "app_"


class InvalidIntegrationOperation(ValidationError):
    """Nombre duplicado, scopes inválidos, integración no encontrada, etc."""


def _generate_app_key():
    return f"{APP_KEY_PREFIX}{secrets.token_hex(8)}"


def _audit(tenant, *, action, user, integration, **extra):
    """A diferencia de `apps.api.services._audit` (que envuelve en
    `try/except` porque `apps.permissions`/`apps.payroll` se
    construyeron antes de que `apps.audit` existiera), aquí no hace
    falta: `apps.api` ya depende directamente de `apps.audit` desde el
    commit anterior de esta misma fase. Aun así, la auditoría nunca
    debe poder romper la gestión de la integración."""
    try:
        log_event(
            tenant, user=user, action=action, domain="api",
            object_type="integration", object_id=integration.app_key, **extra,
        )
    except Exception:  # noqa: BLE001 — la auditoría nunca debe romper la operación.
        pass


def list_integrations(tenant):
    return Integration.all_objects.filter(tenant=tenant).order_by("name")


def get_integration(tenant, pk):
    return Integration.all_objects.filter(tenant=tenant, pk=pk).first()


def create_integration(tenant, *, user, name, provider, scopes):
    if not is_valid_catalog_scope_list(scopes):
        raise InvalidIntegrationOperation("Uno o más scopes de catálogo no son válidos.")
    if Integration.all_objects.filter(tenant=tenant, name__iexact=name).exists():
        raise InvalidIntegrationOperation(f"Ya existe una integración llamada «{name}» en este tenant.")

    secreto = generate_secret()
    integration = Integration.all_objects.create(
        tenant=tenant, name=name, provider=provider, app_key=_generate_app_key(),
        secret_hash=hash_secret(secreto), scopes=list(scopes), created_by=user,
    )
    _audit(
        tenant, action=AuditLog.Action.INTEGRATION_CREATED, user=user, integration=integration,
        after={"name": name, "provider": provider, "scopes": scopes},
    )
    return integration, secreto


def rotate_integration_credential(integration, *, user):
    """Reemplaza el hash de la MISMA fila — invalida el secreto
    anterior de inmediato, mismo criterio que `rotate_api_key`. El
    `app_key` (identidad pública) NO cambia al rotar — solo el
    secreto; si se necesita una identidad nueva, se crea otra
    integración."""
    secreto = generate_secret()
    integration.secret_hash = hash_secret(secreto)
    integration.status = Integration.Status.ACTIVE
    integration.rotated_at = timezone.now()
    integration.save(update_fields=["secret_hash", "status", "rotated_at"])
    _audit(integration.tenant, action=AuditLog.Action.INTEGRATION_ROTATED, user=user, integration=integration)
    return integration, secreto


def revoke_integration(integration, *, user):
    integration.status = Integration.Status.REVOKED
    integration.revoked_at = timezone.now()
    integration.revoked_by = user
    integration.save(update_fields=["status", "revoked_at", "revoked_by"])
    _audit(integration.tenant, action=AuditLog.Action.INTEGRATION_REVOKED, user=user, integration=integration)
    return integration


def set_integration_enabled(integration, *, is_enabled, user):
    integration.is_enabled = is_enabled
    integration.save(update_fields=["is_enabled"])
    accion = AuditLog.Action.INTEGRATION_ENABLED if is_enabled else AuditLog.Action.INTEGRATION_DISABLED
    _audit(integration.tenant, action=accion, user=user, integration=integration)
    return integration


def set_integration_scopes(integration, *, scopes, user):
    if not is_valid_catalog_scope_list(scopes):
        raise InvalidIntegrationOperation("Uno o más scopes de catálogo no son válidos.")
    antes = list(integration.scopes)
    integration.scopes = list(scopes)
    integration.save(update_fields=["scopes"])
    _audit(
        integration.tenant, action=AuditLog.Action.GENERIC, user=user, integration=integration,
        before={"scopes": antes}, after={"scopes": scopes},
    )
    return integration


def authenticate_integration(secreto):
    """Resuelve una `Integration` activa (`status=ACTIVE`,
    `is_enabled=True`, no expirada) a partir del secreto completo
    recibido en la request — nunca por `app_key` enviado por el
    cliente, nunca por un tenant_id. Devuelve `None` si no hay
    coincidencia, está revocada, deshabilitada o expiró."""
    if not secreto:
        return None
    integration = Integration.all_objects.filter(
        secret_hash=hash_secret(secreto), status=Integration.Status.ACTIVE, is_enabled=True,
    ).first()
    if integration is None:
        return None
    if integration.expires_at is not None and integration.expires_at <= timezone.now():
        return None
    return integration


def touch_last_used(integration):
    Integration.all_objects.filter(pk=integration.pk).update(last_used_at=timezone.now())


def test_integration_connection(integration, *, user):
    """"Probar Conexión": una integración activa y no expirada siempre
    se considera CONECTADO, mismo criterio que `apps.api.services.
    test_connection` (es una prueba de la propia credencial, no de un
    servicio externo)."""
    ahora = timezone.now()
    if integration.status != Integration.Status.ACTIVE:
        resultado_ok, error = False, "La integración está revocada."
    elif not integration.is_enabled:
        resultado_ok, error = False, "La integración está deshabilitada."
    elif integration.expires_at is not None and integration.expires_at <= ahora:
        resultado_ok, error = False, "La integración expiró."
    else:
        resultado_ok, error = True, ""
    integration.last_tested_at = ahora
    integration.last_test_ok = resultado_ok
    integration.last_test_error = error
    integration.save(update_fields=["last_tested_at", "last_test_ok", "last_test_error"])
    _audit(
        integration.tenant, action=AuditLog.Action.API_ACCESS, user=user, integration=integration,
        metadata={"prueba_conexion": True, "resultado": resultado_ok},
    )
    return resultado_ok, error
