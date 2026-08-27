"""
Datos de planes de precios (FASE 6 — Landing + Pricing).

Fuente única de verdad para la sección de precios de la landing: la
plantilla itera sobre `PLANS`, nunca hardcodea un precio directamente.

IMPORTANTE — precios de ejemplo: los valores de `price` de este archivo
son PLACEHOLDERS ilustrativos (montos y condiciones típicos de un SaaS
pequeño/mediano). Todavía no hay ninguna decisión de negocio real sobre
precios. Antes de un lanzamiento real, el usuario debe revisar y
actualizar estos valores.

FASE 16 agrega `price_amount`/`price_currency` (Decimal/ISO-4217) a los
planes que sí tienen un precio fijo cobrable — necesarios para poder
crear una orden real de PayPal (la Orders API exige un monto Decimal
exacto, nunca un string de presentación como "$29"). Un plan sin
`price_amount` (gratis, o "Personalizado"/contactar ventas) no tiene
checkout de autoservicio — `apps.billing.services.create_checkout` lo
rechaza explícitamente. Esto NO es el modelo `Plan` real de FASE 17
(que vivirá en base de datos con ciclos de facturación, periodos de
prueba, etc.) — sigue siendo el mismo módulo de configuración de FASE 6,
solo con los campos mínimos que FASE 16 necesita para ser real.

Por qué un módulo de configuración y no un modelo de base de datos: FASE
17 — Billing SaaS construirá el modelo real de planes/suscripciones
conectado a PayPal (con campos que hoy no se pueden anticipar
correctamente: IDs de producto de PayPal, ciclos de facturación exactos,
períodos de prueba, etc.). Crear un modelo `Plan` ahora, en FASE 6, se
quedaría obsoleto o requeriría una migración de reemplazo en FASE 17. Un
módulo de configuración evita ese desperdicio y sigue cumpliendo el
requisito de "no duplicar precios en varias plantillas".
"""

from decimal import Decimal

PLANS = [
    {
        "id": "starter",
        "nombre": "Starter",
        "precio": "Gratis",
        "periodo": "",
        "descripcion": "Para empezar a operar tu negocio sin costo inicial.",
        "destacado": False,
        "caracteristicas": [
            "1 empresa (tenant)",
            "Hasta 2 usuarios",
            "Productos e inventario básico",
            "Soporte por comunidad",
        ],
        "cta_texto": "Crear cuenta gratis",
        "price_amount": None,
        "price_currency": "USD",
    },
    {
        "id": "profesional",
        "nombre": "Profesional",
        "precio": "$29",
        "periodo": "/mes por empresa",
        "descripcion": "Para negocios en crecimiento que necesitan el ERP completo.",
        "destacado": True,
        "caracteristicas": [
            "1 empresa (tenant)",
            "Usuarios ilimitados",
            "Todos los módulos: ventas, POS, compras, gastos, reportes",
            "Roles y auditoría",
            "Soporte prioritario por correo",
        ],
        "cta_texto": "Empezar prueba",
        "price_amount": Decimal("29.00"),
        "price_currency": "USD",
    },
    {
        "id": "empresarial",
        "nombre": "Empresarial",
        "precio": "Personalizado",
        "periodo": "",
        "descripcion": "Para operaciones con múltiples sucursales o necesidades a medida.",
        "destacado": False,
        "caracteristicas": [
            "Múltiples empresas (tenants)",
            "API de Inventario para integraciones y agentes IA",
            "Acuerdos de nivel de servicio (SLA)",
            "Soporte dedicado",
        ],
        "cta_texto": "Contactar a ventas",
        "price_amount": None,
        "price_currency": "USD",
    },
]


def get_plan(plan_id):
    """Devuelve el dict del plan (`PLANS`) por `id`, o `None`. Única
    vía sancionada para resolver un plan por código — nunca iterar
    `PLANS` manualmente desde otro módulo."""
    for plan in PLANS:
        if plan["id"] == plan_id:
            return plan
    return None
