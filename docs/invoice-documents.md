# Documentos adjuntos, recibo e impresión (FASE 10)

## Documentos adjuntos: reutiliza FASE 9, no crea un segundo sistema de archivos

`SalesDocumentAttachment` — un único modelo para adjuntos de
Cotización/Proforma/Venta, discriminado por `document_type`
(`quotation`/`proforma`/`sale`) + `document_id` (referencia genérica,
mismo patrón que `SalesActivityLog`). Reutiliza **literalmente**:

- `apps.customers.file_validation.validar_archivo_adjunto`/
  `nombre_original_seguro` — la misma validación en capas (tamaño ≤10MB,
  lista negra de extensiones peligrosas, lista blanca de formatos,
  firma binaria real contra archivos disfrazados) que FASE 9, sin
  reimplementar una sola línea.
- `apps.customers.models.DocumentCategory` — las mismas categorías
  (Identificación, Documento fiscal, Contrato, Certificado,
  Comprobante, Documento bancario, Otro).
- `apps.customers.models.DocumentoBaseMixin` — los mismos campos
  (`category`, `original_filename`, `content_type`, `size_bytes`,
  `uploaded_by`, `uploaded_at`, `notes`), heredado directamente por
  `SalesDocumentAttachment`.

Almacenamiento en `media-private/ventas/<tenant_id>/<document_type>/<document_id>/<uuid>.<ext>`
— nunca servido como estático público (mismo `MEDIA_URL` sin registrar
en `config/urls.py` que FASE 9); descarga solo vía vista protegida
(login + tenant + pertenencia exacta al documento). Limpieza de
archivos huérfanos mediante la misma señal `post_delete` (adaptada para
`SalesDocumentAttachment`, capturando `OSError` sin propagarlo — ver
`docs/customer-documents.md` para el razonamiento completo).

## Recibo / comprobante

`sale_receipt.html`: empresa (nombre del tenant), cliente, número,
fecha, vendedor, líneas (producto, IMEI/serie cuando aplica, cantidad,
precio, descuento, impuesto, total), subtotal/descuento/impuesto/total,
pagos registrados, estado. Reutilizable tal cual por FASE 11 (POS) para
imprimir el comprobante al cerrar una venta.

## Impresión: HTML, no PDF binario

`quotation_print.html`/`proforma_print.html`/`sale_receipt.html` son
vistas HTML normales con una hoja de estilo `@media print` (oculta los
botones de acción, expande el documento a ancho completo) y un botón
"Imprimir / Guardar PDF" que llama a `window.print()` — el navegador
del usuario genera el PDF si así lo elige ("Guardar como PDF" en el
diálogo de impresión de cualquier navegador moderno). **No se generó
un archivo PDF binario en el servidor**: instalar una librería de PDF
(WeasyPrint, ReportLab, etc.) no está aprobado como dependencia nueva
del proyecto sin decisión explícita del usuario, y WeasyPrint en
particular requiere dependencias nativas (GTK) notoriamente difíciles
de instalar en Windows sin Docker. Si en el futuro se requiere un PDF
real generado en servidor (p. ej. para adjuntarlo automáticamente a un
correo), es una decisión de dependencia a tomar explícitamente, no una
implementada por omisión aquí.

## Preparación para facturación fiscal electrónica (no implementada)

Ningún campo fiscal (`tipo`/`serie`/`número`/`estado fiscal`, respuesta
del proveedor, fecha fiscal, identificador externo) se agregó a
`Quotation`/`ProformaInvoice`/`Sale` — no hay ninguna integración fiscal
real que los fuera a usar hoy, y agregar columnas sin ningún dato real
que las llene sería inventar un estado, el mismo error que este
proyecto ha evitado deliberadamente desde FASE 8 (nunca un campo
desnormalizado sin una fuente real). Cuando llegue esa integración, lo
natural es un modelo relacionado nuevo (p. ej. `FiscalDocumentInfo`,
con su propia FK a `Sale`) — no columnas sueltas hoy. No se inventó
ningún estándar fiscal.

## Multi-Tenancy

Mismo patrón que `docs/customer-documents.md`: un `document_pk` de otro
tenant, o de otro documento del mismo tenant, siempre da 404 al
descargar/eliminar.
