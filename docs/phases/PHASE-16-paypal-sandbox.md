# FASE 16 — PayPal Sandbox + Pagos Online + Integración con Billing SaaS

> **Estado: CONSTRUIDO.** Ver `docs/paypal.md` para el detalle completo
> de la implementación (`apps.billing`: modelos, provider, endpoints
> oficiales, idempotencia, webhooks, refunds, permisos, auditoría). El
> checklist de la sección 18 se marcó abajo con evidencia. FASE 17
> (Billing SaaS completo) sigue sin implementarse.

## 1. Objetivo

Implementar la integración profesional de PayPal como proveedor de pagos online de la plataforma SaaS, sin crear un segundo sistema de pagos, suscripciones o facturación.

PayPal debe ser un proveedor externo de Billing SaaS.

La fase debe preparar y validar:

- Sandbox;
- credenciales seguras;
- checkout/orden o suscripción según el diseño aprobado;
- confirmación;
- webhooks;
- validación de webhooks;
- idempotencia;
- reconciliación;
- errores y reintentos;
- cancelaciones;
- refunds cuando correspondan;
- integración contable/financiera del SaaS cuando corresponda.

## 2. Separación de dominios

### ERP operativo del tenant

Incluye:

- ventas;
- clientes;
- CxC;
- compras;
- CxP;
- caja;
- inventario;
- gastos;
- RRHH;
- nómina;
- contabilidad.

### Billing SaaS

Incluye lo que cada tenant paga al operador del SaaS por usar la plataforma.

No reutilizar `apps.sales.Payment`, `PaymentAllocation` o CxC del tenant como almacenamiento del Billing SaaS.

PayPal debe terminar en los modelos/servicios propios de Billing SaaS.

## 3. Regla incremental

Crear únicamente lo necesario para FASE 16 y sus dependencias inmediatas.

No implementar el Billing SaaS completo de FASE 17 dentro de esta fase.

La integración debe quedar preparada para consumir el núcleo que FASE 17 implementará.

## 4. Provider abstraction

PayPal debe integrarse mediante una capa de provider/adaptador.

Conceptualmente:

```text
Billing SaaS
    ↓
Payment Provider Interface
    ↓
PayPal Provider
```

No colocar lógica de PayPal directamente en modelos de Billing.

La arquitectura debe permitir futuros proveedores sin rehacer el núcleo.

## 5. Credenciales

Las credenciales de PayPal deben:

- almacenarse de forma segura;
- permanecer fuera de Git;
- no aparecer en logs;
- no llegar al frontend;
- no llegar al LLM;
- diferenciar Sandbox y Live;
- validar configuración antes de operar.

## 6. Configuración

La configuración debe existir en el ámbito correcto de plataforma/SaaS.

Debe permitir:

- modo Sandbox/Live;
- Client ID;
- Client Secret;
- estado;
- Test Connection cuando sea viable;
- información de la cuenta/cuenta comercial asociada cuando sea necesario.

No confundir credenciales PayPal del SaaS con configuraciones PayPal de un tenant.

## 7. Orders / Payments / Subscriptions

La implementación debe utilizar los conceptos reales de PayPal que correspondan al flujo elegido.

No asumir que una Order de PayPal es una Invoice interna ni almacenar dos fuentes equivalentes.

Debe existir mapeo explícito:

```text
PayPal external event
        ↓
Billing payment/subscription event
```

## 8. Webhooks

Los webhooks son fuente crítica de confirmación asíncrona.

Deben:

- validar autenticidad/firma con el mecanismo oficial aplicable;
- validar tipo de evento;
- identificar la operación externa;
- soportar eventos duplicados;
- soportar eventos fuera de orden;
- ser idempotentes;
- no activar una suscripción solamente por parámetros del navegador.

## 9. Idempotencia y reconciliación

Un mismo evento externo no puede:

- crear dos pagos;
- activar dos veces una suscripción;
- extender dos veces el período;
- generar dos refunds.

Debe existir una llave de idempotencia/event identifier adecuada.

Mantener separados:

- identificador externo;
- estado del proveedor;
- estado interno.

Los campos definitivos deben agregarse solo si tienen uso real en la implementación.

## 10. Integración con Payment

Si FASE 16 confirma un pago SaaS:

```text
PayPal
→ Provider
→ Billing Payment Service
```

No escribir directamente en la base desde el webhook.

Toda mutación de negocio debe pasar por el servicio central.

## 11. Multi-moneda

