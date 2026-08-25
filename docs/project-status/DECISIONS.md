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
12. Anticipo y saldo a favor son el MISMO saldo por cliente, nunca dos balances paralelos — múltiples orígenes (anticipo, sobrepago, nota de crédito, reembolso convertido a crédito) alimentan un único `CustomerCreditLedger` conceptual. Ver `docs/accounts-receivable.md`.
13. Ninguna cantidad fija de cajas/terminales por tenant: `CashRegister` es ilimitado, creado libremente por el administrador del tenant. Ver `docs/cash-registers.md`.
14. Autorizaciones (`ApprovalRequest`/`ApprovalService`) son un servicio centralizado y reutilizable, nunca lógica de aprobación duplicada por módulo; jerarquía de resolución fija: usuario → rol → tenant → negar. Ver `docs/approvals.md`.
15. Cuentas por Cobrar del ERP (lo que un cliente le debe a un tenant) y Billing del SaaS (lo que un tenant le debe a Budun ERP, FASE 17) son dominios ortogonales que nunca se mezclan estructuralmente.
