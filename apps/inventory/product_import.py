"""
Importación y exportación masiva de productos vía Excel (extensión de
FASE 8 — ver `docs/products.md`, `ADENDUM_FASE_8_IMPORTACION_PRODUCTOS_EXCEL.md`).

Arquitectura (mismo criterio que el resto de `apps.inventory`): este
módulo es la ÚNICA vía para parsear/validar/aplicar un archivo de
importación — ninguna vista toca `openpyxl` ni el modelo `Product`
directamente. Reutiliza siempre infraestructura ya existente, nunca la
duplica:
- `apps.customers.file_validation` para la validación de seguridad del
  archivo (extensión + firma binaria + tamaño), igual que
  `PaymentProof` (FASE 17/18).
- `apps.reports.exports.xlsx_response` para CADA salida `.xlsx`
  (plantilla, exportación de productos, reporte de errores) — ya
  sanitiza cada celda contra CSV/XLSX Formula Injection
  (`apps.core.utils.sanitize_cell_value`, FASE 18), nunca un escritor
  de Excel paralelo.
- `apps.inventory.services.product_has_inventory_history` para la
  MISMA regla que ya impedía cambiar `inventory_tracking_type` desde
  el formulario manual (`ProductForm`).

Diseño clave: NUNCA se persiste el archivo `.xlsx` subido. Se parsea y
valida una sola vez al subir; el resultado ya normalizado
(`ProductImportBatch.preview_data`) es lo único que se usa para
aplicar el lote al confirmar. Esto evita por completo el problema de
"almacenamiento temporal seguro / eliminación de temporales": no hay
ningún archivo temporal que gestionar ni limpiar.

Semántica CREATE vs. UPDATE de una celda en blanco (documentada
explícitamente, ver `docs/products.md`): en un CREATE, una columna
opcional en blanco usa el mismo default que el modelo `Product`. En un
UPDATE, una columna opcional en blanco significa "no cambiar este
campo" — nunca "vaciar/reiniciar a su default" — así una fila que no
repite todas las columnas para un producto ya existente nunca borra
sus datos actuales por accidente. Las columnas obligatorias (SKU,
Nombre, Precio de venta) no pueden estar en blanco en ningún caso.
"""

import zipfile
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from openpyxl import load_workbook

from apps.customers.file_validation import nombre_original_seguro, validar_archivo_adjunto
from apps.reports.exports import xlsx_response

from . import services
from .models import Category, Product, ProductImportBatch

MAX_FILAS_IMPORTACION = 5000

# (header oficial, clave interna, obligatoria). El header se compara
# normalizado (recortado, sin distinguir mayúsculas/minúsculas) — el
# ORDEN de las columnas en el archivo subido no importa, se identifican
# siempre por nombre de encabezado, nunca por posición (más robusto
# ante un usuario que reordena columnas en Excel).
COLUMNAS = [
    ("SKU *", "sku", True),
    ("Nombre *", "name", True),
    ("Código de barras", "barcode", False),
    ("Categoría", "category", False),
    ("Descripción", "description", False),
    ("Marca", "brand", False),
    ("Modelo", "model_name", False),
    ("Tipo de seguimiento", "inventory_tracking_type", False),
    ("Precio de venta *", "sale_price", True),
    ("Precio de compra", "purchase_price", False),
    ("Impuesto (%)", "tax_rate", False),
    ("Stock mínimo", "min_stock", False),
    ("Activo", "is_active", False),
    ("Atributos de variante", "variant_attributes", False),
]
_CLAVE_POR_HEADER = {header.strip().lower(): clave for header, clave, _obligatoria in COLUMNAS}
_HEADERS_OFICIALES = [header for header, _clave, _obligatoria in COLUMNAS]
_OBLIGATORIAS = {clave for _header, clave, obligatoria in COLUMNAS if obligatoria}

_TRACKING_POR_TEXTO = {
    "": Product.TrackingType.QUANTITY,
    "quantity": Product.TrackingType.QUANTITY,
    "por cantidad": Product.TrackingType.QUANTITY,
    "cantidad": Product.TrackingType.QUANTITY,
    "serialized": Product.TrackingType.SERIALIZED,
    "serializado": Product.TrackingType.SERIALIZED,
}
_VERDADERO_POR_TEXTO = {"si", "sí", "true", "1", "activo", "yes", "verdadero"}
_FALSO_POR_TEXTO = {"no", "false", "0", "inactivo", "falso"}