No hardcodear una única moneda.

Debe conservarse:

- moneda interna;
- monto interno;
- moneda reportada por PayPal;
- monto reportado por PayPal;

cuando sean necesarios para reconciliación.

Nunca mezclar monedas sin una regla explícita.

## 12. Refund

Los reembolsos de PayPal pueden ser asíncronos.

El dominio interno debe poder representar al menos el ciclo:

```text
PENDING
→ COMPLETED
```

y fallos:

```text
PENDING
→ FAILED
```

sin borrar el historial.

No crear un estado paralelo innecesario si el modelo de Billing ya lo contempla.

## 13. Contabilidad

No utilizar `apps.accounting` tenant-scoped para registrar automáticamente la relación Tenant→SaaS.

Si el operador SaaS necesita contabilidad propia, deberá ser un dominio separado de la contabilidad del tenant.

FASE 16 únicamente debe respetar las interfaces que existan para esa futura trazabilidad.

## 14. Seguridad

Probar:

- credenciales inválidas;
- modo incorrecto;
- webhook inválido;
- webhook duplicado;
- webhook fuera de orden;
- payload manipulado;
- refund duplicado;
- aislamiento de plataforma;
- no exposición de secretos.

## 15. Tests

Mínimos:

- configuración;
- autenticación;
- order/payment;
- webhook;
- idempotencia;
- reconciliación;
- cancelación;
- refund;
- errores/reintentos;
- multi-moneda;
- regresión.

## 16. Smoke test

Probar en Sandbox:

```text
checkout
→ pago
→ webhook
→ Billing event
→ reconciliación
```

y, cuando corresponda:

```text
refund
→ webhook/event
→ estado interno actualizado
```

## 17. Dependencias

Revisar:

- `docs/billing.md`;
- `docs/payments.md`;
- `docs/currency.md`;
- FASE 15;
- arquitectura real del proyecto.

No inventar endpoints de PayPal.

Cuando la implementación lo requiera, consultar la documentación oficial vigente de PayPal antes de fijar detalles del API.

## 18. Criterios de aceptación

- [x] Sandbox funcional — Test Connection, crear orden, consultar orden y verify-webhook-signature ejecutados de verdad contra PayPal Sandbox (9/9 verificaciones, `smoke_paypal_fase16.py`).
- [x] Credenciales seguras — `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`/`PAYPAL_WEBHOOK_ID` en `.env` (nunca BD/Git); access token nunca persistido, solo cacheado en memoria.
- [x] Webhooks validados — verificación oficial de firma (`/v1/notifications/verify-webhook-signature`), probada tanto mockeada (unit tests) como contra el endpoint REAL de Sandbox (smoke test).
- [x] Idempotencia — `PayPal-Request-Id` hacia PayPal, `UniqueConstraint` en `event_id` hacia nosotros, verificada con hilos reales y con doble entrega real contra Sandbox.
- [x] Reconciliación — `provider_amount`/`provider_currency` separados de `amount`/`currency` internos.
- [x] Refund — ciclo completo `CONFIRMED → REFUND_PENDING/REFUNDED/REFUND_FAILED`, sin duplicar reembolsos.
- [x] Multi-moneda — moneda interna y reportada por PayPal conservadas por separado, nunca mezcladas.
- [x] Sin duplicar el Billing — ningún `Plan`/`Subscription`/`SaaS Invoice`/`SaaS Payment` creado; `apps.sales.Payment` nunca tocado.
- [x] Seguridad revisada — credenciales inválidas, ambiente incorrecto, firma inválida/duplicada/manipulada, replay, refund duplicado, acceso no autorizado (403 sin `is_superuser`), sin fuga de secretos (verificado inspeccionando el contenido serializado de cada `AuditLog`).
- [x] Suite completa verde — **988/988 tests OK** (941 previos + 47 nuevos de `apps.billing`, incluyendo el test de regresión del bug #107).
- [x] Smoke test real — `smoke_paypal_fase16.py`, 9/9 verificaciones OK contra PayPal Sandbox real (credenciales del usuario).
- [x] Documentación actualizada — `docs/paypal.md` (reescrito, CONSTRUIDO), `docs/billing.md`, `CLAUDE.md`/`docs/MASTER-PROMPT.md`/`ARCHITECTURE.md`, `docs/project-status/*`.
- [x] Git commit.

## 19. Regla de parada

Al cerrar FASE 16:

**DETENERSE.**

No iniciar FASE 17 automáticamente.
