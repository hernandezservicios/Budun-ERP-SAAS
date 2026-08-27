"""
Throttling de intentos de autenticación (FASE 18 — Security Hardening).

Hallazgo ya documentado desde FASE 4 (`docs/authentication.md`,
"Pendiente deliberadamente fuera de alcance") y confirmado en la
sincronización de FASE 18 (`docs/security.md`): ni el login ni la
recuperación de contraseña tenían ningún límite de intentos, dejando
ambos flujos abiertos a fuerza bruta / credential stuffing / abuso de
envío de correos. Esta corrección lo cierra sin infraestructura
nueva: usa el mismo `CACHES["default"]` (`LocMemCache`, un solo
proceso) ya configurado en `config/settings.py` — Redis sigue
deferido hasta que una fase futura demuestre necesidad real (mismo
criterio ya aplicado a `apps.api.throttling`).

Dos ejes de bloqueo, deliberadamente separados:
- Por IDENTIFICADOR (email normalizado): protege una cuenta concreta
  contra intentos distribuidos entre muchas IPs.
- Por IP: protege contra un atacante que prueba muchas cuentas desde
  el mismo origen.

Ambos se registran/consultan con la misma primitiva genérica
(`register_attempt`/`is_blocked`/`reset`), reutilizable también para
la recuperación de contraseña (dos scopes distintos, nunca comparten
contador con el login)."""

from django.core.cache import cache

_PREFIX = "accounts:throttle"


def _cache_key(scope, identifier):
    return f"{_PREFIX}:{scope}:{identifier}"


def is_blocked(scope, identifier, *, max_attempts):
    """`True` si `identifier` ya alcanzó o superó `max_attempts` dentro
    de la ventana vigente para `scope`. Nunca lanza si la clave no
    existe todavía (cuenta en 0)."""
    if not identifier:
        return False
    count = cache.get(_cache_key(scope, identifier), 0)
    return count >= max_attempts


def register_attempt(scope, identifier, *, window_seconds):
    """Incrementa el contador de intentos de `identifier` para `scope`,
    creando la ventana (`window_seconds`) si no existía. Carrera
    aceptable en `LocMemCache` de un solo proceso: en el peor caso dos
    hilos pierden un incremento, lo que a lo sumo permite un intento
    de más — nunca un bloqueo indebido de un usuario legítimo."""
    if not identifier:
        return
    key = _cache_key(scope, identifier)
    # `cache.add` solo crea la clave si no existe (arranca la ventana);
    # si ya existe, `incr` falla con `ValueError` si expiró entre medio
    # (ventana de carrera muy pequeña) — se recrea en ese caso.
    created = cache.add(key, 0, timeout=window_seconds)
    if created:
        cache.incr(key)
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)


def reset(scope, identifier):
    """Limpia el contador — se llama tras una autenticación exitosa
    para que un usuario legítimo nunca quede penalizado por intentos
    fallidos previos una vez que ya demostró la contraseña correcta."""
    if not identifier:
        return
    cache.delete(_cache_key(scope, identifier))
