# PayPal (especificación)

> **Estado: ESPECIFICACIÓN, no implementación.** Diseño aprobado para
> FASE 16 — ningún campo, modelo ni integración se crea a partir de
> este documento. Detalle completo en
> `docs/phases/PHASE-16-paypal-sandbox.md`.
>
> **Corrección de sincronización**: la versión anterior de este
> documento describía PayPal integrándose directamente sobre
> `apps.sales.Payment`/`Refund` (el motor de pagos del ERP de cada
> tenant). Esa descripción quedó **contradicha** por la decisión
> definitiva de FASE 16/17 (ver `docs/phases/PHASE-16-paypal-sandbox.md`
> sección 2, `docs/billing.md`): **PayPal es un proveedor de pagos del
> Billing SaaS** (lo que un `Tenant` le paga a Budun ERP por usar la
> plataforma) — **nunca** un proveedor de pagos del ERP operativo de
> cada tenant. Este documento se reescribe para reflejar esa decisión.

Sandbox primero, luego Production. La integración debe seguir
documentación oficial vigente de PayPal (nunca inventar endpoints,
argumentos o herramientas MCP).

## 1. PayPal es un provider de Billing SaaS, no del ERP del tenant

```text
Billing SaaS (apps.billing, FASE 17)
    ↓
Payment Provider Interface
    ↓
PayPal Provider
```

PayPal **nunca** se conecta a `apps.sales.Payment`/`PaymentAllocation`/
`Refund` (el motor de cuentas por cobrar de cada tenant, FASE 10/11) —
esos modelos siguen siendo exclusivamente del ERP operativo del
tenant, y PayPal ahí no participa. Todo pago confirmado por PayPal
termina en los modelos propios de Billing SaaS (`SaaS Payment`, ver
`docs/billing.md`), nunca en un `Payment` de `apps.sales`.

La única superposición legítima entre "PayPal" y `apps.sales` es
distinta y ya existe: un tenant puede registrar manualmente que UN
CLIENTE SUYO le pagó por PayPal fuera del sistema (`Payment.method`
extensible, ver `docs/payments.md`/`docs/sales.md`) — eso es una
entrada manual del cajero/administrador del tenant, no una integración
en vivo, y no tiene ninguna relación con la integración de FASE 16.

## 2. Separación de dominios (ver `docs/billing.md`)

| | ERP operativo del tenant | Billing SaaS (esta integración) |
|---|---|---|
| Quién paga a quién | Cliente → Tenant | Tenant → Budun ERP |
| Modelos | `apps.sales.Payment`/`PaymentAllocation`/`Refund` | `SaaS Payment`/`SaaS Invoice`/`Subscription` (FASE 17) |
| PayPal aquí | No se integra (solo entrada manual, ver arriba) | Provider oficial vía Payment Provider Interface |

## 3. Provider abstraction

No colocar lógica de PayPal directamente en los modelos de Billing —
una capa de provider/adaptador (`PayPalProvider`) implementa una
interfaz genérica (`PaymentProviderInterface`) que Billing SaaS
consume, para poder agregar futuros proveedores sin rehacer el
núcleo. Toda mutación de negocio (confirmar pago, activar suscripción,
registrar refund) pasa por el servicio central de Billing — un
webhook **nunca** escribe directamente en la base de datos.

## 4. Credenciales

Credenciales de PayPal DEL SAAS (nunca confundir con configuraciones
PayPal que un tenant pudiera tener para sí mismo, si en el futuro
existieran): fuera de Git, no en logs, no en frontend, no llegan al
LLM. Diferenciar Sandbox/Live explícitamente. Configuración en el
ámbito de PLATAFORMA (Super Admin), no por tenant.

## 5. Idempotencia y reconciliación

Un identificador de evento/idempotencia de PayPal nunca puede:
crear dos pagos, activar dos veces una suscripción, extender dos
veces un período, ni generar dos refunds. Mantener separados:
identificador externo (PayPal), estado del proveedor, estado interno
de Billing — nunca un único campo que confunda los tres.

## 6. Webhooks

Verificación de firma obligatoria (documentación oficial vigente de
PayPal). Deben soportar eventos duplicados y fuera de orden, ser
idempotentes, y nunca activar una suscripción solo por parámetros del
navegador (la confirmación real siempre llega por webhook verificado,
nunca por un simple "redirect exitoso" del checkout).

## 7. Refunds

Un reembolso de PayPal puede ser asíncrono — el dominio de Billing
SaaS debe poder representar al menos `PENDING → COMPLETED` y
`PENDING → FAILED`, sin borrar historial (mismo principio de
inmutabilidad ya aplicado en todo el proyecto a `Return`/
`PaymentAllocation` revertida/`JournalEntry` reversado). Distinguir
siempre refund / nota de crédito / saldo a favor DE BILLING (ver
`docs/billing.md` sección de Refunds) — nunca el `Refund` de
`apps.sales`, que es un concepto completamente distinto del ERP.

## 8. Multi-moneda

No hardcodear una única moneda. Cuando sea necesario para
reconciliación, conservar moneda/monto interno de Billing junto con
moneda/monto reportado por PayPal (que puede diferir si hubo
conversión del lado del proveedor) — nunca mezclarlos sin una regla
explícita.

## 9. Contabilidad

No usar `apps.accounting` tenant-scoped para la relación Tenant→SaaS.
Si el operador SaaS necesita contabilidad propia, es un dominio
separado (ver `docs/billing.md` sección de contabilidad).

## 10. MCP

MCP es una herramienta del entorno de agente/desarrollo/operaciones,
no un sustituto del backend de pagos — el flujo real de cobro nunca
depende de que el agente esté disponible. Consultar siempre
documentación oficial vigente de PayPal/PayPal MCP antes de fijar
detalles del API — nunca inventar endpoints ni argumentos.

## Qué NO se construye con este documento

Ninguna integración real, ningún modelo de Billing, ningún webhook.
Ver `docs/phases/PHASE-16-paypal-sandbox.md` para el checklist
completo de la fase.
