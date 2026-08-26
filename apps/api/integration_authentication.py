"""
Autenticación por credencial de `Integration` (`Authorization: Bearer
<secreto>`) — la ÚNICA forma de autenticarse ante `/api/v1/catalog/`.
Mismo mecanismo que `apps.api.authentication.ApiKeyAuthentication`
(Bearer + hash), pero resuelve una `Integration` en vez de una
`ApiKey` — nunca la misma credencial ni el mismo modelo: son dos capas
deliberadamente separadas (administrativa vs. comercial, ver
`docs/integrations.md`). El tenant se resuelve SIEMPRE desde la
credencial — nunca de un parámetro enviado por el cliente."""

from rest_framework import authentication, exceptions

from . import integration_services


class IntegrationCredentialAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        encabezado = authentication.get_authorization_header(request).decode("utf-8", errors="ignore")
        if not encabezado:
            return None
        partes = encabezado.split()
        if len(partes) != 2 or partes[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Encabezado Authorization inválido — usa «Bearer <secreto>».")

        integration = integration_services.authenticate_integration(partes[1])
        if integration is None:
            raise exceptions.AuthenticationFailed("Credencial de integración inválida, revocada, deshabilitada o expirada.")

        integration_services.touch_last_used(integration)
        # `request.user` queda `None` deliberadamente (no hay un usuario
        # humano detrás de una integración) — `request.tenant`/
        # `request.integration` son lo que el resto de la Catalog API
        # consulta.
        request.tenant = integration.tenant
        request.integration = integration
        return (None, integration)

    def authenticate_header(self, request):
        return self.keyword
