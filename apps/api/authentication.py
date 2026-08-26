"""
Autenticación por API Key (`Authorization: Bearer <clave>`) — la ÚNICA
forma de autenticarse ante `/api/v1/`. Nunca sesión/cookie/JWT
genérico (`REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = []` en
`config/settings.py`; esta clase se asigna explícitamente por vista).
El tenant se resuelve SIEMPRE desde la credencial — nunca de un
parámetro enviado por el cliente (mismo principio de FASE 3)."""

from rest_framework import authentication, exceptions

from . import services


class ApiKeyAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        encabezado = authentication.get_authorization_header(request).decode("utf-8", errors="ignore")
        if not encabezado:
            return None
        partes = encabezado.split()
        if len(partes) != 2 or partes[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Encabezado Authorization inválido — usa «Bearer <clave>».")

        api_key = services.authenticate_api_key(partes[1])
        if api_key is None:
            raise exceptions.AuthenticationFailed("Clave de API inválida, revocada o expirada.")

        services.touch_last_used(api_key)
        # `request.user` queda `None` deliberadamente (no hay un
        # usuario humano detrás de una API Key) — `request.tenant`/
        # `request.api_key` son lo que el resto de la API consulta.
        request.tenant = api_key.tenant
        request.api_key = api_key
        return (None, api_key)

    def authenticate_header(self, request):
        return self.keyword
