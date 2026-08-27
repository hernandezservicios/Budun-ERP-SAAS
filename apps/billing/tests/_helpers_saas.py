"""Utilidades de prueba de Billing SaaS completo (FASE 17)."""

from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.billing.models import Plan, PlanVersion, SaaSCustomer
from apps.tenants.models import Membership, Tenant

User = get_user_model()


def crear_tenant_con_owner(*, name="Empresa Billing SaaS", slug="empresa-billing-saas", email="owner.saas@example.com"):
    tenant = Tenant.objects.create(name=name, slug=slug)
    owner = User.objects.create_user(email=email, password="clave-de-prueba-987")
    Membership.objects.create(user=owner, tenant=tenant, role=Membership.Role.OWNER)
    return tenant, owner


def crear_plan_con_version(*, slug="profesional-saas", nombre="Profesional", precio=Decimal("29.00"), frecuencia="monthly", currency="USD"):
    plan = Plan.objects.create(name=nombre, slug=slug)
    version = PlanVersion.objects.create(plan=plan, frequency=frecuencia, price_amount=precio, price_currency=currency, is_current=True)
    return plan, version


def crear_saas_customer(*, name="Cliente SaaS de prueba", email="cliente.saas@example.com"):
    return SaaSCustomer.objects.create(name=name, email=email)