# Caracteres con los que Excel interpretaría el valor como el INICIO de
# una fórmula — mismo criterio que `apps.core.utils.sanitize_cell_value`
# (FASE 18), pero aquí para RECHAZAR en vez de escapar: un valor
# importado nunca debe guardarse con apariencia de fórmula. Solo "="/"@"
# (nunca "+"/"-": son comunes al inicio de SKUs/nombres legítimos, y
# los campos numéricos ya rechazan naturalmente cualquier texto no
# numérico al intentar convertirlo a Decimal).
_DISPARADORES_FORMULA_TEXTO = ("=", "@")


class ProductImportError(ValidationError):
    """Error de validación del ARCHIVO completo (antes de construir
    ninguna fila de preview) — headers/tamaño/límite de filas."""


class InvalidImportOperation(ValidationError):
    """Se lanza al intentar confirmar un lote que no puede confirmarse
    (ya procesado, con errores, o un conflicto real detectado recién al
    aplicar — ver `apply_import_batch`)."""


# ------------------------------------------------------------------
# Validación de archivo (seguridad)
# ------------------------------------------------------------------


def _archivo_contiene_macros(archivo):
    """`.xlsm`/`.xlsb` comparten la misma firma binaria ZIP que `.xlsx`
    (ambos son contenedores OOXML) — `validar_archivo_adjunto` no los
    distingue por firma. Defensa adicional explícita: un archivo OOXML
    con macros siempre incluye `xl/vbaProject.bin` en su contenido ZIP
    interno, sin importar la extensión declarada."""
    archivo.seek(0)
    try:
        with zipfile.ZipFile(archivo) as zf:
            tiene_macro = "xl/vbaProject.bin" in zf.namelist()
    except zipfile.BadZipFile:
        tiene_macro = False  # ya lo habría rechazado validar_archivo_adjunto por firma inválida
    finally:
        archivo.seek(0)
    return tiene_macro


def validar_archivo_importacion(archivo):
    """Valida el archivo subido antes de intentar parsearlo. Lanza
    SIEMPRE `ProductImportError` (nunca deja pasar un archivo dudoso,
    y nunca deja escapar el `ValidationError` genérico de
    `apps.customers.file_validation` sin envolver — el llamador de
    este módulo solo necesita atrapar un único tipo de excepción)."""
    nombre = archivo.name or ""
    if not nombre.lower().endswith(".xlsx"):
        raise ProductImportError("Solo se aceptan archivos .xlsx (Excel).")
    try:
        extension, _content_type = validar_archivo_adjunto(archivo)
    except ValidationError as error:
        raise ProductImportError(error.messages[0] if error.messages else str(error)) from error
    if extension != ".xlsx":
        raise ProductImportError("Solo se aceptan archivos .xlsx (Excel).")
    if _archivo_contiene_macros(archivo):
        raise ProductImportError(
            "El archivo contiene macros — por seguridad, sube una plantilla .xlsx sin macros."
        )


# ------------------------------------------------------------------
# Plantilla y exportación
# ------------------------------------------------------------------


def generar_plantilla_xlsx():
    """Plantilla descargable: encabezados oficiales + una fila de
    instrucciones (SKU empieza con "#", ver `_es_fila_de_comentario` —
    el parser la ignora si el usuario la deja al importar) + dos filas
    de ejemplo reales (una por cantidad, una serializada). No incluye
    ningún campo interno/sensible (nunca IMEI/serial/costos internos/
    IDs de base de datos)."""
    instrucciones = (
        "Completa una fila por producto. Las columnas con * son obligatorias. "
        "El orden de las columnas no importa (se leen por nombre de encabezado). "
        "'Tipo de seguimiento': 'Por cantidad' o 'Serializado'. "
        "'Atributos de variante': formato clave:valor;clave:valor (ej. color:Negro;capacidad:256GB). "
        "'Activo': Sí/No. Esta fila de instrucciones se ignora al importar (empieza con #)."
    )
    fila_instrucciones = ["#" + instrucciones] + [""] * (len(_HEADERS_OFICIALES) - 1)
    ejemplo_1 = [
        "EJEMPLO-001", "Camiseta azul talla M", "7501234567890", "Ropa",
        "Camiseta de algodón", "MarcaEjemplo", "", "Por cantidad",
        "450.00", "250.00", "18", "5", "Sí", "color:Azul;talla:M",
    ]
    ejemplo_2 = [
        "EJEMPLO-002", "Teléfono modelo X", "", "Electrónica",
        "Equipo con IMEI (la plantilla general no carga unidades — ver docs/products.md)",
        "MarcaEjemplo", "Modelo X", "Serializado",
        "12000.00", "8000.00", "18", "0", "Sí", "color:Negro;capacidad:128GB",
    ]
    return xlsx_response(
        filename="plantilla_productos.xlsx", sheet_title="Productos",
        header=_HEADERS_OFICIALES, rows=[fila_instrucciones, ejemplo_1, ejemplo_2],
    )


