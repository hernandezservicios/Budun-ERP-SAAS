# Decisiones vigentes

1. Django + PostgreSQL.
2. Desarrollo local en Windows con PostgreSQL administrado mediante pgAdmin 4.
3. Sin Docker.
4. Sin MySQL/MariaDB.
5. Producción en Hostinger VPS.
6. SaaS Multi-Tenant con aislamiento estricto.
7. 25 fases exactas: 0–24.
8. API de Inventario `/api/v1/` read-only inicialmente para agentes CRM IA.
9. PayPal Sandbox antes de Production; PayPal MCP según documentación oficial vigente.
10. Antigravity es IDE; Claude es el agente principal.
11. Un `Payment` puede aplicarse a una o varias facturas del mismo cliente (`PaymentAllocation`, ledger append-only) — decidido tras el cierre inicial de FASE 10, revirtiendo la omisión original explícitamente permitida ("cuando no sea necesario"). Ver `docs/payments.md`.
12. Anticipo y saldo a favor son el MISMO saldo por cliente, nunca dos balances paralelos — múltiples orígenes (anticipo, sobrepago, nota de crédito, reembolso convertido a crédito) se suman en `get_customer_credit_balance` desde los ledgers reales (`Payment`/`PaymentAllocation` + `CreditNote`/`CreditNoteApplication`), sin una tabla `CustomerCreditLedger` separada (ver decisión 16). Ver `docs/accounts-receivable.md`.
13. Ninguna cantidad fija de cajas/terminales por tenant: `CashRegister` es ilimitado, creado libremente por el administrador del tenant. Ver `docs/cash-registers.md`.
14. Autorizaciones (`ApprovalRequest`/`ApprovalService`) son un servicio centralizado y reutilizable, nunca lógica de aprobación duplicada por módulo; jerarquía de resolución fija: usuario → rol → tenant → negar. Ver `docs/approvals.md`.
15. Cuentas por Cobrar del ERP (lo que un cliente le debe a un tenant) y Billing del SaaS (lo que un tenant le debe a Budun ERP, FASE 17) son dominios ortogonales que nunca se mezclan estructuralmente.
16. `CustomerCreditLedger` como tabla separada NO se construyó (FASE 11): el saldo a favor se deriva generalizando `get_customer_credit_balance`/`get_sale_paid_amount` para sumar `Payment`/`PaymentAllocation` (FASE 10) + `CreditNote`/`CreditNoteApplication` (FASE 11) — dos ledgers reales, nunca una tercera tabla resumen. Ver `docs/accounts-receivable.md`.
17. El propietario del tenant (`Membership.Role.OWNER`) está siempre autorizado para operar cualquier caja, dar cualquier descuento y exceder el crédito de cualquier cliente, sin necesidad de una `ApprovalPolicy` configurada — regla de negocio explícita (el propietario ya tiene autoridad administrativa completa desde FASE 4), aplicada en el servidor. Ver `docs/approvals.md`/`docs/pos.md`.
18. El POS (FASE 11) es una interfaz de orquestación sobre `apps.sales`/`apps.inventory`/`apps.customers`/`apps.approvals` — nunca un segundo motor de ventas, nunca lógica de negocio duplicada.
19. `docs/phases/FASES_OFICIALES_0_24_ACTUALIZADAS.md` (entregado por el usuario tras el cierre de FASE 11) es la nueva fuente maestra de alcance de las 25 fases — agregado a la jerarquía de "Fuente de verdad" de `CLAUDE.md`. Amplía significativamente el alcance descrito de FASE 12 (Purchases: órdenes, recepción parcial/completa, costos, landed cost, cuentas por pagar) y FASE 14 (Reportes de Inventario detallados) respecto a lo que existía antes; no crea ninguna fase nueva (siguen siendo exactamente 25, 0–24).
