"""
Modelos de Clientes y Proveedores (FASE 9).

`Customer` y `Supplier` heredan `TenantScopedModel` (FASE 3): aislamiento
automático por tenant (`objects` tenant-aware, `all_objects` como vía de
escape consciente, igual que `apps.inventory`). Comparten la mayoría de
sus campos a través del mixin abstracto `ContactoMixin`, pero son
modelos independientes entre sí — no hay ninguna relación ni tabla
compartida entre ambos.

## Identificación fiscal extensible
`identification_type` es un `CharField` con `choices` (no una tabla
aparte): agregar un nuevo tipo de identificación en el futuro (p. ej. un
país nuevo) es agregar una línea a `IdentificationType`, nunca una
migración que reestructure la tabla. `identification_number` es el valor
libre asociado. Un `CheckConstraint` exige que, si hay número, también
haya tipo (para no guardar un número "huérfano" sin saber qué es).

## Datos comerciales: preparados, sin motor financiero
`payment_terms`, `credit_days`, `credit_enabled`, `currency` (ambos
modelos) y `credit_limit`/`commercial_notes` (solo `Customer`) son
campos de CONFIGURACIÓN reales — el usuario ya puede definir, hoy, que
"este cliente tiene crédito de 30 días, límite $5000, en USD". Lo que
deliberadamente NO existe todavía es el motor financiero que los
consume: no hay `balance`, ni `AccountsReceivable`/`AccountsPayable`, ni
ningún movimiento/ledger — esos requieren transacciones reales
(ventas/compras/pagos) que no existen hasta FASE 10/12/17. Cuando esas
fases lleguen, lo natural es un modelo relacionado nuevo (p. ej.
`CustomerAccount`/`SupplierAccount`, con su propio ledger append-only,
mismo patrón que `StockMovement`/`InventoryUnit` en FASE 8) vinculado
por FK a `Customer`/`Supplier` — nunca un campo `balance` desnormalizado
aquí. Ver "Preparación arquitectónica" en `docs/customers.md` y
`docs/suppliers.md`.

## Documentos adjuntos
`CustomerDocument`/`SupplierDocument` (más abajo) son las unidades de
archivo adjunto por cliente/proveedor — ver `docs/customer-documents.md`
y `docs/supplier-documents.md` para el diseño de seguridad completo
(validación de extensión/firma binaria/tamaño, nombres de archivo
seguros, descarga protegida).

## Auditoría
`ActivityLog` es una bitácora MÍNIMA, acotada a este módulo (creación,
edición, desactivación, reactivación, subida/eliminación/descarga de
documentos) — NO es el sistema de auditoría transversal que construirá
FASE 15 (Roles + Audit), que más adelante podrá generalizar o sustituir
este modelo por uno de alcance global para todo el proyecto.

## Historial de ventas/compras
El "historial" (ventas para Cliente, compras para Proveedor) pedido en
el objetivo de esta fase todavía no existe como dato real: se muestra
como estado vacío honesto en el detalle de cada cliente/proveedor hasta
que existan `Sale`/`SaleItem` (FASE 10) y `Purchase`/`PurchaseItem`
(FASE 12) — mismo principio que los KPIs "Ventas del mes"/"Gastos del
mes" del Panel (FASE 7): nunca se inventa un dato que todavía no existe.
"""

import os
import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.tenants.models import TenantScopedModel

# Extensiones permitidas para documentos adjuntos (ver también
# `file_validation.py`, que además verifica la firma binaria real del
# archivo, no solo la extensión declarada).
EXTENSIONES_DOCUMENTO_PERMITIDAS = ["pdf", "jpg", "jpeg", "png", "doc", "docx", "xls", "xlsx"]


class PartyType(models.TextChoices):
    PERSONA = "persona", "Persona"
    EMPRESA = "empresa", "Empresa"


class IdentificationType(models.TextChoices):
    """Extensible sin rehacer el modelo: agregar un tipo nuevo es
    agregar una línea aquí, no una migración estructural."""

    CEDULA = "cedula", "Cédula"
    RNC = "rnc", "RNC"
    PASAPORTE = "pasaporte", "Pasaporte"
    TAX_ID = "tax_id", "Tax ID"
    OTRO = "otro", "Otro"