def exportar_productos_xlsx(tenant):
    """`Productos → Exportar Excel`. Mismas columnas que la plantilla
    (permite editar y volver a importar) — solo campos comerciales,
    nunca IMEI/serial/costos internos de `InventoryUnit`/`StockMovement`.
    Respeta tenant (siempre filtrado por `tenant=`, nunca `all_objects`
    sin filtro) — el permiso lo exige la vista."""
    productos = (
        # `all_objects` explícito (nunca el manager tenant-scoped por
        # defecto): esta es una función de SERVICIO, debe dar el mismo
        # resultado se llame desde una request HTTP real o desde
        # cualquier otro contexto (test, script, comando) — mismo
        # criterio que el resto de `apps.inventory.services` y de
        # `apps.billing`/`apps.reports` (ver KNOWN_ISSUES #90/#95/#97/#108).
        Product.all_objects.filter(tenant=tenant).select_related("category").order_by("name")
    )
    filas = []
    for producto in productos:
        filas.append([
            producto.sku, producto.name, producto.barcode,
            producto.category.name if producto.category_id else "",
            producto.description, producto.brand, producto.model_name,
            producto.get_inventory_tracking_type_display(),
            str(producto.sale_price), str(producto.purchase_price),
            str(producto.tax_rate), str(producto.min_stock),
            "Sí" if producto.is_active else "No",
            _variant_attributes_a_texto(producto.variant_attributes),
        ])
    return xlsx_response(filename="productos.xlsx", sheet_title="Productos", header=_HEADERS_OFICIALES, rows=filas)


def generar_reporte_errores_xlsx(batch):
    header = ["Fila", "Columna", "Valor", "Motivo"]
    filas = [(error["row"], error["column"], error["value"], error["reason"]) for error in batch.errors_data]
    return xlsx_response(
        filename=f"errores_{batch.reference}.xlsx", sheet_title="Errores", header=header, rows=filas,
    )


def _variant_attributes_a_texto(atributos):
    if not atributos:
        return ""
    return ";".join(f"{clave}:{valor}" for clave, valor in atributos.items())


# ------------------------------------------------------------------
# Parseo y validación (subir → preview)
# ------------------------------------------------------------------


