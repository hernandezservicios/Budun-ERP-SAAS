# Documentos de Clientes (FASE 9)

Documentos adjuntos por cliente (`CustomerDocument`), pedidos
explícitamente por el usuario como parte de un módulo "profesional" de
Clientes. Ver `docs/supplier-documents.md` para la contraparte de
proveedores (arquitectura idéntica, modelo separado).

## Modelo

`CustomerDocument` hereda `TenantScopedModel` + el mixin
`DocumentoBaseMixin` (compartido con `SupplierDocument`):

| Campo | Notas |
|---|---|
| `customer` | FK a `Customer`, `on_delete=PROTECT` (protege el historial de auditoría) |
| `file` | El archivo en sí — guardado con nombre generado, nunca el original (ver "Seguridad") |
| `category` | Identificación, Documento fiscal, Contrato, Certificado, Comprobante, Documento bancario, Otro — extensible sin migración estructural (`choices`) |
| `original_filename` | Nombre saneado, solo para MOSTRAR en la interfaz |
| `content_type` | Tipo MIME detectado por firma binaria real (no el declarado por el navegador) |
| `size_bytes` | Tamaño real |
| `uploaded_by` / `uploaded_at` | Auditoría de quién y cuándo |
| `notes` | Notas libres opcionales |

## Formatos permitidos y límite de tamaño

PDF, JPG, JPEG, PNG, DOC, DOCX, XLS, XLSX. Límite: **10 MB** por
archivo (`file_validation.MAX_UPLOAD_SIZE_BYTES`), aplicado tanto en la
validación explícita como en `DATA_UPLOAD_MAX_MEMORY_SIZE`/
`FILE_UPLOAD_MAX_MEMORY_SIZE` de Django (`config/settings.py`).

## Validación de seguridad (`apps/customers/file_validation.py`)

Sin depender de librerías nativas externas (no hay Docker, y garantizar
`libmagic` en Windows sin él no es trivial ni está aprobado como
dependencia del proyecto): la validación combina varias capas, todas
en Python puro (stdlib):

1. **Tamaño**: se rechaza cualquier archivo mayor a 10 MB antes de
   guardar nada.
2. **Lista negra explícita**: `.exe`, `.bat`, `.cmd`, `.ps1`, `.dll`,
   `.sh`, `.js`, `.vbs`, `.msi`, `.scr`, `.com`, `.jar`, `.app` se
   rechazan sin más comprobación (pedido explícitamente por el
   usuario).
3. **Lista blanca de extensión**: solo se acepta una extensión de la
   lista de formatos permitidos.
4. **Firma binaria (magic bytes)**: los primeros bytes del archivo deben
   coincidir con la firma real del formato declarado por la extensión
   (p. ej. `%PDF-` para PDF, `\x89PNG\r\n\x1a\n` para PNG,
   `\xff\xd8\xff` para JPEG, `PK\x03\x04` para DOCX/XLSX,
   `\xd0\xcf\x11\xe0...` para DOC/XLS legado). Esta es la defensa
   central contra un **archivo disfrazado** (p. ej. un `.exe` renombrado
   a `.pdf`): la extensión puede mentir, el contenido no.

**Limitación conocida y documentada**: `.doc`/`.xls` comparten la misma
firma (formato OLE de Office legado) y `.docx`/`.xlsx` comparten la
misma firma (ambos son contenedores ZIP/OOXML). La validación no
distingue esos dos pares entre sí — sí garantiza, en ambos casos, que el
contenido es realmente un documento de ese formato general y no un
ejecutable/script disfrazado. Una validación más profunda (parsear el
XML interno de un OOXML, o los streams de un OLE) exigiría una
dependencia adicional no aprobada; se documenta como limitación
explícita en vez de fingir una garantía que no se puede dar hoy.

## Nombres de archivo: nunca el original en disco

El archivo se guarda con un nombre generado
(`uuid4().hex + extensión`, organizado por tenant y cliente:
`clientes/<tenant_id>/<customer_id>/<uuid>.<ext>`), nunca con el nombre
que subió el usuario. El nombre original se guarda por separado
(`original_filename`, saneado con `nombre_original_seguro`: quita
separadores de ruta y caracteres no imprimibles) solo para mostrarlo en
la interfaz. Esto es la defensa central contra:
- **Path traversal**: un nombre como `../../etc/passwd` nunca llega a
  formar parte de la ruta real en disco.
- **Colisiones**: dos archivos con el mismo nombre original no chocan.
- **Nombres inseguros**: caracteres de control, rutas absolutas, etc.
  nunca se usan para construir una ruta de archivo real.

## Almacenamiento: `media-private/`, nunca servido como público

`MEDIA_ROOT = BASE_DIR / "media-private"` (ya estaba en `.gitignore`
desde FASE 1, anticipando este uso). Deliberadamente **NO** se registra
`static(MEDIA_URL, document_root=MEDIA_ROOT)` en `config/urls.py`: eso
serviría cualquier archivo como estático público, sin autenticación ni
verificación de tenant, apenas alguien adivinara la ruta. La única forma
de obtener el contenido de un documento es la vista de descarga
protegida.

## Descarga controlada y protegida

`CustomerDocumentDownloadView` (y su equivalente de proveedor) exige:
login (`LoginRequiredMixin`) + tenant activo (`TenantRequiredMixin`) +
que el documento pertenezca exactamente al `customer` de la URL, dentro
del tenant de la request — un `document_pk` real de otro cliente (aunque
sea del mismo tenant) o de otro tenant da 404, nunca el contenido.
Cada descarga se registra en `ActivityLog` (`DOCUMENT_DOWNLOADED`).

## Archivos huérfanos: cerrado por diseño con una señal `post_delete`

Un `queryset.delete()` masivo, el admin, o un futuro cascade NO deberían
dejar un archivo físico sin su fila en la base de datos ("archivo
huérfano"). En vez de exigir que cada código de borrado recuerde
limpiar el archivo a mano, se conectó un receptor `post_delete` en
`models.py` (`_eliminar_archivo_al_borrar_documento`) para
`CustomerDocument`/`SupplierDocument`: Django envía esa señal para cada
instancia individual en cualquier camino de borrado en cuanto hay un
receptor conectado (desactiva la optimización de "fast delete" del
ORM para ese modelo), así que el archivo se limpia siempre, sin importar
por dónde se borre la fila. Si el borrado físico falla (p. ej. el
archivo está momentáneamente bloqueado por otro proceso — se observó en
desarrollo en Windows, ver `KNOWN_ISSUES.md`), se registra el error con
`logging` pero nunca se propaga como un 500: la fila ya se borró de
PostgreSQL (la fuente de verdad), y no tiene sentido convertir un
problema de limpieza de disco en un error para el usuario.

## Auditoría

Cada subida, descarga y eliminación de documento se registra en
`ActivityLog` (ver `docs/customers.md`), con tenant, usuario y el
nombre del archivo — nunca el archivo completo ni datos sensibles de su
contenido.

## Multi-Tenancy: cobertura de tests

`test_isolation.py` verifica explícitamente: Tenant A no puede
descargar, eliminar ni subir un documento a un cliente de Tenant B; ni
siquiera combinando el `pk` real de un cliente propio con el
`document_pk` real de un documento ajeno (perteneciente a otro cliente)
se expone o afecta nada — la vista exige coincidencia exacta
documento↔cliente↔tenant, las tres a la vez.

## Qué NO se construyó (deliberado)

Vista previa embebida de documentos (solo descarga), versionado de
documentos, firma electrónica, OCR/extracción de texto, escaneo
antivirus de contenido (fuera del alcance razonable sin una dependencia
externa aprobada).
