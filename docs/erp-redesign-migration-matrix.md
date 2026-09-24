# ERP REDESIGN — MIGRATION MATRIX (FASE 5 — CERRADA / APROBADA)

Las 13 familias maestras están `VERIFICADA` (implementadas en Etapas
1-3C, auditadas visualmente a nivel de código en ETAPA 4 — QA sin
regresiones — y reconfirmadas en el cierre de ETAPA 5, ver
`docs/erp-redesign-implementation-plan.md` §20 y §21). Ver ese mismo
documento para el detalle completo de cada fila (riesgos,
dependencias, componentes reutilizables).

| Pantalla | Ruta | Template | View | Modelo | Stitch | Componentes | Riesgo | Estado |
|---|---|---|---|---|---|---|---|---|
| Shell | (global, todas las rutas) | `templates/layout_app.html` | — | — | Panel — Móvil (`6ed6aa54e5b74dbb924da664f1e60215`) | Sidebar, Topbar | ALTO | VERIFICADA |
| Dashboard | `dashboard:panel` | `apps/dashboard/templates/dashboard/panel.html` | `DashboardView` | `Membership`, `Product` | Panel — Escritorio (`c9f884fd30a74aa982b1d1d09998d76d`) | KpiCards, Cards, Alerts, Buttons | BAJO | VERIFICADA |
| List (Ventas) | `sales:sale_list` | `apps/sales/templates/sales/sale_list.html` | `SaleListView` | `Sale` | Ventas — Escritorio (`02e8d0ac82734bce9af4c1c97f38fa4f`) | TableStandard, Badges, Buttons, Pagination | BAJO | VERIFICADA |
| Detail (Venta) | `sales:sale_detail` | `apps/sales/templates/sales/sale_detail.html` | `SaleDetailView` | `Sale`, `SaleItem`, `PaymentAllocation`, `SalesDocumentAttachment` | Detalle de Venta — Escritorio (`e4b1d1ac48a74521bcff580bf8ddb08f`) | Breadcrumbs, Tabs, TableFinancial, Badges, Buttons | MEDIO | VERIFICADA |
| Form (Gasto) | `expenses:expense_create` | `apps/expenses/templates/expenses/expense_form.html` | `ExpenseCreateView` | `Expense`, `ExpenseCategory` | Nuevo gasto — Escritorio (`aeb1993f4c3b4ec0956aeddb794912dd`) | FormFields, FormLayout, Buttons | BAJO | VERIFICADA |
| Finance (Cobrar) | `pos:customer_collections` | `apps/pos/templates/pos/customer_collections.html` | `CustomerCollectionsView` + 5 | `Sale`, `Payment`, `PaymentAllocation`, `CreditNote` | Cobrar — Escritorio (`335527c381044431a12953e2828d55a3`) | FormControls, TableStandard, Badges, Buttons | ALTO | VERIFICADA |
| Inventory | `inventory:product_list` | `apps/inventory/templates/inventory/product_list.html` (+ kardex en `product_detail.html`) | `ProductListView`, `ProductDetailView` | `Product`, `Category`, `StockMovement` | Inventario — Escritorio (`553fe2a34e57418290df296b18a75c9a`) | TableStandard, TableFinancial, Badges | BAJO | VERIFICADA |
| Sales (Cotizaciones) | `sales:quotation_list` | `apps/sales/templates/sales/quotation_list.html` | `QuotationListView` | `Quotation` | Cotizaciones — Escritorio (`ae13424e64b5460ab9a2e25de1049099`) | TableStandard, Badges, Buttons | BAJO | VERIFICADA |
| Purchases | `purchases:purchase_order_list` | `apps/purchases/templates/purchases/purchase_order_list.html` (+ `purchase_order_detail.html`) | `PurchaseOrderListView`, `PurchaseOrderDetailView` | `PurchaseOrder`, `PurchaseOrderItem`, `PurchaseReceiptItem` | Compras — Escritorio (`1925f3f08c95454b9ddad749a8b56f43`) | TableStandard, Badges — **ProgressBar NO implementado, ver plan §18** | MEDIO | VERIFICADA (sin barra de progreso — ver discrepancia) |
| HR/Payroll | `hr:employee_detail` | `apps/hr/templates/hr/employee_detail.html` (+ `apps/payroll/templates/payroll/payroll_detail.html`) | `EmployeeDetailView`/`EmployeeEditView` | `Employee`, `EmploymentContract`, `PayrollLine` | Detalle de empleado — Escritorio (`506ef2dddb1444e49a489e2e478570e8`) | Tabs, TableFinancial, Badges, campo oculto por permiso | MEDIO | VERIFICADA |
| Reports | `reports:sales` | `apps/reports/templates/reports/sales_report.html` | `SalesReportView` | `Sale` (agregados) | Reporte de ventas — Escritorio (`3d24d005fd014b83b647eb2cb9a5efac`) | TableStandard (KPI summary como tabla, sin convertir a KpiCards), Buttons de exportación | BAJO | VERIFICADA |
| Configuration | `core:settings` + `api_config:config` | `apps/core/templates/core/settings_home.html` + `apps/api/templates/api/config.html` | `SettingsHomeView`; `ApiKeyConfigView`+5 | `ApiKey` | Configuración — Escritorio (`9f5f8bfd92194724bfc44c467c4e6383`) | Cards (hub, grilla responsive), Badges, código enmascarado (`.u-cifra`), Buttons | BAJO | VERIFICADA |
| Approvals | `approvals:pending_list` | `apps/approvals/templates/approvals/pending_list.html` | `PendingApprovalsView`, `ApprovalResolveView` | `ApprovalRequest` | Autorizaciones pendientes — Escritorio (`43185f44d57443b2a0be66cd32622a8d`) | TableStandard, Badges, Buttons | BAJO | VERIFICADA |
