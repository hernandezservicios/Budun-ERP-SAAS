# BUDUN ERP SAAS — ESPECIFICACIÓN OFICIAL DE FASES 0–24

> Documento maestro de alcance y arquitectura de fases.
> La numeración es fija: **FASE 0 a FASE 24**. No existe FASE 25.
> Cada fase se implementa, prueba, verifica, documenta, versiona y cierra antes de avanzar.

## Arquitectura oficial

### Desarrollo local
- Windows
- Python
- Django
- PostgreSQL 18
- pgAdmin 4
- Git/GitHub
- Sin Docker
- Sin MySQL
- Sin WAMP como dependencia

### Producción
- Hostinger VPS
- Linux
- Django
- PostgreSQL
- Gunicorn
- Nginx/servidor web apropiado
- SSL
- Variables de entorno
- Backups PostgreSQL
- Sin Docker como dependencia

### Regla de base de datos
PostgreSQL es la única base oficial. pgAdmin 4 administra/inspecciona PostgreSQL; no lo sustituye. Django Models + Migrations son la fuente de verdad de estructura.

## Reglas globales

Cada fase debe cumplir: implementación, tests, seguridad, Multi-Tenancy, PostgreSQL, regresión, performance cuando aplique, UX/UI cuando aplique, documentación, Git y verificación final. No saltar fases ni avanzar automáticamente.

Todo dato de negocio es tenant-scoped. Nunca confiar en `tenant_id` del frontend para autorizar. Nunca mostrar secretos. No usar `all_objects` directamente desde views/endpoints de forma insegura.

## Inventario — doctrina oficial

El inventario soporta dos tipos:

### QUANTITY
Fuente de verdad: `StockMovement`.

### SERIALIZED
Fuente de verdad: `InventoryUnit`.

No crear una tercera fuente de stock contradictoria.

Productos serializados soportan IMEI 1, IMEI 2 y Serial. Los identificadores actuales son únicos por tenant entre valores no vacíos, con IMEI 1 distinto de IMEI 2.

Estados de unidad: EN_STOCK, RESERVADO, VENDIDO, DEVUELTO, REPARACION, GARANTIA, DANADO, PERDIDO.

Búsqueda: nombre, SKU, barcode, QR como valor, IMEI 1, IMEI 2, serial e identificador de unidad.

## Pagos y cuentas por cobrar — doctrina oficial

`Payment` + `PaymentAllocation` soportan un pago aplicado a varias facturas, varios pagos a una factura, parciales, límites de aplicación, idempotencia, reversos y auditoría.

### Anticipo
Dinero recibido antes de una factura/venta definitiva.

### Saldo a favor
Crédito disponible del cliente que puede provenir de anticipo no aplicado, sobrepago, nota de crédito, refund convertido a crédito u otros movimientos autorizados.

Anticipo y saldo a favor no son dos balances independientes. El crédito debe ser trazable; no usar un saldo manual editable como fuente de verdad.

### Nota de crédito
Documento independiente aplicable parcial o totalmente a facturas futuras o pendientes; no modifica la factura histórica.

### Refund
Devolución de dinero, separada de devolución de mercancía, nota de crédito, anticipo y saldo a favor.

### Estado de cuenta
Debe poder mostrar facturas, pagos, asignaciones, anticipos, notas de crédito, refunds, reversiones, saldo pendiente y saldo a favor.

## Cajas — doctrina oficial

Una tienda/tenant puede tener cualquier cantidad de cajas/terminales.

Entidades: `CashRegister`, `CashSession`, `CashMovement`.

Reglas: un usuario no puede tener dos sesiones activas simultáneamente; una caja no puede tener dos sesiones activas simultáneamente salvo permiso explícito; apertura y cierre auditados; ventas operativas/POS que requieran caja no se confirman sin CashSession abierta; solo efectivo altera el efectivo físico.

## Autorizaciones — doctrina oficial

Sistema central: `ApprovalPolicy`, `ApprovalRequest`, `ApprovalService`.

Jerarquía: usuario específico -> rol -> tenant -> negar.

Descuentos: controlar por porcentaje y por monto. Si se supera cualquiera de los dos límites, se requiere autorización.

