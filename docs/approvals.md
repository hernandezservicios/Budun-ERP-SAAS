# Autorizaciones (`ApprovalRequest` / `ApprovalService`)

> **Estado: CONSTRUIDO en FASE 11** (`apps/approvals`), consumido por
> el POS (`apps/pos`) para descuentos y crédito excedido — los únicos
> dos consumidores reales hoy, tal como se anticipó en este documento.
> El resto de operaciones autorizables de la sección 7 (reembolsos
> especiales, anulaciones sensibles, ajustes de inventario, etc.)
> siguen sin construirse; `ApprovalService` ya está listo para que una
> fase futura los conecte sin duplicar esta lógica. Ver `docs/pos.md`.

## 1. Principio central: un solo servicio, muchos consumidores

`ApprovalService` es la única vía para: pedir autorización, resolverla
(aprobar/rechazar) y consultar si una operación concreta necesita
autorización antes de ejecutarse. Cualquier módulo que necesite este
patrón (descuentos, crédito excedido, reembolsos especiales,
anulaciones sensibles, ajustes de inventario, movimientos de caja
especiales) lo consume — nunca reimplementa su propia versión. Mismo
principio arquitectónico que ya rige `apps.inventory.services`/
`apps.sales.services`: una única capa de servicios como fuente de
verdad de una regla de negocio.

## 2. `ApprovalRequest`

Campos: `tenant`, `type` (extensible por `choices`, mismo patrón que
`PaymentMethod`/`IdentificationType` — un tipo nuevo es una línea
nueva, nunca rehacer el modelo), `document_type`/`document_id`
(referencia genérica al documento afectado — mismo patrón ya usado por
`SalesDocumentAttachment`/`SalesActivityLog`), `requested_by`,
`approved_by` (nulo mientras esté `PENDING`), `reason`,
`requested_value` (el valor que se quiere autorizar: un descuento, un
límite de crédito excedido, un monto de ajuste), `allowed_limit` (el
límite que se superó, para dejar constancia de POR QUÉ hizo falta
autorización), `approved_value` (nulo hasta la decisión; puede diferir
de `requested_value` si el aprobador autoriza un valor distinto al
pedido), `status`, `requested_at`, `decided_at`, `metadata` (JSON,
**nunca secretos ni datos sensibles sin cifrar** — mismo principio de
"logs sin secretos" de `CLAUDE.md`).

Estados (`ApprovalRequest.Status`):

```
PENDING → APPROVED
        → REJECTED
        → CANCELED   (el solicitante desiste antes de una decisión)
        → EXPIRED     (venció sin decisión, política de tiempo configurable)
```

## 3. Jerarquía de resolución: usuario → rol → tenant → negar

`ApprovalService.check_authorization(user, *, action_type, value)`
resuelve, en este orden estricto, sin saltarse ningún nivel:

