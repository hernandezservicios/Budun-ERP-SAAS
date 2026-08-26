"""Almacenamiento de imágenes de catálogo (ampliación final de FASE 15,
ver `docs/api-catalog.md`). Carpeta física distinta de `media-private/`
(`settings.CATALOG_MEDIA_ROOT`) — este contenido es explícitamente
público, nunca servido con el mismo mecanismo que los documentos
privados de Clientes/Proveedores.

`base_location` se resuelve de forma PEREZOSA (`cached_property`,
invalidada por la señal `setting_changed` que `FileSystemStorage.__init__`
ya conecta) en vez de fijar la ruta como string en el constructor —
si se hiciera así, `override_settings(CATALOG_MEDIA_ROOT=...)` en los
tests quedaría sin efecto (la ruta ya habría quedado congelada al
importar este módulo, mismo tipo de gotcha ya documentado para
`SimpleRateThrottle.THROTTLE_RATES` de DRF, ver `KNOWN_ISSUES.md` #100)."""

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.functional import cached_property


class CatalogMediaStorage(FileSystemStorage):
    @cached_property
    def base_location(self):
        return self._value_or_setting(self._location, settings.CATALOG_MEDIA_ROOT)

    def _clear_cached_properties(self, setting, **kwargs):
        # `FileSystemStorage._clear_cached_properties` (Django) solo
        # reacciona a los nombres de setting fijos que conoce
        # ("MEDIA_ROOT", "MEDIA_URL", ...) — nunca a un nombre
        # personalizado como `CATALOG_MEDIA_ROOT`. Sin este override,
        # `override_settings(CATALOG_MEDIA_ROOT=...)` en los tests no
        # tendría ningún efecto (la propiedad ya calculada quedaría en
        # caché para siempre).
        if setting == "CATALOG_MEDIA_ROOT":
            self.__dict__.pop("base_location", None)
            self.__dict__.pop("location", None)
        else:
            super()._clear_cached_properties(setting, **kwargs)


catalog_media_storage = CatalogMediaStorage()
