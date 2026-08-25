# FASE 13 — Expenses

## Objetivo
Gastos profesionales: categorías, proveedor opcional, documentos
adjuntos, monto, impuestos, método de pago, fecha, estado, y relación
con caja/pagos cuando el gasto se paga en efectivo desde una caja
física. Preparar (sin implementar todavía) recurrencia y aprobaciones
de gastos vía `apps.approvals` (FASE 11, ya construido).

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] CRUD de `Expense` (categoría, proveedor opcional, monto, impuestos, método, fecha, estado, documentos adjuntos)
- [ ] tenant scoped
- [ ] Relación con caja — un gasto pagado en efectivo desde una `CashRegister` requiere `CashSession` abierta (`apps.pos`) y genera el `CashMovement` correspondiente; otros métodos de pago no afectan el efectivo físico.
- [ ] Preparación de recurrencia (sin implementar el motor de repetición todavía, salvo necesidad real explícita)
- [ ] Preparación de aprobaciones de gastos por encima de un límite, reutilizando `apps.approvals` (sin conectar todavía salvo necesidad real explícita)

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 8 — Inventario Serializado

FASE 8 agregó inventario serializado (`InventoryUnit`, ver
`docs/inventory.md`). Revisado explícitamente: Gastos (registro de
egresos de la empresa, sin relación directa con unidades de inventario)
no consume esa interfaz — no se requiere ningún cambio de diseño en esta
fase por ese motivo. Se documenta aquí solo para dejar constancia de que
se revisó, tal como pidió el usuario para todas las fases 10–15.

## Nota de FASE 9 — Interfaz de Proveedores a consumir

FASE 9 agregó `apps/customers` (`Supplier`, ver `docs/suppliers.md`).
Cuando un gasto corresponda a un proveedor conocido, `Expense` debería
poder referenciarlo opcionalmente mediante su propia FK
(`Expense.supplier`, nulo/opcional — no todo gasto tiene un proveedor
formal), reutilizando `apps.customers.services.get_active_suppliers`
para el selector, en vez de reimplementar la consulta o duplicar datos
de proveedor dentro de `apps.expenses`.

## Nota de FASE 10 — Motor comercial (revisado, sin cambios de diseño necesarios)

FASE 10 agregó el motor comercial (`apps/sales`, ver `docs/sales.md`).
Revisado explícitamente: Gastos no tiene relación directa con
Cotizaciones/Proformas/Ventas/Pagos — no se requiere ningún cambio de
diseño en esta fase por ese motivo. Si en el futuro un gasto necesitara
un número comercial propio, reutilizar el patrón de `DocumentSequence`
(agregando su propio `DocumentType`) en vez de inventar un esquema de
numeración paralelo.

## Nota de sincronización — Caja y Autorizaciones ya construidas (FASE 11)

FASE 11 construyó `apps.pos` (`CashRegister`/`CashSession`/
`CashMovement`) y `apps.approvals` (`ApprovalPolicy`/`ApprovalRequest`)
como servicios reales — esta fase debe consumirlos, nunca
reimplementarlos:

- Un gasto pagado en efectivo desde una caja física exige una
  `CashSession` `OPEN` para quien registra el pago
  (`apps.pos.services.ensure_open_session_for_checkout`) y genera un
  `CashMovement` (tipo `CASH_OUT` o uno específico si esta fase decide
  agregarlo, p. ej. para distinguir "gasto" de "retiro genérico") —
  nunca un cálculo de efectivo paralelo al de `apps.pos`.
- Si esta fase agrega un límite de monto que un gasto puede registrar
  sin aprobación, debe usar `apps.approvals.services`
  (`request_approval`/`resolve_approval`), reutilizando el mismo
  patrón de "bloquear → solicitar → aprobar → reintentar" ya construido
  para descuentos/crédito excedido en el POS — ver `docs/approvals.md`
  sección 7, que ya anticipa esto como operación autorizable futura.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