Crédito: si una venta a crédito supera límite, días o condiciones y el usuario no tiene permiso suficiente, se requiere autorización.

Registrar solicitante, aprobador, documento, valores, límite, motivo, estado y fechas.

# FASES OFICIALES

## FASE 0 — Auditoría del entorno
Verificar Windows, Python, pip, Git, Node/npm cuando aplique, PostgreSQL, servicio, puerto, pgAdmin 4 y herramientas. Confirmar no Docker/MySQL/WAMP. No construir negocio.

## FASE 1 — Project Foundation
Entorno virtual, Django, settings, `.env`, seguridad base, estructura, templates, tests, Git, documentación. Custom User preparado desde el inicio. Sin negocio.

## FASE 2 — PostgreSQL Foundation
Crear/verificar DB y usuario de aplicación, conexión Django->PostgreSQL, migrations, check, tests reales, smoke HTTP, verificación en pgAdmin y documentación.

## FASE 3 — Multi-Tenancy
Tenant, Membership, Custom User, Tenant Context, middleware, managers/querysets tenant-aware, permissions, services y tests de aislamiento A/B.

## FASE 4 — Authentication
Registro, login por email, logout, password reset/change, perfil, onboarding transaccional User+Tenant+Membership OWNER, Tenant Context. Preparar verificación de email, rate limiting y SMTP futuro.

## FASE 5 — Design System
Tokens, azul+verde+neutros, tipografía, spacing, buttons, inputs, selects, tables, cards, badges, alerts, modals, dropdowns, pagination, breadcrumbs, tabs, toasts, empty/loading/error, responsive y accesibilidad. Sin colores extraños ni efectos excesivos.

## FASE 6 — Landing + Pricing
Landing SaaS premium orientada a conversión, informativa, moderna y coherente con el Design System. Pricing centralizado/configurable. API/IA puede presentarse como próxima hasta su implementación.

## FASE 7 — Dashboard
Centro de control con encabezado, contexto, KPIs, tendencias, alertas, actividad y acciones rápidas. Datos reales, sin números inventados. Preparado para ventas, inventario, compras, gastos, clientes y reportes.

## FASE 8 — Products + Inventory
Categorías, productos, SKU, barcode, precios, impuestos, tracking QUANTITY/SERIALIZED, StockMovement, InventoryUnit, IMEI/serial, entradas, salidas, ajustes, stock, stock mínimo, búsqueda, estados, integridad, concurrencia y aislamiento. Preparar consumo por ventas/POS/compras/reportes/API.

## FASE 9 — Customers + Suppliers
Módulo profesional con personas/empresas, identificación fiscal extensible, contacto, dirección, datos comerciales, condiciones de pago, crédito preparado, documentos/archivos de hasta 10MB con validación y almacenamiento privado, historial, búsqueda, filtros, paginación, auditoría y aislamiento.

## FASE 10 — Sales + Quotations + Proformas + Invoices + Payments
Motor comercial central. Entidades independientes para cotización, proforma, venta/factura, pagos, PaymentAllocation, reservas, devoluciones, refunds, notas de crédito y aplicaciones. Snapshot histórico, numeración por tenant/serie, descuentos, impuestos, reservas, pagos parciales/múltiples, idempotencia, concurrencia y trazabilidad. Preparado para AR/AP, caja, POS y PayPal sin adelantar contabilidad/fiscalidad.

## FASE 11 — POS + Caja + Cobros + Autorizaciones
POS como capa de orquestación sobre FASE 10. Múltiples cajas por tenant, CashRegister/CashSession/CashMovement, apertura/cierre/conciliación, buscador profesional por nombre/SKU/barcode/QR/IMEI/serial, productos quantity y serialized, cobros de una o varias facturas, anticipos, saldo a favor, notas de crédito, refunds y ApprovalService para descuentos por porcentaje/monto y crédito excedido. Requiere caja abierta para ventas operativas de caja.

## FASE 12 — Purchases + Purchase Orders + Receiving + Costs + AP preparation
Órdenes de compra, recepciones parciales/completas, quantity/serialized, IMEI/serial en recepción, costos históricos, landed cost preparado, devoluciones a proveedor, documentos, approvals reutilizables, preparación de cuentas por pagar y anticipos a proveedores. El pago en efectivo desde caja requiere CashSession; otros medios no afectan efectivo físico. No contabilidad general todavía.

