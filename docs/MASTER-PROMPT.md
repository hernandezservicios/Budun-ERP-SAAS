# MASTER PROMPT — SaaS ERP Multi-Tenant

Actúa como un equipo senior de arquitectura, Django, PostgreSQL, REST API, seguridad, UX/UI, QA, DevOps y pagos. Construye desde cero un SaaS ERP Multi-Tenant profesional.

## Stack oficial

- Windows para desarrollo.
- Python + virtualenv.
- Django.
- PostgreSQL.
- pgAdmin 4 para administración gráfica local.
- Git/GitHub.
- Hostinger VPS en producción.
- Gunicorn + Nginx o servidor web apropiado en producción.
- Redis solo si se justifica posteriormente.
- PayPal + PayPal MCP.

## Prohibiciones

- NO Docker.
- NO Docker Desktop.
- NO Docker Compose.
- NO MySQL.
- NO MariaDB.
- NO WAMP como dependencia.
- NO SQLite como base oficial del proyecto.
- NO Django Admin como UI principal.

## Fases

Hay exactamente 25 fases: 0 a 24. No saltar ninguna.

0. Auditoría del entorno
1. Project Foundation
2. PostgreSQL Foundation
3. Multi-Tenancy
4. Authentication
5. Design System
6. Landing + Pricing
7. Dashboard
8. Products + Inventory
9. Customers + Suppliers
10. Sales Engine
11. POS
12. Purchases
13. Expenses
14. Reports
15. Roles + Audit + Inventory API
16. PayPal Sandbox
17. Billing SaaS
18. Security Hardening
19. Performance
20. Backups
21. Hostinger Deployment
22. Data Migration
23. Production Verification
24. Final Audit

## Ciclo por fase

Analizar → planificar → implementar → ejecutar → probar → verificar → corregir → volver a probar → documentar → commit → cerrar.

Nunca avanzar con fallos críticos.

## UX/UI

Diseña una interfaz moderna, profesional, sobria y legible. Tú decides la dirección visual concreta, pero debe priorizar experiencia de usuario, claridad, jerarquía, consistencia, accesibilidad y productividad. La identidad puede usar azul y verde como colores principales/secundarios, con neutros y colores semánticos. Evita colores extraños, neón, exceso de gradientes y saturación visual.

## Multi-Tenancy

Single PostgreSQL database con aislamiento estricto por tenant. Ningún tenant puede acceder a datos de otro. Probar expresamente este requisito.

## API de Inventario

En `Configuración → API de Inventario` crear una integración para agentes CRM IA:

- Base URL `/api/v1/`.
- API Key por tenant.
- Generar, regenerar y revocar.
- Mostrar la clave completa solo en el momento controlado de creación/rotación; después enmascararla.
- Botón Probar Conexión.
- Estado: Conectado, No conectado, Error, Deshabilitado.
- Última prueba, última conexión, último error.
- API read-only inicialmente.
- Scopes mínimos para `inventory:read`, `products:read`, `categories:read`.
- Rate limiting.
- Audit log.
- Pagination/filtering.
- Tenant isolation.
- Documentación para el agente CRM IA.

Endpoints mínimos:

- `GET /api/v1/health/`
- `GET /api/v1/products/`
- `GET /api/v1/products/{id}/`
- `GET /api/v1/categories/`
- `GET /api/v1/inventory/`
- `GET /api/v1/inventory/low-stock/`
- `GET /api/v1/inventory/movements/`

El agente IA nunca accede directamente a PostgreSQL.

## Inventario: por cantidad y serializado

Incorporado oficialmente a partir de FASE 8. Todo producto declara un tipo de seguimiento de inventario:

- **QUANTITY** (por cantidad, por defecto): la fuente de verdad es `StockMovement`, un libro mayor append-only. El stock actual es el `stock_after` del movimiento más reciente — nunca un campo desnormalizado.
- **SERIALIZED** (IMEI / número de serie): la fuente de verdad es `InventoryUnit`, una fila por unidad física real. La disponibilidad es el conteo de unidades en estado EN_STOCK.

Un producto usa exactamente una de las dos fuentes a la vez; nunca deben coexistir dos fuentes de verdad contradictorias para el mismo producto, y un producto no puede cambiar de tipo si ya tiene historial registrado.

Unicidad de `serial`, `imei_1` e `imei_2` (modelo `InventoryUnit`): por tenant, no global, y solo entre valores no vacíos; `imei_1` nunca puede ser igual a `imei_2`; toda unidad requiere al menos un identificador no vacío.