class PaymentTerms(models.TextChoices):
    CONTADO = "contado", "Contado"
    NET_15 = "net_15", "15 días"
    NET_30 = "net_30", "30 días"
    NET_60 = "net_60", "60 días"
    OTRO = "otro", "Otro"


class DocumentCategory(models.TextChoices):
    """Extensible: agregar una categoría nueva es agregar una línea
    aquí, sin tocar `CustomerDocument`/`SupplierDocument`."""

    IDENTIFICACION = "identificacion", "Identificación"
    DOCUMENTO_FISCAL = "documento_fiscal", "Documento fiscal"
    CONTRATO = "contrato", "Contrato"
    CERTIFICADO = "certificado", "Certificado"
    COMPROBANTE = "comprobante", "Comprobante"
    DOCUMENTO_BANCARIO = "documento_bancario", "Documento bancario"
    OTRO = "otro", "Otro"


class ContactoMixin(models.Model):
    """Campos comunes a `Customer` y `Supplier`. Abstracto: no crea tabla
    propia — cada modelo concreto declara sus propias constraints, porque
    la unicidad de `identification_number`/`email` es POR modelo (un
    mismo documento puede corresponder a un cliente y, por separado, a un
    proveedor distinto; son universos distintos)."""

    party_type = models.CharField(
        "tipo", max_length=20, choices=PartyType.choices, default=PartyType.PERSONA
    )
    trade_name = models.CharField("nombre comercial", max_length=200, blank=True)
    identification_type = models.CharField(
        "tipo de identificación", max_length=20, choices=IdentificationType.choices, blank=True
    )
    identification_number = models.CharField(
        "número de identificación",
        max_length=50,
        blank=True,
        help_text="Cédula, RNC, pasaporte, Tax ID u otro, según el tipo seleccionado.",
    )
    email = models.EmailField("correo electrónico", blank=True)
    phone = models.CharField("teléfono", max_length=30, blank=True)
    address = models.CharField("dirección", max_length=255, blank=True)
    city = models.CharField("ciudad", max_length=100, blank=True)
    state_province = models.CharField("provincia / estado", max_length=100, blank=True)
    country = models.CharField("país", max_length=100, blank=True)
    notes = models.TextField("notas", blank=True)

    # --- Datos comerciales: preparados, sin motor financiero (ver arriba) ---
    payment_terms = models.CharField(
        "condiciones de pago", max_length=20, choices=PaymentTerms.choices, default=PaymentTerms.CONTADO
    )
    credit_days = models.PositiveSmallIntegerField("días de crédito", default=0)
    credit_enabled = models.BooleanField("crédito habilitado", default=False)
    currency = models.CharField("moneda", max_length=3, default="USD")

    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        abstract = True


class Customer(TenantScopedModel, ContactoMixin):
    """Cliente de la empresa (tenant). CRUD completo, aislado por tenant."""

    first_name = models.CharField("nombre", max_length=150, blank=True)
    last_name = models.CharField("apellido", max_length=150, blank=True)
    company_name = models.CharField("empresa", max_length=200, blank=True)
    secondary_phone = models.CharField("teléfono secundario", max_length=30, blank=True)
    alternate_email = models.EmailField("correo alternativo", blank=True)
    postal_code = models.CharField("código postal", max_length=20, blank=True)
    credit_limit = models.DecimalField("límite de crédito", max_digits=12, decimal_places=2, default=0)
    commercial_notes = models.TextField("notas comerciales", blank=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["first_name", "last_name", "company_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "identification_number"],
                condition=models.Q(identification_number__gt=""),
                name="unique_customer_tenant_identificacion_no_vacia",
            ),
            models.UniqueConstraint(
                fields=["tenant", "email"],
                condition=models.Q(email__gt=""),
                name="unique_customer_tenant_email_no_vacio",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(first_name="")
                    | ~models.Q(last_name="")
                    | ~models.Q(company_name="")
                    | ~models.Q(trade_name="")
                ),
                name="customer_al_menos_un_nombre",
            ),
            models.CheckConstraint(
                check=models.Q(identification_number="") | ~models.Q(identification_type=""),
                name="customer_tipo_identificacion_si_hay_numero",
            ),
            models.CheckConstraint(check=models.Q(credit_limit__gte=0), name="customer_credit_limit_no_negativo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active", "first_name"], name="idx_customer_tenant_activo"),
        ]

    @property
    def display_name(self):
        nombre_persona = " ".join(parte for parte in [self.first_name, self.last_name] if parte)
        if self.company_name and nombre_persona:
            return f"{self.company_name} ({nombre_persona})"
        return self.company_name or nombre_persona or self.trade_name or f"#{self.pk}"

    def __str__(self):
        return self.display_name