## FASE 13 — Expenses
Gastos profesionales con categorías, proveedor, documentos, monto, impuestos, método, fecha, estado, recurrencia futura, aprobaciones futuras, auditoría y relación con caja/pagos cuando corresponda.

## FASE 14 — Reports
Módulo completo de reportes de ventas, cotizaciones, compras, gastos, clientes, proveedores y cuentas. Incluir explícitamente **Reportes de Inventario**:
- existencias: stock actual, reservado, disponible, comprometido;
- productos por cantidad/serializados, activos/inactivos;
- bajo stock y agotados;
- movimientos: entradas, salidas, ajustes, devoluciones;
- serializados: IMEI, serial, estado, fecha, usuario, producto;
- trazabilidad completa de movimientos;
- valorización preparada;
- reportes de cajas: aperturas, cierres, ventas cash, entradas, salidas, refunds, sobrantes/faltantes;
- cuentas por cobrar: pendientes, pagos, allocations, anticipos, saldo a favor, notas de crédito, refunds, estado de cuenta y aging futuro;
- cuentas por pagar equivalentes.

## FASE 15 — Roles + Audit + Inventory API
Roles Super Admin, Tenant Owner, Manager, Cashier, Employee; permisos granulares; audit transversal; API de Inventario v1 con Base URL, API Key, generación/rotación/revocación, prueba/estado, health, products, categories, inventory, low-stock, movements y serializado según scopes. Read-only inicialmente; tenant isolation, rate limiting, audit, pagination, filtering.

## FASE 16 — PayPal Sandbox + PayPal MCP
Sandbox, Orders, Payments, Subscriptions cuando corresponda, webhooks, refunds, cancelación, idempotencia y reconciliación. Payment Service independiente de PayPal. MCP con documentación oficial vigente, sin inventar tools/args ni guardar secretos en código.

## FASE 17 — SaaS Billing
Billing de la suscripción del tenant, separado de AR/AP del ERP. Planes, trial, subscriptions, estados, PayPal, webhooks, cancelación y límites del plan.

## FASE 18 — Security Hardening
Auditoría completa de autenticación, autorización, CSRF, XSS, SQL injection, archivos, secrets, API, rate limiting, webhooks, PayPal, Multi-Tenant, approvals, caja, pagos, backups, logs, brute force y sesiones.

## FASE 19 — Performance
Optimización medida: N+1, índices, PostgreSQL, queries, paginación, caching, POS, búsqueda, reportes y API.

## FASE 20 — Backup & Recovery
pg_dump/pg_restore, backups programados, retención, verificación, restore test, backup de media y recuperación.

## FASE 21 — Hostinger Deployment
VPS, Linux, PostgreSQL, Python, Gunicorn, Nginx/servidor web, SSL, firewall, environment, static/media, logs, health checks y backups. Sin Docker. No runserver en producción.

## FASE 22 — Data Migration
pg_dump, transferencia, pg_restore, migrations, verificación, conteos e integridad para clientes, proveedores, productos, seriales, ventas, compras y documentos.

## FASE 23 — Production Verification
Dominio, HTTPS, login, Multi-Tenant, dashboard, POS, cajas, ventas, cotizaciones, proformas, facturas, pagos, devoluciones, inventario, seriales, compras, gastos, reportes, API, PayPal, Billing, backups y seguridad.

## FASE 24 — Final Audit
Auditoría final de arquitectura, seguridad, Multi-Tenant, PostgreSQL, Django, inventario, serialización, POS, caja, compras, ventas, AR/AP, API, PayPal, Billing, backups, UX, accesibilidad, performance, documentación, Git y deployment. Generar `FINAL_PROJECT_AUDIT.md`. Solo después: PROJECT COMPLETE.

# REGLA FINAL

Este documento define el roadmap oficial. Las fases son exactamente 0–24. Una nueva decisión debe actualizar los `.md` relevantes antes de implementar la fase afectada. No se debe construir una segunda fuente de verdad para inventario, pagos, crédito, caja o aprobaciones si ya existe un dominio aprobado.
