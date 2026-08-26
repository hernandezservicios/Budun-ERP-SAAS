"""Construye URLs absolutas y estables para imágenes de catálogo —
compartido por `catalog_serializers.py` y `catalog_views.py` para no
duplicar la lógica de armado de URL."""

from django.urls import reverse


def build_media_url(request, imagen):
    """`imagen` es un `ProductImage`. Devuelve una URL ABSOLUTA (nunca
    relativa — debe ser consumible directamente por un CRM/agente
    externo) apuntando al endpoint público de archivo, identificado
    por `public_id` (UUID no adivinable), nunca por el `id` secuencial."""
    ruta = reverse("catalog:media_file", args=[imagen.public_id])
    if request is not None:
        return request.build_absolute_uri(ruta)
    return ruta
