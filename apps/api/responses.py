"""
Sobre de respuesta consistente de `/api/v1/` — TODA respuesta (éxito o
error) tiene la forma `{"success", "data", "meta", "errors"}`, nunca
un cuerpo "desnudo". `meta` lleva paginación cuando aplica; `errors`
es siempre una lista de `{"code", "detail"}` (nunca un traceback ni
un mensaje interno de Django/Python)."""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def build_success_response(data, *, meta=None, status_code=status.HTTP_200_OK):
    return Response({"success": True, "data": data, "meta": meta or {}, "errors": None}, status=status_code)


def build_error_response(*, code, detail, status_code):
    return Response(
        {"success": False, "data": None, "meta": {}, "errors": [{"code": code, "detail": detail}]},
        status=status_code,
    )


_CODIGOS_POR_STATUS = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
    405: "method_not_allowed", 409: "conflict", 429: "rate_limited",
}


def api_exception_handler(exc, context):
    """`EXCEPTION_HANDLER` de DRF para todo `/api/v1/` — nunca deja
    escapar un traceback interno; todo error conocido de DRF se
    reformatea al sobre estándar, y cualquier excepción no manejada
    por DRF (bug real) se registra en el log del servidor y se
    responde como 500 genérico, sin detalle interno."""
    respuesta = drf_exception_handler(exc, context)
    if respuesta is not None:
        codigo = _CODIGOS_POR_STATUS.get(respuesta.status_code, "error")
        detalle = respuesta.data.get("detail", respuesta.data) if isinstance(respuesta.data, dict) else respuesta.data
        return build_error_response(code=codigo, detail=str(detalle), status_code=respuesta.status_code)

    logger.exception("Error no manejado en /api/v1/: %s", exc)
    return build_error_response(
        code="internal_error", detail="Ocurrió un error interno.", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