def _texto_celda(valor):
    """Normaliza cualquier valor de celda de openpyxl a texto — un SKU
    tecleado como número en Excel (ej. 123) llega como `float`/`int`,
    nunca como texto: se convierte sin el sufijo `.0` que produciría
    `str(123.0)`."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _es_fila_de_comentario(valores_por_clave):
    # Se identifica por la columna SKU específicamente (nunca por
    # posición física): el orden de columnas en el archivo no importa
    # en ningún otro punto de este módulo, esta comprobación no puede
    # ser la excepción.
    return valores_por_clave.get("sku", "").startswith("#")


def _es_fila_vacia(fila_textos):
    return not any(fila_textos)


def _parsear_decimal(texto, *, campo, fila, errores, permitir_vacio=True, default=Decimal("0")):
    if texto == "":
        return default if permitir_vacio else None
    if texto.startswith(_DISPARADORES_FORMULA_TEXTO):
        errores.append({"row": fila, "column": campo, "value": texto, "reason": "El valor tiene apariencia de fórmula — no se acepta."})
        return None
    try:
        valor = Decimal(texto.replace(",", ""))
    except InvalidOperation:
        errores.append({"row": fila, "column": campo, "value": texto, "reason": "No es un número válido."})
        return None
    if valor < 0:
        errores.append({"row": fila, "column": campo, "value": texto, "reason": "No puede ser negativo."})
        return None
    return valor.quantize(Decimal("0.01")) if campo != "Stock mínimo" else valor.quantize(Decimal("0.001"))


def _parsear_booleano(texto, *, campo, fila, errores, default=True):
    if texto == "":
        return default
    normalizado = texto.strip().lower()
    if normalizado in _VERDADERO_POR_TEXTO:
        return True
    if normalizado in _FALSO_POR_TEXTO:
        return False
    errores.append({"row": fila, "column": campo, "value": texto, "reason": "Usa Sí/No."})
    return None


def _parsear_tracking(texto, *, fila, errores):
    normalizado = texto.strip().lower()
    if normalizado in _TRACKING_POR_TEXTO:
        return _TRACKING_POR_TEXTO[normalizado]
    errores.append({"row": fila, "column": "Tipo de seguimiento", "value": texto, "reason": "Usa 'Por cantidad' o 'Serializado'."})
    return None


def _parsear_variant_attributes(texto, *, fila, errores):
    if texto == "":
        return {}
    if texto.startswith(_DISPARADORES_FORMULA_TEXTO):
        errores.append({"row": fila, "column": "Atributos de variante", "value": texto, "reason": "El valor tiene apariencia de fórmula — no se acepta."})
        return None
    atributos = {}
    for par in texto.split(";"):
        par = par.strip()
        if not par:
            continue
        if ":" not in par:
            errores.append({"row": fila, "column": "Atributos de variante", "value": texto, "reason": f"Formato inválido en «{par}» — usa clave:valor."})
            return None
        clave, _sep, valor = par.partition(":")
        atributos[clave.strip()] = valor.strip()
    return atributos


def _validar_texto_simple(texto, *, campo, fila, errores, max_length, requerido):
    if texto == "":
        if requerido:
            errores.append({"row": fila, "column": campo, "value": "", "reason": "Es obligatorio."})
            return None
        return ""
    if texto.startswith(_DISPARADORES_FORMULA_TEXTO):
        errores.append({"row": fila, "column": campo, "value": texto, "reason": "El valor tiene apariencia de fórmula — no se acepta."})
        return None
    if len(texto) > max_length:
        errores.append({"row": fila, "column": campo, "value": texto, "reason": f"Supera el máximo de {max_length} caracteres."})
        return None
    return texto


def build_preview(tenant, archivo, *, user):
    """Parsea y valida el archivo completo, y crea el `ProductImportBatch`
    (siempre — con o sin errores, el lote guarda el resultado completo
    para mostrarlo en el preview; solo un lote SIN errores puede
    confirmarse, ver `ProductImportBatch.can_confirm`). Consultas en
    BLOQUE (nunca una por fila): un solo `filter(sku__in=...)`, un solo
    `filter(barcode__in=...)`, categorías del tenant cargadas una vez —
    el conteo de queries no crece con el número de filas del archivo."""
    validar_archivo_importacion(archivo)

    # `data_only=False` (el default de openpyxl) es DELIBERADO: si una
    # celda contiene una fórmula, `cell.value` devuelve el TEXTO de la
    # fórmula ("=SUM(...)"), nunca su resultado cacheado — así el
    # rechazo de "valores con apariencia de fórmula" (más abajo) puede
    # detectarla siempre. Con `data_only=True`, una fórmula sin caché
    # calculado (ej. un archivo nunca abierto en Excel real) se leería
    # como `None`, perdiendo silenciosamente el dato en vez de
    # rechazarlo explícitamente.
    libro = load_workbook(archivo, data_only=False, read_only=True)
    hoja = libro.active
    filas_hoja = list(hoja.iter_rows(values_only=True))
    if not filas_hoja:
        raise ProductImportError("El archivo está vacío.")

    encabezados_crudos = [(_texto_celda(valor)) for valor in filas_hoja[0]]
    columna_a_clave = {}
    for indice, encabezado in enumerate(encabezados_crudos):
        if not encabezado:
            continue
        clave = _CLAVE_POR_HEADER.get(encabezado.strip().lower())
        if clave is None:
            raise ProductImportError(f"Columna desconocida en la plantilla: «{encabezado}».")
        columna_a_clave[indice] = clave
    faltantes = _OBLIGATORIAS - set(columna_a_clave.values())
    if faltantes:
        nombres = ", ".join(h for h, c, _o in COLUMNAS if c in faltantes)
        raise ProductImportError(f"Faltan columnas obligatorias: {nombres}.")

    filas_datos_crudas = filas_hoja[1:]
    if len(filas_datos_crudas) > MAX_FILAS_IMPORTACION:
        raise ProductImportError(
            f"El archivo tiene más de {MAX_FILAS_IMPORTACION} filas — divide la importación en lotes más pequeños."
        )

    errores = []
    advertencias = []
    filas_validas = []  # [{"row": n, "sku": ..., "valores": {clave: texto crudo}}]
    contador_sku_archivo = {}

    for indice_fila, fila_cruda in enumerate(filas_datos_crudas, start=2):
        valores_por_clave = {}
        for indice_columna, valor_crudo in enumerate(fila_cruda or ()):
            clave = columna_a_clave.get(indice_columna)
            if clave:
                valores_por_clave[clave] = _texto_celda(valor_crudo)
        if _es_fila_de_comentario(valores_por_clave):
            continue
        if _es_fila_vacia(list(valores_por_clave.values())):
            continue

        sku = valores_por_clave.get("sku", "").strip()
        if sku:
            contador_sku_archivo[sku] = contador_sku_archivo.get(sku, 0) + 1
        filas_validas.append({"row": indice_fila, "valores": valores_por_clave})

    if not filas_validas:
        raise ProductImportError("El archivo no tiene ninguna fila de datos (además del encabezado).")

    skus_duplicados_en_archivo = {sku for sku, cantidad in contador_sku_archivo.items() if cantidad > 1}

    skus_del_archivo = [f["valores"].get("sku", "").strip() for f in filas_validas if f["valores"].get("sku", "").strip()]
    productos_existentes_por_sku = {
        p.sku: p for p in Product.all_objects.filter(tenant=tenant, sku__in=skus_del_archivo)
    }
    barcodes_del_archivo = [
        f["valores"].get("barcode", "").strip() for f in filas_validas if f["valores"].get("barcode", "").strip()
    ]
    productos_existentes_por_barcode = {
        p.barcode: p for p in Product.all_objects.filter(tenant=tenant, barcode__in=barcodes_del_archivo)
    } if barcodes_del_archivo else {}
    categorias_por_nombre = {
        c.name.strip().lower(): c for c in Category.all_objects.filter(tenant=tenant)
    }

    preview_rows = []
    contador_barcode_archivo = {}
    for barcode in barcodes_del_archivo:
        contador_barcode_archivo[barcode] = contador_barcode_archivo.get(barcode, 0) + 1

    for fila in filas_validas:
        n = fila["row"]
        v = fila["valores"]
        errores_antes = len(errores)

        sku = _validar_texto_simple(v.get("sku", ""), campo="SKU", fila=n, errores=errores, max_length=64, requerido=True)
        if sku and sku in skus_duplicados_en_archivo:
            errores.append({"row": n, "column": "SKU", "value": sku, "reason": "SKU duplicado dentro del archivo."})
            sku = None

        producto_existente = productos_existentes_por_sku.get(sku) if sku else None
        accion = "UPDATE" if producto_existente else "CREATE"

        # Obligatorio solo en CREATE — en UPDATE, en blanco significa
        # "no cambiar el nombre actual" (misma regla que el resto de
        # columnas opcionales, ver docstring del módulo).
        nombre = _validar_texto_simple(v.get("name", ""), campo="Nombre", fila=n, errores=errores, max_length=200, requerido=(accion == "CREATE"))

        barcode_texto = v.get("barcode", "").strip()
        barcode = _validar_texto_simple(barcode_texto, campo="Código de barras", fila=n, errores=errores, max_length=64, requerido=False)
        if barcode:
            if contador_barcode_archivo.get(barcode, 0) > 1:
                errores.append({"row": n, "column": "Código de barras", "value": barcode, "reason": "Código de barras duplicado dentro del archivo."})
            dueno_actual = productos_existentes_por_barcode.get(barcode)
            if dueno_actual and dueno_actual.sku != sku:
                errores.append({"row": n, "column": "Código de barras", "value": barcode, "reason": f"Ya lo usa el producto con SKU «{dueno_actual.sku}»."})

        categoria_texto = v.get("category", "").strip()
        categoria = None
        if categoria_texto:
            categoria = categorias_por_nombre.get(categoria_texto.lower())
            if categoria is None:
                errores.append({"row": n, "column": "Categoría", "value": categoria_texto, "reason": "No existe ninguna categoría con ese nombre."})

        descripcion = _validar_texto_simple(v.get("description", ""), campo="Descripción", fila=n, errores=errores, max_length=100_000, requerido=False)
        marca = _validar_texto_simple(v.get("brand", ""), campo="Marca", fila=n, errores=errores, max_length=100, requerido=False)
        modelo = _validar_texto_simple(v.get("model_name", ""), campo="Modelo", fila=n, errores=errores, max_length=100, requerido=False)

        tracking_texto = v.get("inventory_tracking_type", "").strip()
        tracking = None
        if tracking_texto or accion == "CREATE":
            tracking = _parsear_tracking(tracking_texto, fila=n, errores=errores)
            if tracking and producto_existente and producto_existente.inventory_tracking_type != tracking:
                if services.product_has_inventory_history(producto_existente):
                    errores.append({
                        "row": n, "column": "Tipo de seguimiento", "value": tracking_texto,
                        "reason": f"«{sku}» ya tiene movimientos/unidades registradas — no se puede cambiar su tipo de seguimiento.",
                    })

        precio_venta = _parsear_decimal(v.get("sale_price", ""), campo="Precio de venta", fila=n, errores=errores, permitir_vacio=(accion == "UPDATE"), default=None)
        if accion == "CREATE" and v.get("sale_price", "").strip() == "":
            errores.append({"row": n, "column": "Precio de venta", "value": "", "reason": "Es obligatorio."})
        precio_compra = _parsear_decimal(v.get("purchase_price", ""), campo="Precio de compra", fila=n, errores=errores)
        impuesto = _parsear_decimal(v.get("tax_rate", ""), campo="Impuesto (%)", fila=n, errores=errores)
        stock_minimo = _parsear_decimal(v.get("min_stock", ""), campo="Stock mínimo", fila=n, errores=errores)
        activo = _parsear_booleano(v.get("is_active", ""), campo="Activo", fila=n, errores=errores)
        atributos = _parsear_variant_attributes(v.get("variant_attributes", ""), fila=n, errores=errores)

        if len(errores) > errores_antes:
            continue  # esta fila tiene errores — no se agrega al preview aplicable

        campos = {}
        if accion == "CREATE":
            campos = {
                # `category_id` (int|None), nunca `category` (instancia
                # de modelo): `preview_data` es un JSONField, tiene que
                # ser serializable — mismo campo que usa la rama UPDATE
                # más abajo.
                "name": nombre, "barcode": barcode or "", "category_id": categoria.pk if categoria else None,
                "description": descripcion or "", "brand": marca or "", "model_name": modelo or "",
                "inventory_tracking_type": str(tracking or Product.TrackingType.QUANTITY),
                "sale_price": str(precio_venta), "purchase_price": str(precio_compra),
                "tax_rate": str(impuesto), "min_stock": str(stock_minimo),
                "is_active": activo, "variant_attributes": atributos,
            }
        else:
            if v.get("name", "").strip():
                campos["name"] = nombre
            if barcode_texto:
                campos["barcode"] = barcode
            if categoria_texto:
                campos["category_id"] = categoria.pk
            if v.get("description", "").strip():
                campos["description"] = descripcion
            if v.get("brand", "").strip():
                campos["brand"] = marca
            if v.get("model_name", "").strip():
                campos["model_name"] = modelo
            if tracking_texto:
                campos["inventory_tracking_type"] = str(tracking)
            if v.get("sale_price", "").strip():
                campos["sale_price"] = str(precio_venta)
            if v.get("purchase_price", "").strip():
                campos["purchase_price"] = str(precio_compra)
            if v.get("tax_rate", "").strip():
                campos["tax_rate"] = str(impuesto)
            if v.get("min_stock", "").strip():
                campos["min_stock"] = str(stock_minimo)
            if v.get("is_active", "").strip():
                campos["is_active"] = activo
            if v.get("variant_attributes", "").strip():
                campos["variant_attributes"] = atributos
            if not campos:
                advertencias.append({"row": n, "column": "", "value": sku, "reason": "Sin cambios respecto al producto actual."})

        preview_rows.append({
            "row": n, "action": accion, "sku": sku,
            "product_pk": producto_existente.pk if producto_existente else None,
            "fields": campos,
        })

    creados = sum(1 for f in preview_rows if f["action"] == "CREATE")
    actualizados = sum(1 for f in preview_rows if f["action"] == "UPDATE")

    batch = ProductImportBatch.all_objects.create(
        tenant=tenant, uploaded_by=user, original_filename=nombre_original_seguro(archivo.name),
        total_rows=len(filas_validas), created_count=creados, updated_count=actualizados,
        error_count=len(errores), warning_count=len(advertencias),
        preview_data=preview_rows, errors_data=errores, warnings_data=advertencias,
    )
    return batch


# ------------------------------------------------------------------
# Confirmación (aplicar el lote)
# ------------------------------------------------------------------


@transaction.atomic
def apply_import_batch(batch_pk, *, tenant, user):
    """Aplica un lote ya validado. Todo o nada (modo estricto: nunca
    productos parcialmente importados):
    - Bloquea la FILA DEL LOTE (`select_for_update`) para que dos
      confirmaciones del mismo lote (doble clic, dos pestañas) nunca lo
      apliquen dos veces.
    - Bloquea cada `Product` existente (`select_for_update`, en orden
      determinístico por SKU — evita interbloqueos entre dos lotes
      concurrentes que compartan SKUs) antes de actualizarlo.
    - Un `CREATE` que choca con una fila creada por OTRA transacción
      concurrente entre el preview y la confirmación (mismo SKU/barcode)
      queda protegido por los `UniqueConstraint` ya existentes de
      `Product` — se captura como conflicto real (`IntegrityError`) vía
      un SAVEPOINT interno: el lote completo se revierte y queda
      `FAILED`, nunca parcialmente aplicado."""
    lote = ProductImportBatch.all_objects.select_for_update().get(pk=batch_pk, tenant=tenant)
    if lote.status != ProductImportBatch.Status.PENDING_REVIEW:
        raise InvalidImportOperation("Este lote ya fue procesado — no se puede confirmar de nuevo.")
    if lote.error_count > 0:
        raise InvalidImportOperation("El lote tiene errores — corrígelos y sube el archivo de nuevo.")

    creados = 0
    actualizados = 0
    try:
        with transaction.atomic():
            for fila in sorted(lote.preview_data, key=lambda f: f["sku"]):
                campos = dict(fila["fields"])
                if fila["action"] == "CREATE":
                    campos["variant_attributes"] = campos.get("variant_attributes") or {}
                    for clave_decimal in ("sale_price", "purchase_price", "tax_rate", "min_stock"):
                        if clave_decimal in campos:
                            campos[clave_decimal] = Decimal(campos[clave_decimal])
                    Product.all_objects.create(tenant=lote.tenant, sku=fila["sku"], **campos)
                    creados += 1
                else:
                    producto = Product.all_objects.select_for_update().get(pk=fila["product_pk"], tenant=lote.tenant)
                    for clave, valor in campos.items():
                        if clave in ("sale_price", "purchase_price", "tax_rate", "min_stock"):
                            valor = Decimal(valor)
                        if clave == "category_id":
                            producto.category_id = valor
                        else:
                            setattr(producto, clave, valor)
                    producto.save()
                    actualizados += 1
    except IntegrityError as error:
        lote.status = ProductImportBatch.Status.FAILED
        lote.failure_reason = (
            "Conflicto de datos al confirmar (otro proceso modificó el mismo SKU/código de barras "
            "entre la vista previa y la confirmación). Vuelve a subir el archivo — el catálogo no cambió."
        )
        lote.save(update_fields=["status", "failure_reason"])
        raise InvalidImportOperation(lote.failure_reason) from error

    lote.status = ProductImportBatch.Status.CONFIRMED
    lote.created_count = creados
    lote.updated_count = actualizados
    lote.confirmed_at = timezone.now()
    lote.save(update_fields=["status", "created_count", "updated_count", "confirmed_at"])
    return lote