1. **Autorización específica del usuario**, si existe (un override
   configurado explícitamente por un administrador para ESE usuario en
   particular — p. ej. "este cajero en concreto puede autorizar hasta
   15%", distinto del límite general de su rol).
2. **Política del rol** del usuario (p. ej. Cajero 10%, Manager 20%).
3. **Política global/tenant** (un límite por defecto cuando ni el
   usuario ni su rol tienen una política específica configurada).
4. **Negar** (y generar/permitir generar un `ApprovalRequest`) si
   ninguno de los tres niveles anteriores autoriza el valor solicitado.

Esta jerarquía se documenta aquí como contrato **oficial** — la fase
que implemente `ApprovalService` debe respetarla exactamente, no
inventar un orden distinto (p. ej. "rol antes que usuario" sería
incorrecto: el override específico de un usuario siempre debe poder
superar — en cualquier dirección, más o menos permisivo — la política
genérica de su rol).

## 4. Descuentos: autorización por porcentaje Y por monto

Cada rol (y, por la jerarquía de la sección 3, cada usuario mediante
override) puede tener configurados **dos límites independientes**,
ninguno de los dos hardcodeado:

- `max_discount_percent` (ej.: Cajero 10%, Manager 20%, Admin
  configurable).
- `max_discount_amount` (ej.: Cajero RD$2,000).

**Si la operación excede CUALQUIERA de los dos límites, requiere
autorización** — no basta con cumplir uno de los dos:

| Descuento solicitado | ¿Dentro del % permitido? | ¿Dentro del monto permitido? | Resultado |
|---|---|---|---|
| 10% (dentro del límite) pero RD$2,500 | Sí | No (límite RD$2,000) | Requiere autorización |
| RD$1,000 (dentro del límite) pero 15% | No (límite 10%) | Sí | Requiere autorización |
| 8% y RD$1,500 | Sí | Sí | No requiere autorización |

Los límites deben ser **configurables por tenant/rol/usuario**, nunca
un porcentaje o monto fijo en el código — mismo principio ya aplicado
a `PaymentMethod`/categorías de documento en fases anteriores.

## 5. Crédito excedido

Cuando una venta a crédito superaría el `credit_limit`/`credit_days`/
`credit_enabled` ya existentes en `Customer` (FASE 9, ver
`docs/customers.md`), el sistema debe pedir autorización
(`ApprovalService.check_authorization`) si el usuario actual no tiene
suficiente nivel para aprobarlo por sí mismo. **Nunca un bypass desde
el frontend**: la validación vive en la capa de servicios (`apps.sales.services`
o donde corresponda cuando se construya), nunca solo en JavaScript ni
en una condición de plantilla.

## 6. Auditoría

Toda autorización (solicitada, aprobada, rechazada, cancelada,
vencida) queda auditada: solicitante, aprobador, documento afectado,
valor solicitado, límite superado, valor aprobado, motivo, fechas de
solicitud y decisión. **El historial de aprobaciones nunca se borra** —
mismo principio de auditoría inmutable que `PaymentAllocation`/`Return`
(una decisión equivocada se corrige con una nueva `ApprovalRequest` o
un movimiento compensatorio, nunca editando ni eliminando el registro
original).

## 7. Operaciones autorizables futuras (diseño extensible, no todas construidas ahora)

`ApprovalService` debe poder reutilizarse, sin cambios estructurales,
para:

- Descuentos por encima del límite (sección 4).
- Crédito excedido (sección 5).
- Reembolsos especiales (montos altos, o fuera de la política estándar
  de `docs/returns.md`).
- Anulaciones sensibles (p. ej. anular una venta ya confirmada por una
  vía distinta a `create_return`, si una fase futura lo permitiera).
- Ajustes de inventario fuera de lo normal (FASE 12/13).
- Movimientos de caja especiales (`docs/cash-registers.md`, sección 5:
  "ajuste autorizado").
- Otras operaciones críticas que una fase futura identifique.

Esta fase de diseño **no implementa** todos estos casos — solo deja el
servicio preparado para que cada uno se conecte sin reinventar el
patrón de solicitud/resolución/auditoría.

## 8. Dónde vive esto (relación con las fases)

`ApprovalRequest`/`ApprovalService` se construyeron en `apps.approvals`
(app propia, reutilizable — ni dentro de `apps.pos` ni de
`apps.tenants`), consumidos primero por FASE 11 (POS), que es donde
surgió la primera necesidad operativa real (descuentos y crédito
excedido durante una venta de mostrador) — ver
`docs/phases/PHASE-11-pos.md` y `docs/pos.md`. La infraestructura de
roles/permisos más rica (políticas más allá de OWNER/MEMBER) sigue
siendo responsabilidad de FASE 15 (Roles + Audit + API, ver
`docs/phases/PHASE-15-roles-plus-audit-plus-inventory-api.md`), que
debe **extender**, no sustituir, el modelo `ApprovalPolicy`/
`Membership.Role` ya existente desde esta fase.

## 9. Estado de implementación (FASE 11)

`ApprovalRequest`/`ApprovalPolicy` están construidos en `apps/approvals`
tal como se diseñó aquí: jerarquía usuario→rol→tenant→negar
(`services.get_effective_policy`), consumo de descuentos y crédito
excedido desde `apps.pos`, consumo de la resolución (`can_user_approve`)
gateado por el propietario del tenant o por `ApprovalPolicy.can_approve`.
Se agregó un mecanismo no anticipado explícitamente en la
especificación original pero necesario para cumplir "nunca reutilizar
una autorización dos veces": `ApprovalRequest.consumed_at`/
`consumed_by` (`services.mark_consumed`/`get_usable_approved_request`)
— sin esto, una misma solicitud aprobada podría aplicarse a múltiples
descuentos distintos dentro de la misma venta. Ver `docs/pos.md` para
el flujo completo bloquear→solicitar→aprobar→reintentar.

Sigue sin construirse: reembolsos especiales, anulaciones sensibles,
ajustes de inventario y movimientos de caja especiales como
operaciones autorizables (sección 7) — el servicio ya está listo para
que una fase futura los conecte sin duplicar esta lógica.
