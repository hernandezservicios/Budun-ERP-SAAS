from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.billing.models import Coupon
from apps.billing.services import reports as services
from apps.billing.services import subscriptions as subscription_services

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


class MrrWithCouponTests(TestCase):
    """FASE DE CORRECCIÓN 5: `_mrr_de_suscripcion` usaba el precio de
    LISTA del plan sin importar si la suscripción tenía un cupón vigente
    — antes de esta corrección, el MRR/ARR reportado sobreestimaba el
    ingreso real de cualquier suscripción con un cupón activo (no usaba
    el mismo cálculo de descuento que la factura real ya aplica)."""

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("100.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)

    def test_mrr_sin_cupon_usa_el_precio_de_lista(self):
        resumen = services.get_billing_dashboard_summary()
        self.assertEqual(resumen["mrr"], Decimal("100.00"))

    def test_mrr_con_cupon_vigente_aplica_el_mismo_descuento_que_la_factura(self):
        cupon = Coupon.objects.create(code="MRR10", discount_type=Coupon.DiscountType.PERCENT, discount_value=Decimal("10"))
        self.subscription.coupon = cupon
        self.subscription.save(update_fields=["coupon"])
        resumen = services.get_billing_dashboard_summary()
        self.assertEqual(resumen["mrr"], Decimal("90.00"))

    def test_mrr_con_cupon_ya_vencido_vuelve_a_usar_el_precio_de_lista(self):
        cupon = Coupon.objects.create(
            code="MRR-VENCIDO", discount_type=Coupon.DiscountType.PERCENT, discount_value=Decimal("10"),
            valid_until=date.today() - timedelta(days=1),
        )
        self.subscription.coupon = cupon
        self.subscription.save(update_fields=["coupon"])
        resumen = services.get_billing_dashboard_summary()
        self.assertEqual(resumen["mrr"], Decimal("100.00"))
