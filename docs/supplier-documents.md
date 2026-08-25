# Documentos de Proveedores (FASE 9)

`SupplierDocument` es la contraparte exacta de `CustomerDocument` para
proveedores — ver `docs/customer-documents.md` para el diseño completo
(formatos permitidos, límite de tamaño, validación de firma binaria,
nombres de archivo seguros, almacenamiento en `media-private/`,
descarga protegida, limpieza de archivos huérfanos vía señal
`post_delete`, auditoría, cobertura de Multi-Tenancy). Todo aplica
idéntico, cambiando únicamente:

| | Cliente | Proveedor |
|---|---|---|
| Modelo | `CustomerDocument` | `SupplierDocument` |
| FK al dueño | `customer` (`Customer`) | `supplier` (`Supplier`) |
| Ruta en disco | `clientes/<tenant_id>/<customer_id>/<uuid>.<ext>` | `proveedores/<tenant_id>/<supplier_id>/<uuid>.<ext>` |
| Vistas | `SupplierDocumentUploadView`/`DeleteView`/`DownloadView` (mismas bases compartidas `_ContactDocument*` en `views.py`) | ídem |

Ambos modelos comparten `DocumentoBaseMixin` (`category`,
`original_filename`, `content_type`, `size_bytes`, `uploaded_by`,
`uploaded_at`, `notes`) y las mismas categorías de documento
(`DocumentCategory`), para que la experiencia sea idéntica desde
cualquiera de los dos módulos.

## Qué NO se construyó (deliberado)

Igual que `docs/customer-documents.md`.