class Supplier(TenantScopedModel, ContactoMixin):
    """Proveedor de la empresa (tenant). CRUD completo, aislado por tenant.

    Deliberadamente sin `first_name`/`last_name` separados (ver spec de
    la fase): un proveedor se identifica por `legal_name` (razón social,
    que para un proveedor persona física es simplemente su nombre
    completo) y, opcionalmente, `trade_name` (nombre comercial).
    """

    legal_name = models.CharField("razón social", max_length=200, blank=True)

    class Meta:
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        ordering = ["legal_name", "trade_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "identification_number"],
                condition=models.Q(identification_number__gt=""),
                name="unique_supplier_tenant_identificacion_no_vacia",
            ),
            models.UniqueConstraint(
                fields=["tenant", "email"],
                condition=models.Q(email__gt=""),
                name="unique_supplier_tenant_email_no_vacio",
            ),
            models.CheckConstraint(
                check=~models.Q(legal_name="") | ~models.Q(trade_name=""),
                name="supplier_al_menos_un_nombre",
            ),
            models.CheckConstraint(
                check=models.Q(identification_number="") | ~models.Q(identification_type=""),
                name="supplier_tipo_identificacion_si_hay_numero",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active", "legal_name"], name="idx_supplier_tenant_activo"),
        ]

    @property
    def display_name(self):
        return self.legal_name or self.trade_name or f"#{self.pk}"

    def __str__(self):
        return self.display_name


# ---------------------------------------------------------------------
# Documentos adjuntos
# ---------------------------------------------------------------------


def _ruta_documento_cliente(instance, filename):
    """Nunca usa el nombre original del archivo como ruta en disco (ver
    `docs/customer-documents.md` — defensa contra path traversal /
    colisiones): genera un nombre aleatorio, organizado por tenant y
    cliente."""
    extension = os.path.splitext(filename)[1].lower()
    return f"clientes/{instance.tenant_id}/{instance.customer_id}/{uuid.uuid4().hex}{extension}"


def _ruta_documento_proveedor(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"proveedores/{instance.tenant_id}/{instance.supplier_id}/{uuid.uuid4().hex}{extension}"


class DocumentoBaseMixin(models.Model):
    """Campos comunes a `CustomerDocument`/`SupplierDocument`. La
    validación real de contenido (extensión + firma binaria + tamaño)
    vive en `file_validation.py` y se aplica en `forms.py`/`services.py`
    ANTES de guardar — este modelo asume que, si llegó hasta aquí, ya
    fue validado."""

    category = models.CharField(
        "categoría", max_length=30, choices=DocumentCategory.choices, default=DocumentCategory.OTRO
    )
    original_filename = models.CharField(
        "nombre original",
        max_length=255,
        help_text="Nombre del archivo tal como se mostrará en la interfaz (saneado). "
        "El archivo se guarda en disco con un nombre generado, nunca con este valor.",
    )
    content_type = models.CharField("tipo de contenido detectado", max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField("tamaño (bytes)")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="subido por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    uploaded_at = models.DateTimeField("subido", auto_now_add=True)
    notes = models.CharField("notas", max_length=255, blank=True)

    class Meta:
        abstract = True


class CustomerDocument(TenantScopedModel, DocumentoBaseMixin):
    customer = models.ForeignKey(
        Customer, verbose_name="cliente", related_name="documents", on_delete=models.PROTECT
    )
    file = models.FileField(
        "archivo",
        upload_to=_ruta_documento_cliente,
        validators=[FileExtensionValidator(allowed_extensions=EXTENSIONES_DOCUMENTO_PERMITIDAS)],
    )

    class Meta:
        verbose_name = "documento de cliente"
        verbose_name_plural = "documentos de clientes"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["tenant", "customer", "uploaded_at"], name="idx_custdoc_tenant_cliente"),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.customer})"