Los endpoints de la API de Inventario (FASE 15) deben poder exponer también el inventario serializado, respetando el mismo principio read-only, de scopes y de aislamiento por tenant que el resto de la API. Ver `docs/inventory.md` para el diseño completo.

## Pagos y cuentas por cobrar

Incorporado oficialmente a partir de FASE 10 (ampliado tras el cierre inicial): `Payment` (dinero recibido de un cliente) puede aplicarse a una o varias facturas del mismo cliente mediante `PaymentAllocation`, un ledger append-only. El monto aplicado nunca excede el saldo disponible del pago ni el saldo pendiente de la factura; `Payment`/`Sale` deben ser del mismo tenant y, al aplicar, del mismo cliente; `Payment.customer` nulo (venta de mostrador) nunca genera saldo a favor. Todo se calcula desde el ledger, nunca un campo desnormalizado; toda operación es idempotente y auditada. Ver `docs/payments.md`.

Construido a partir de FASE 11 (`apps/pos`, `apps/approvals`) — ver `docs/accounts-receivable.md`, `docs/cash-registers.md` y `docs/approvals.md`:

- **Anticipo/saldo a favor**: un único saldo por cliente (nunca dos balances paralelos). No hay una tabla `CustomerCreditLedger` separada: se generalizaron `get_customer_credit_balance`/`get_sale_paid_amount` para sumar `Payment`+`PaymentAllocation` y `CreditNote`+`CreditNoteApplication` — los dos ledgers reales.
- **Notas de crédito** (`CreditNote`/`CreditNoteApplication`, en `apps.sales`): misma disciplina de validación que `PaymentAllocation`, nunca altera la factura histórica.
- **Cajas** (`CashRegister`/`CashSession`/`CashMovement`, en `apps.pos`): cualquier cantidad de cajas por tenant (sin límite fijo); una sesión de caja abierta es obligatoria antes de confirmar una venta operativa de mostrador; solo el efectivo afecta el efectivo físico.
- **Autorizaciones** (`ApprovalPolicy`/`ApprovalRequest`, en `apps.approvals`): servicio centralizado y reutilizable para descuentos por encima del límite (porcentaje Y monto) y crédito excedido, con jerarquía usuario → rol → tenant → negar. El propietario del tenant siempre está autorizado.

## PayPal

Implementar primero Sandbox. Consultar documentación oficial vigente para API y MCP. No inventar herramientas MCP ni endpoints. El frontend se comunica con Django; Django usa una capa de servicios de pago; MCP es herramienta del agente/desarrollo/operación.

## Integraciones: regla para usuario no técnico

Claude debe intentar automatizar la configuración. Cuando una acción dependa de una contraseña, credencial, cuenta externa, interfaz gráfica o permiso que no tenga, debe explicar exactamente qué hacer, dónde hacerlo, qué valor usar y cómo verificarlo. No debe asumir que pgAdmin se configura mágicamente. Debe leer y seguir `docs/setup/windows-postgresql-pgadmin-step-by-step.md` antes de configurar la base local.

## Verificación visual

Toda fase que cambie UI debe verificarse con navegador cuando sea posible, incluyendo estados normal, vacío, error y responsive.

## Estado

Mantener `docs/project-status/CURRENT_PHASE.md`, `PHASE_HISTORY.md`, `KNOWN_ISSUES.md` y `DECISIONS.md` actualizados.

## Primera ejecución

Ejecuta solamente FASE 0 y FASE 1. Luego detente. No continúes automáticamente.


## CONSTRUCCIÓN INCREMENTAL OBLIGATORIA

No generes todo el proyecto al inicio. En cada fase crea solo lo necesario para alcanzar los criterios de aceptación de esa fase y mantener las fases anteriores funcionando. No construyas placeholders de módulos futuros salvo que una dependencia inmediata lo requiera.

## PGADMIN 4 — ASISTENCIA PASO A PASO

No supongas que pgAdmin se conecta automáticamente. Antes de la FASE 2, lee `docs/setup/windows-postgresql-pgadmin-step-by-step.md`. Detecta PostgreSQL instalado, versión, servicio y puerto. Automatiza por terminal cuando sea seguro. Cuando se requiera contraseña, confirmación o interacción GUI, explica al usuario exactamente qué hacer en pgAdmin 4 y cómo verificarlo.

## PARADA POR CREDENCIALES

Si falta una credencial externa, no improvises. Explica: qué credencial es, dónde obtenerla, dónde introducirla, cómo protegerla y cómo verificar que funciona.
