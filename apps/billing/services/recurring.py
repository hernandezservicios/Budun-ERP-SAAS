"""
Cobro recurrente automático de PayPal (FASE DE CORRECCIÓN 2C, Gate
Local — ver `docs/billing.md` sección "Billing recurrente con PayPal",
`docs/paypal.md`, `KNOWN_ISSUES.md`/`DECISIONS.md`).

Arquitectura elegida — PayPal Subscriptions API (Catalog Products +
Billing Plans + Subscriptions), NUNCA PayPal Reference Transactions/
Vault: Reference Transactions exige aprobación especial de PayPal para
cuentas LIVE (contactar al gestor de cuenta; "Merchant not enabled for
reference transaction" es el error real si no se tiene), mientras que
Subscriptions es una API REST estándar sin aprobación adicional, igual
en Sandbox y en Live — la decisión correcta para no quedar bloqueados
por un proceso de aprobación externo fuera de nuestro control. Ver
`DECISIONS.md` para el detalle completo con las fuentes oficiales
consultadas.

Mapeo Budun <-> PayPal, siempre 1:1 y CENTRALIZADO (nunca un producto/
plan de PayPal por tenant):
- `PlanVersion` (Budun) <-> Producto + Billing Plan (PayPal), vía
  `PlanVersion.paypal_product_id`/`paypal_plan_id` — se crean una única
  vez, la primera vez que algún tenant contrata esa versión con cobro
  recurrente (`ensure_paypal_billing_plan`).
- `Subscription` (Budun) <-> Subscription (PayPal), vía
  `Subscription.paypal_subscription_id` — una por tenant, creada al
  autorizar el cobro recurrente (`create_recurring_checkout`).

Budun sigue siendo la ÚNICA fuente de verdad de negocio (Plan/
Subscription/SaaSInvoice/SaaSPayment/Allocation/billing_status) — PayPal
solo autoriza/ejecuta el cobro y reporta su propio estado externo
(`Subscription.paypal_subscription_status`, informativo, nunca usado
para decidir nada por sí solo).

Reintentos: PayPal reintenta un cobro recurrente fallido por su cuenta
(`payment_preferences.payment_failure_threshold` configurado en el
Billing Plan, ver `create_billing_plan`) — Budun NO implementa un
scheduler de reintentos propio para el método PayPal; solo reacciona a
los webhooks de éxito/fallo que PayPal ya emite. Para transferencia
(sin autorización de cobro posible), el mecanismo de gracia/suspensión
por calendario ya existente (`BillingPolicy`,
`apply_billing_past_due_policy`) sigue siendo el único disponible, sin
cambios.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog

from ..models import PlanVersion, SaaSInvoice, SaaSPayment, Subscription
from ..providers import PaymentProviderError
from ._saas_audit import audit_event
from . import invoicing as invoicing_services
from . import payments as payment_services
from . import subscriptions as subscription_services

# NUNCA `from ..providers import get_default_provider` aquí: eso crearía
# un nombre propio en el espacio de este módulo, invisible para
# `unittest.mock.patch("apps.billing.services.get_default_provider")`
# (el mismo mecanismo que ya usan todos los tests de `apps.billing` vía
# `fake_provider()`) — un error real encontrado durante esta misma
# corrección (un test sin querer llegó a hacer una llamada de red real
# a PayPal Sandbox antes de detectarlo). En su lugar, cada llamada
# accede al atributo del PAQUETE en el momento de usarlo, para que un
# parche aplicado sobre `apps.billing.services` (el `__init__.py`, el
# único lugar donde `get_default_provider` vive de verdad) sea visto
# también desde aquí.
from .. import services as _billing_services

# Política de reintentos de PayPal para el Billing Plan (sección 16 de
# la corrección): PROPUESTA documentada, no una política comercial ya
# decidida por el negocio — 2 reintentos antes de que PayPal reporte el
# fallo como definitivo (mismo valor de ejemplo que la documentación
# oficial de PayPal usa), configurable aquí en un único lugar si el
# negocio decide otro valor.
PAYPAL_PAYMENT_FAILURE_THRESHOLD = 2


class InvalidRecurringOperation(ValidationError):
    pass


def is_paypal_recurring_available():
    """Mismo interruptor de plataforma que el checkout de pago único
    (`apps.billing.services.is_paypal_available`) — un solo lugar
    decide si PayPal (en cualquiera de sus dos modalidades) está
    disponible; el cobro recurrente nunca tiene su propio interruptor
    aparte."""
    from . import is_paypal_available

    return is_paypal_available()


def ensure_paypal_billing_plan(plan_version, *, user=None):
    """Idempotente: si `plan_version` YA tiene un Producto+Plan de
    PayPal (creados por una contratación anterior de CUALQUIER tenant),
    los reutiliza tal cual — nunca crea un segundo Producto/Plan para la
    misma versión. Si no, los crea ahora, una única vez, y los guarda en
    la propia `PlanVersion` (inmutable desde entonces, igual que el
    precio que representa)."""
    if plan_version.paypal_plan_id:
        return plan_version

    provider = _billing_services.get_default_provider()
    with transaction.atomic():
        plan_version = PlanVersion.objects.select_for_update().get(pk=plan_version.pk)
        if plan_version.paypal_plan_id:  # otro hilo/proceso ganó la carrera mientras esperábamos el lock.
            return plan_version

        if not plan_version.paypal_product_id:
            try:
                producto = provider.create_product(
                    name=f"Budun ERP — {plan_version.plan.name}",
                    description=f"Plan {plan_version.plan.name} ({plan_version.get_frequency_display()})",
                    idempotency_key=f"budun-paypal-product-{plan_version.pk}",
                )
            except PaymentProviderError as error:
                raise InvalidRecurringOperation(f"No se pudo crear el producto en PayPal: {error}") from error
            plan_version.paypal_product_id = producto.external_product_id
            plan_version.save(update_fields=["paypal_product_id"])

        try:
            plan = provider.create_billing_plan(
                product_id=plan_version.paypal_product_id,
                name=f"{plan_version.plan.name} — {plan_version.get_frequency_display()}",
                amount=plan_version.price_amount, currency=plan_version.price_currency,
                frequency=plan_version.frequency, payment_failure_threshold=PAYPAL_PAYMENT_FAILURE_THRESHOLD,
                idempotency_key=f"budun-paypal-plan-{plan_version.pk}",
            )
        except PaymentProviderError as error:
            raise InvalidRecurringOperation(f"No se pudo crear el plan de facturación en PayPal: {error}") from error
        plan_version.paypal_plan_id = plan.external_plan_id
        plan_version.save(update_fields=["paypal_plan_id"])
        audit_event(
            None, action=AuditLog.Action.GENERIC, user=user, object_type="plan_version", object_id=plan_version.pk,
            after={"paypal_product_id": plan_version.paypal_product_id, "paypal_plan_id": plan_version.paypal_plan_id},
        )
    return plan_version


def create_recurring_checkout(subscription, *, user, return_url, cancel_url):
    """Autoriza el cobro recurrente de PayPal para `subscription` —
    equivalente recurrente de `apps.billing.services.
    create_checkout_for_invoice`, pero autoriza cobros FUTUROS en vez de
    cobrar una factura puntual. El primer cobro real solo se confirma al
    volver del checkout (`reconcile_recurring_subscription`) o, más
    tarde, por webhook (`PAYMENT.SALE.COMPLETED`) — nunca se activa la
    suscripción solo porque el navegador volvió con éxito aparente."""
    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        if subscription.paypal_subscription_id and subscription.paypal_subscription_status not in (
            "CANCELLED", "EXPIRED", "",
        ):
            raise InvalidRecurringOperation(
                "Esta suscripción ya tiene una autorización de cobro recurrente de PayPal activa o pendiente."
            )

        plan_version = ensure_paypal_billing_plan(subscription.plan_version, user=user)
        provider = _billing_services.get_default_provider()
        try:
            creada = provider.create_recurring_subscription(
                plan_id=plan_version.paypal_plan_id, reference_id=str(subscription.pk),
                return_url=return_url, cancel_url=cancel_url,
                idempotency_key=f"budun-paypal-subscription-{subscription.pk}",
            )
        except PaymentProviderError as error:
            raise InvalidRecurringOperation(f"No se pudo crear la suscripción en PayPal: {error}") from error

        subscription.paypal_subscription_id = creada.external_subscription_id
        subscription.paypal_subscription_status = creada.status
        subscription.save(update_fields=["paypal_subscription_id", "paypal_subscription_status", "updated_at"])
        audit_event(
            subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="subscription", object_id=subscription.pk,
            after={"paypal_subscription_id": creada.external_subscription_id, "status": creada.status},
        )
    return subscription, creada.approve_url


def confirm_recurring_charge(subscription, *, amount, currency, external_reference, user=None):
    """Aplica un cobro recurrente de PayPal ya confirmado — reutilizada
    tanto por la reconciliación SÍNCRONA al volver del checkout inicial
    (`reconcile_recurring_subscription`) como por el webhook
    `PAYMENT.SALE.COMPLETED` de cada renovación posterior: mismo
    principio ya documentado en el SaaS Platform Knowledge Kit
    ("Invoice -> Payment -> Allocation... convergen en el MISMO par de
    funciones"). Nunca cobra una factura inexistente: si no hay ninguna
    factura `OPEN`/`PARTIALLY_PAID` para la suscripción todavía (el cron
    de renovación no alcanzó a correr antes de que llegara el webhook),
    la genera ella misma (`ensure_next_renewal_invoice`) — el sistema
    nunca depende de que el scheduler corra primero."""
    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        invoice = SaaSInvoice.all_objects.filter(
            subscription=subscription, status__in=[SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID],
        ).order_by("due_date", "id").first()

        if invoice is None and subscription.status in (Subscription.Status.CANCELLED, Subscription.Status.EXPIRED):
            # Cobro tardío/fuera de orden sobre una suscripción que el
            # tenant YA canceló (sección 9/10: "impedir nuevos cobros" —
            # nunca se genera una factura nueva para un período que no
            # debería facturarse). El dinero ya fue cobrado por PayPal
            # de todas formas: se registra como pago SIN aplicar (nunca
            # se pierde, mismo criterio que un sobrepago) y se audita
            # como anomalía para que un humano decida (típicamente,
            # reembolsar).
            pago = payment_services.record_payment(
                tenant=subscription.tenant, saas_customer=subscription.saas_customer, subscription=subscription,
                method=SaaSPayment.Method.PAYPAL, amount=amount, currency=currency,
                external_reference=external_reference, user=user, status=SaaSPayment.Status.CONFIRMED,
            )
            pago.received_at = timezone.now()
            pago.save(update_fields=["received_at"])
            audit_event(
                subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_payment", object_id=pago.pk,
                reason="Cobro recurrente de PayPal recibido para una suscripción ya cancelada/expirada — revisar reembolso",
                metadata={"monto": f"{amount} {currency}"},
            )
            return pago

        if invoice is None:
            if subscription.current_period_end is None:
                # Nunca debería pasar (la autorización inicial ya generó
                # la primera factura con un período fijado) — defensivo.
                raise InvalidRecurringOperation(
                    "No hay ninguna factura pendiente ni período vigente para aplicar este cobro recurrente."
                )
            invoice, _creada = invoicing_services.ensure_next_renewal_invoice(subscription)

        pago = payment_services.record_payment(
            tenant=subscription.tenant, saas_customer=subscription.saas_customer, subscription=subscription,
            method=SaaSPayment.Method.PAYPAL, amount=amount, currency=currency,
            external_reference=external_reference, user=user, status=SaaSPayment.Status.CONFIRMED,
        )
        pago.received_at = timezone.now()
        pago.save(update_fields=["received_at"])
        payment_services.auto_apply_payment(pago, user=user)

        if amount != invoice.total or currency != invoice.currency:
            # El dinero YA se cobró — nunca se rechaza retroactivamente
            # (mismo criterio que el resto de Billing SaaS: el ledger
            # siempre refleja lo realmente cobrado). Por diseño esto no
            # debería ocurrir nunca (el Billing Plan de PayPal congela el
            # precio de `plan_version` en el momento de crearse), así que
            # se audita como anomalía para revisión humana.
            audit_event(
                subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_invoice", object_id=invoice.pk,
                reason="Monto/moneda del cobro recurrente no coincide con la factura",
                metadata={"cobrado": f"{amount} {currency}", "factura": f"{invoice.total} {invoice.currency}"},
            )

        estado_previo = subscription.status

    # FASE DE CORRECCIÓN 3 (Lifecycle integral): `ACTIVATE != REACTIVATE`
    # — fuera del `with transaction.atomic()` de arriba (mismo estilo que
    # `subscriptions.activate_pending_subscription`), porque
    # `reactivate_subscription` abre su propia transacción/lock. Antes de
    # esta corrección, un cobro recurrente confirmado sobre una
    # suscripción PAST_DUE/SUSPENDED llamaba siempre al primitivo de
    # activación INICIAL, sin restaurar el período si ya había vencido.
    if estado_previo == Subscription.Status.PENDING:
        subscription_services.activate_subscription(subscription, user=user)
    elif estado_previo in (Subscription.Status.PAST_DUE, Subscription.Status.SUSPENDED):
        subscription_services.reactivate_subscription(subscription, user=user)
    return pago


def reconcile_recurring_subscription(subscription, *, user=None):
    """Reconciliación SÍNCRONA al volver del checkout de autorización
    (`return_url`) — nunca depende del webhook para la autorización
    INICIAL, porque en Gate Local (localhost) un webhook real de PayPal
    Sandbox no puede entregarse a `127.0.0.1` (mismo criterio ya
    documentado para el checkout de pago único en `docs/paypal.md`).
    Las renovaciones POSTERIORES (sin ningún retorno del navegador,
    PayPal cobra en segundo plano) SÍ dependen exclusivamente del
    webhook — no hay ninguna otra forma de enterarse."""
    provider = _billing_services.get_default_provider()
    try:
        estado = provider.get_recurring_subscription(external_subscription_id=subscription.paypal_subscription_id)
    except PaymentProviderError as error:
        raise InvalidRecurringOperation(f"No se pudo consultar la suscripción en PayPal: {error}") from error

    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        subscription.paypal_subscription_status = estado.status
        subscription.save(update_fields=["paypal_subscription_status", "updated_at"])

    if estado.status == "ACTIVE":
        invoice = SaaSInvoice.all_objects.filter(
            subscription=subscription, status__in=[SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID],
        ).order_by("due_date", "id").first()
        if invoice is not None:
            confirm_recurring_charge(
                subscription, amount=invoice.total, currency=invoice.currency,
                external_reference=subscription.paypal_subscription_id, user=user,
            )
    return subscription


def cancel_recurring_subscription(subscription, *, immediate=False, reason="", user=None):
    """Cancela AMBOS lados de forma coordinada (sección 10): primero
    PayPal (impide cualquier cobro futuro), luego Budun
    (`subscription_services.cancel_subscription`, sin cambios — conserva
    intacto todo el historial de facturas/pagos, nunca los borra). Si
    PayPal ya no tiene nada que cancelar (`should_fail_cancel_recurring_
    subscription` simulado, o la suscripción de PayPal ya estaba
    cancelada/expirada), el lado de Budun se cancela igual — un tenant
    nunca debe quedar atrapado por un error transitorio del proveedor
    externo al querer cancelar su propia cuenta."""
    if subscription.paypal_subscription_id and subscription.paypal_subscription_status not in ("CANCELLED", "EXPIRED", ""):
        provider = _billing_services.get_default_provider()
        try:
            provider.cancel_recurring_subscription(
                external_subscription_id=subscription.paypal_subscription_id, reason=reason or "Cancelado por el tenant",
                idempotency_key=f"budun-paypal-subscription-cancel-{subscription.pk}",
            )
            subscription.paypal_subscription_status = "CANCELLED"
            subscription.save(update_fields=["paypal_subscription_status", "updated_at"])
        except PaymentProviderError as error:
            audit_event(
                subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="subscription", object_id=subscription.pk,
                reason="No se pudo cancelar la suscripción recurrente en PayPal", metadata={"error": str(error)[:255]},
            )
    return subscription_services.cancel_subscription(subscription, immediate=immediate, reason=reason, user=user)


# ---------------------------------------------------------------------
# Webhooks de Subscriptions (FASE DE CORRECCIÓN 2C) — dispatch propio,
# SEPARADO del de Orders API v2 (`apps.billing.services._apply_webhook_
# event`, que resuelve un `PayPalTransaction`): estos eventos referencian
# una Subscription de PayPal, nunca una orden/captura/reembolso, así que
# el objeto a bloquear/actualizar es `Subscription`, nunca
# `PayPalTransaction`.
# ---------------------------------------------------------------------

SUBSCRIPTION_EVENT_PREFIXES = ("BILLING.SUBSCRIPTION.",)
SUBSCRIPTION_PAYMENT_EVENT_TYPES = ("PAYMENT.SALE.COMPLETED",)


def is_subscription_event(event_type):
    return event_type.startswith(SUBSCRIPTION_EVENT_PREFIXES) or event_type in SUBSCRIPTION_PAYMENT_EVENT_TYPES


def resolve_subscription_from_resource(event_type, resource):
    """Localiza la `Subscription` de Budun a partir del recurso del
    evento. `BILLING.SUBSCRIPTION.*` trae el ID de suscripción como
    `resource.id`; `PAYMENT.SALE.COMPLETED` lo trae como
    `resource.billing_agreement_id` (nombre heredado de la API de
    Payments clásica que PayPal reutiliza también para Subscriptions)."""
    if event_type in SUBSCRIPTION_PAYMENT_EVENT_TYPES:
        external_id = resource.get("billing_agreement_id", "")
    else:
        external_id = resource.get("id", "")
    if not external_id:
        return None
    return Subscription.all_objects.filter(paypal_subscription_id=external_id).first()


def apply_subscription_webhook_event(subscription_pk, *, event_type, resource):
    """Aplica la transición correspondiente — cada rama re-verifica el
    estado ACTUAL antes de escribir (mismo criterio que `_apply_webhook_
    event` de Orders API), así que un evento duplicado o fuera de orden
    es un no-op idempotente, nunca un error ni una doble aplicación."""
    if event_type in SUBSCRIPTION_PAYMENT_EVENT_TYPES:
        subscription = Subscription.all_objects.get(pk=subscription_pk)
        # Estructura real de PayPal para `PAYMENT.SALE.COMPLETED`
        # (hereda el formato de la API de Payments clásica, reutilizado
        # también para el cobro de Subscriptions): `resource.amount` =
        # {"total": "29.00", "currency": "USD"}.
        amount_info = resource.get("amount") or {}
        if not amount_info.get("total"):
            return  # evento sin monto reportado — nada seguro que aplicar.
        monto = Decimal(amount_info["total"])
        moneda = amount_info.get("currency", "")
        confirm_recurring_charge(subscription, amount=monto, currency=moneda, external_reference=resource.get("id", ""))
        return

    # `select_for_update()` exige una transacción real explícita — nunca
    # asumir que el llamador ya está dentro de una (un error real
    # encontrado durante esta misma corrección: funcionaba en los tests
    # unitarios solo porque `TestCase` envuelve cada prueba en su propia
    # transacción ambiente, y fallaba de verdad — silenciosamente
    # atrapado como `PayPalWebhookEvent.Status.ERROR` — en un smoke
    # manual fuera de ese contexto).
    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription_pk)
        nuevo_estado_externo = resource.get("status", "")
        if nuevo_estado_externo:
            subscription.paypal_subscription_status = nuevo_estado_externo
            subscription.save(update_fields=["paypal_subscription_status", "updated_at"])

    if event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
        return  # informativo — la activación real de Budun ocurre al confirmar el primer cobro (PAYMENT.SALE.COMPLETED).

    if event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
        if subscription.status == Subscription.Status.ACTIVE:
            subscription_services.mark_past_due(subscription)
        return

    if event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
        if subscription.status != Subscription.Status.SUSPENDED:
            subscription_services.suspend_subscription(subscription, reason="Suspendida por PayPal (umbral de fallos de cobro)")
        return

    if event_type == "BILLING.SUBSCRIPTION.CANCELLED":
        if subscription.status != Subscription.Status.CANCELLED:
            subscription_services.cancel_subscription(subscription, immediate=True, reason="Cancelada del lado de PayPal")
        return

    if event_type == "BILLING.SUBSCRIPTION.EXPIRED":
        if subscription.status != Subscription.Status.CANCELLED:
            subscription_services.cancel_subscription(subscription, immediate=True, reason="Expirada del lado de PayPal")
        return

    # BILLING.SUBSCRIPTION.CREATED/UPDATED y cualquier otro evento
    # reconocido pero fuera de alcance (p. ej. cambios de precio del
    # propio Billing Plan, que Budun nunca edita — un cambio de precio
    # siempre crea una PlanVersion/Billing Plan nuevos): no-op
    # deliberado, nunca un error.