class SupplierDocument(TenantScopedModel, DocumentoBaseMixin):
    supplier = models.ForeignKey(
        Supplier, verbose_name="proveedor", related_name="documents", on_delete=models.PROTECT
    )
    file = models.FileField(
        "archivo",
        upload_to=_ruta_documento_proveedor,
        validators=[FileExtensionValidator(allowed_extensions=EXTENSIONES_DOCUMENTO_PERMITIDAS)],
    )

    class Meta:
        verbose_name = "documento de proveedor"
        verbose_name_plural = "documentos de proveedores"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["tenant", "supplier", "uploaded_at"], name="idx_supdoc_tenant_proveedor"),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.supplier})"


def _log_documentos():
    import logging

    return logging.getLogger("apps.customers.documents")


@receiver(post_delete, sender=CustomerDocument)
@receiver(post_delete, sender=SupplierDocument)
def _eliminar_archivo_al_borrar_documento(sender, instance, **kwargs):
    """Borra el archivo físico de `media-private/` cuando se elimina la
    fila del documento — sea cual sea el camino de borrado (la vista de
    eliminación, el admin, un `queryset.delete()` masivo, o un cascade
    futuro). Django envía `post_delete` para cada instancia individual en
    todos esos casos en cuanto hay algún receptor conectado a esta señal
    (desactiva la optimización de "fast delete" del ORM), así que esto
    cierra por diseño el riesgo de "archivos huérfanos" en disco sin
    depender de que cada código de borrado recuerde limpiar el archivo
    a mano.

    Si el borrado físico falla (p. ej. el archivo está momentáneamente
    bloqueado por otro proceso — típico en Windows si acaba de
    descargarse en la misma request/proceso), se registra el error pero
    NUNCA se propaga: la fila ya se borró de PostgreSQL (la fuente de
    verdad) y no tiene sentido convertir un problema de limpieza de
    disco en un 500 para el usuario. El archivo huérfano que pudiera
    quedar es recuperable con una tarea de limpieza manual/futura; no
    perder la operación de borrado en sí es la prioridad."""
    if instance.file:
        try:
            instance.file.delete(save=False)
        except OSError:
            _log_documentos().exception(
                "No se pudo borrar el archivo físico del documento eliminado: %s", instance.file.name
            )


# ---------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo — ver docstring del módulo)
# ---------------------------------------------------------------------


class ActivityLog(TenantScopedModel):
    """Bitácora mínima de Clientes y Proveedores. NO es el sistema de
    auditoría transversal de FASE 15 — ver docstring del módulo."""

    class Action(models.TextChoices):
        CREATED = "created", "Creación"
        UPDATED = "updated", "Edición"
        DEACTIVATED = "deactivated", "Desactivación"
        REACTIVATED = "reactivated", "Reactivación"
        DOCUMENT_UPLOADED = "document_uploaded", "Documento subido"
        DOCUMENT_DELETED = "document_deleted", "Documento eliminado"
        DOCUMENT_DOWNLOADED = "document_downloaded", "Documento descargado"

    entity_type = models.CharField("tipo de entidad", max_length=20)  # "customer" | "supplier"
    entity_id = models.PositiveBigIntegerField("id de la entidad")
    entity_label = models.CharField(
        "nombre de la entidad (al momento del evento)", max_length=255, blank=True
    )
    action = models.CharField("acción", max_length=30, choices=Action.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    details = models.CharField("detalles", max_length=255, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "registro de actividad (clientes/proveedores)"
        verbose_name_plural = "registros de actividad (clientes/proveedores)"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["tenant", "entity_type", "entity_id", "created_at"],
                name="idx_activitylog_tenant_entidad",
            ),
        ]

    def __str__(self):
        return f"{self.get_action_display()} · {self.entity_type} #{self.entity_id}"
