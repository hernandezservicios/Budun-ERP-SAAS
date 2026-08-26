"""
Generación/hash de secretos — compartido por `ApiKey` (Inventory API) e
`Integration` (Catalog API, ampliación final de FASE 15) para no
duplicar el mismo mecanismo criptográfico en dos lugares (ver
`docs/integrations.md`). SHA-256 es apropiado aquí porque el secreto
ya es aleatorio de alta entropía (`secrets.token_urlsafe`, nunca
`random`) — a diferencia de una contraseña humana, que sí necesita un
hash lento. El secreto en texto plano NUNCA se guarda en ningún lugar:
solo existe como valor de retorno de `generate_secret()`, en el
momento de la creación/rotación."""

import hashlib
import secrets


def generate_secret():
    return secrets.token_urlsafe(32)


def hash_secret(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()
