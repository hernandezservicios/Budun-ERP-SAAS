"""
Validación de seguridad para documentos adjuntos de Clientes/Proveedores
(FASE 9).

Defensa en profundidad, sin depender de librerías nativas externas (no
hay Docker, y garantizar `libmagic` en Windows sin él no es trivial ni
está aprobado como dependencia del proyecto): la extensión declarada Y
la firma binaria real del archivo (sus primeros bytes) deben ser
consistentes entre sí, además de una lista negra explícita de
extensiones peligrosas y un límite de tamaño. Cualquier discrepancia
(p. ej. un `.exe` renombrado a `.pdf`) se rechaza antes de guardar nada
en disco.

Limitación conocida y documentada (ver `docs/customer-documents.md`):
`.doc`/`.xls` comparten la misma firma binaria (formato OLE de Office
legado) y `.docx`/`.xlsx` comparten la misma firma (ambos son
contenedores ZIP/OOXML). Esta validación no distingue esos dos pares
entre sí — sí garantiza, en ambos casos, que el contenido es realmente
un documento de ese formato general y no un ejecutable/script disfrazado.
"""

import ntpath
import os

from django.core.exceptions import ValidationError

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

FORMATOS_PERMITIDOS_LEGIBLE = "PDF, JPG, JPEG, PNG, DOC, DOCX, XLS, XLSX"

# Extensión -> (firmas binarias válidas al inicio del archivo, tipo MIME a registrar).
_FIRMAS_PERMITIDAS = {
    ".pdf": ((b"%PDF-",), "application/pdf"),
    ".png": ((b"\x89PNG\r\n\x1a\n",), "image/png"),
    ".jpg": ((b"\xff\xd8\xff",), "image/jpeg"),
    ".jpeg": ((b"\xff\xd8\xff",), "image/jpeg"),
    # Formato OLE de Office legado (.doc y .xls son indistinguibles por firma).
    ".doc": ((b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",), "application/msword"),
    ".xls": ((b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",), "application/vnd.ms-excel"),
    # OOXML: contenedor ZIP (.docx y .xlsx son indistinguibles por firma).
    ".docx": ((b"PK\x03\x04",), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": ((b"PK\x03\x04",), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}

# Extensiones/formatos explícitamente prohibidos (defensa adicional y
# explícita, aunque la lista blanca de arriba ya las excluye por
# omisión — pedido explícitamente por el usuario).
EXTENSIONES_PROHIBIDAS = {
    ".exe",
    ".bat",
    ".cmd",
    ".ps1",
    ".dll",
    ".sh",
    ".js",
    ".vbs",
    ".msi",
    ".scr",
    ".com",
    ".jar",
    ".app",
}


def validar_archivo_adjunto(archivo):
    """Valida un `UploadedFile` de Django antes de guardarlo. Lanza
    `ValidationError` (nunca deja pasar un archivo dudoso) si:
    - excede 10 MB;
    - su extensión está explícitamente prohibida;
    - su extensión no está en la lista blanca de formatos permitidos;
    - su contenido (primeros bytes) no coincide con la extensión
      declarada (defensa contra un ejecutable/script disfrazado).

    Devuelve `(extension, content_type_detectado)` cuando el archivo es
    válido, para que el llamador los guarde sin repetir esta lógica.
    """
    nombre = archivo.name or ""
    extension = os.path.splitext(nombre)[1].lower()

    if archivo.size is not None and archivo.size > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError("El archivo supera el límite de 10 MB.")

    if extension in EXTENSIONES_PROHIBIDAS:
        raise ValidationError("Este tipo de archivo no está permitido por seguridad.")

    firma_esperada = _FIRMAS_PERMITIDAS.get(extension)
    if firma_esperada is None:
        raise ValidationError(f"Formato no permitido. Formatos válidos: {FORMATOS_PERMITIDOS_LEGIBLE}.")

    firmas_validas, content_type_detectado = firma_esperada
    archivo.seek(0)
    encabezado = archivo.read(8)
    archivo.seek(0)
    if not any(encabezado.startswith(firma) for firma in firmas_validas):
        raise ValidationError(
            "El contenido del archivo no coincide con su extensión declarada "
            "(posible archivo disfrazado). Sube el archivo original sin renombrarle la extensión."
        )

    return extension, content_type_detectado


def nombre_original_seguro(nombre):
    """Sanitiza el nombre original de un archivo solo para MOSTRARLO en
    la interfaz — el archivo en sí nunca se guarda en disco con este
    valor (ver `models._ruta_documento_cliente`/`_ruta_documento_proveedor`,
    que generan un nombre aleatorio). Elimina separadores de ruta
    (defensa contra path traversal) y caracteres no imprimibles."""
    # Usar ntpath.basename para extraer el nombre base soportando tanto
    # separadores Windows ('\') como Unix ('/') en cualquier sistema operativo.
    nombre = ntpath.basename((nombre or "").strip())
    nombre = nombre.replace("\\", "_").replace("/", "_")
    nombre = "".join(caracter for caracter in nombre if caracter.isprintable())
    return nombre[:255] or "documento"
