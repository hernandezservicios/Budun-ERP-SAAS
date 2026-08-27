"""
Señales de Django — el contrato estable que FASE 17 conectará para
reaccionar a eventos de Billing (activar/renovar una `Subscription`,
actualizar una `SaaS Invoice`, etc. — ninguno de esos modelos existe
todavía, ver `docs/billing.md`). FASE 16 solo EMITE estas señales
(además de auditar cada evento); no tiene ningún receptor propio más
allá de la propia auditoría, documentado explícitamente como el punto
de extensión pedido en `docs/phases/PHASE-16-paypal-sandbox.md`
sección 21 ("preparar los eventos que FASE 17 consumirá").

`SUBSCRIPTION_ACTIVATED`/`SUBSCRIPTION_CANCELLED` (mencionados como
ejemplo en la instrucción de FASE 16) NO se modelan aquí: no existe
todavía ningún concepto de `Subscription` al que asociarlos (eso es
FASE 17) — inventar esas señales ahora sería exactamente el "segundo
sistema de Billing" que la fase prohíbe. Los nombres reales usados son
los que corresponden a lo que FASE 16 sí implementa: el ciclo de vida
de un pago/reembolso de PayPal."""

import django.dispatch

payment_confirmed = django.dispatch.Signal()
payment_failed = django.dispatch.Signal()
checkout_cancelled = django.dispatch.Signal()
refund_requested = django.dispatch.Signal()
refund_completed = django.dispatch.Signal()
refund_failed = django.dispatch.Signal()
