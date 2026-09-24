# ERP STITCH SCREEN MAP (FASE 4)

Matriz de trazabilidad de las 13 pantallas maestras congeladas en Stitch.
Cada fila conecta la pantalla real de Django (verdad funcional), el
registro en `docs/erp-redesign-map.md` (verdad de contenido), el patrón
visual de `docs/erp-redesign-design-system.md` (lenguaje Atlas) y la
decisión correspondiente del `docs/erp-redesign-design-lab-decision-log.md`
cuando aplica.

**Proyecto Stitch**: "Budun ERP — Atlas", `projects/8973448531701085715`.
**Design systems**: "Atlas — Día" (`assets/8315432074048865179`, usado en
las 13 pantallas) y "Atlas — Noche" (`assets/14852482893901083698`, creado
y listo para aplicar en FASE 5/7 — no usado todavía en las pantallas
maestras, ver Notas). Cada pantalla es recuperable con `get_screen` sobre
su `name` completo (`projects/8973448531701085715/screens/<id>`).

Ningún archivo del ERP productivo fue modificado para producir esta
matriz ni las pantallas de Stitch.

| # | Pantalla real (Django) | Pantalla Stitch (id) | Fuente funcional | Patrón visual | Componentes | Estados representados |
|---|---|---|---|---|---|---|
| 01 | Shell — `layout_app.html` (móvil) | Panel — Móvil · `6ed6aa54e5b74dbb924da664f1e60215` | ERP MAP §01 Arquitectura, §04 Pantallas (Dashboard) | Navigation (responsive off-canvas) | Topbar, KPI Cards, Cards, Badges | — (chrome únicamente) |
| 02 | Shell + `dashboard:panel` (escritorio) | Panel — Escritorio · `c9f884fd30a74aa982b1d1d09998d76d` | ERP MAP §02 Módulos (21/8 grupos), §04 Dashboard | Navigation, Dashboard | Sidebar, Topbar, KPI Cards, Cards, Buttons | — |
| 03 | `sales:sale_list` | Ventas — Escritorio · `02e8d0ac82734bce9af4c1c97f38fa4f` | ERP MAP §04 Pantallas, §08 Tablas (Ventas) | Table (List) | TableStandard, Badges, Buttons, Pagination | Pagada (success), Pendiente (warning), Borrador (neutral) |
| 04 | `sales:sale_detail` | Detalle de Venta — Escritorio · `e4b1d1ac48a74521bcff580bf8ddb08f` | ERP MAP §04-05 (Venta: líneas/pagos/documentos/actividad) | Detail view | Breadcrumbs, Badges, Tabs, TableFinancial, Buttons | Pagada (success) |
| 05 | `expenses:expense_create` | Nuevo gasto — Escritorio · `aeb1993f4c3b4ec0956aeddb794912dd` | ERP MAP §07 Formularios (Gasto: Categoría/Proveedor/Fecha/Monto/Descripción/Frecuencia) | Form (sectioned) | FormFields, FormLayout, Buttons | — |
| 06 | `pos:customer_collections` | Cobrar — Escritorio · `335527c381044431a12953e2828d55a3` | ERP MAP §12 POS (Cobros de cliente, selección múltiple de facturas) | Finance | FormControls (checkbox), TableStandard, Badges, Buttons | Pendiente (warning), Vencida (danger) |
| 07 | `inventory:product_list` + `StockMovement` | Inventario — Escritorio · `553fe2a34e57418290df296b18a75c9a` | ERP MAP §04 Inventario, doctrina QUANTITY/SERIALIZED | Table (List) + Table (Financial/dense) | TableStandard, TableFinancial, Badges | Stock bajo (warning), Activo (success), Cantidad/Serializado (neutral/info) |
| 08 | `sales:quotation_list` | Cotizaciones — Escritorio · `ae13424e64b5460ab9a2e25de1049099` | ERP MAP §04 Cotizaciones — escalado del patrón List/Badges a otro dominio Comercial | Table (List), Lista→Detalle→Acciones | TableStandard, Badges, Buttons | Enviada (info), Aceptada (success), Rechazada (danger) |
| 09 | `purchases:purchase_order_list` | Compras — Escritorio · `1925f3f08c95454b9ddad749a8b56f43` | ERP MAP §04 Compras, doctrina de recepción agregada (nunca campo desnormalizado) | Table (List) + **Progress bar (nuevo)** | TableStandard, Badges, **ProgressBar** | Recibida (success), Enviada (info), Borrador (neutral) |
| 10 | `hr:employee_detail` + `payroll` (línea de nómina) | Detalle de empleado — Escritorio · `506ef2dddb1444e49a489e2e478570e8` | ERP MAP §04 RRHH/Nómina, `can_view_sensitive_employee_data` | Detail view + gating de sensibles | Tabs, TableFinancial, Badges, **campo oculto por permiso** | Activo (success), Procesando (info), Ingreso/Deducción (success/danger) |
| 11 | `reports:sales_report` | Reporte de ventas — Escritorio · `3d24d005fd014b83b647eb2cb9a5efac` | ERP MAP §11 Reportes (único con exportación CSV+PDF+XLSX completa) | Reports | KpiCards, TableStandard, Badges, export Buttons | Pagada (success) |
| 12 | `core:settings` + `api_config:config` | Configuración — Escritorio · `9f5f8bfd92194724bfc44c467c4e6383` | ERP MAP §13 Integraciones (patrón "secreto mostrado una vez") | Configuration | Cards (hub), Badges, código enmascarado, Buttons | Activa (success) |
| 13 | `approvals:pending_list` | Autorizaciones pendientes — Escritorio · `43185f44d57443b2a0be66cd32622a8d` | ERP MAP §10 Permisos / Autorizaciones (jerarquía usuario→rol→tenant→negar) | Approvals | TableStandard, Badges, Buttons | Pendiente (warning) |

## Notas de fidelidad de color (Stitch vs. especificación)

Stitch genera su paleta con un motor de color dinámico (Material) a
partir de un color semilla (`customColor`) — no reproduce un hexadecimal
literal pixel a pixel incluso con `colorVariant: FIDELITY` (la opción
más fiel disponible; se probó primero `NEUTRAL`, que desaturaba el azul
casi a gris, y se corrigió). El resultado real que Stitch produjo y
aplicó de forma consistente en las 13 pantallas es un azul `#325f9b`
(primary) / `#4d78b6` (primary-container) — visualmente fiel a la
familia de "azul profundo institucional" del spec, pero no el hex exacto
`#1D4E89`. **La implementación real en Django (FASE 5) debe usar los
valores exactos de `docs/erp-redesign-design-system.md`**, tomando las
pantallas de Stitch como referencia de composición/jerarquía/densidad,
nunca como fuente de verdad del valor hexadecimal.

Por la misma razón, la familia tipográfica de datos (IBM Plex Mono) no
existe como opción en el picker de fuentes de Stitch — se configuró
`labelFont: GOOGLE_SANS_MONO` como sustituto más cercano sin colisionar
con JetBrains Mono (la mono del SaaS), pero Stitch internamente la
reemplazó por Public Sans en varias generaciones (limitación confirmada
de la herramienta, no una decisión de diseño). **La implementación real
usa IBM Plex Mono tal como especifica Atlas**, sin excepción.

`download_assets` no produjo archivos locales en este entorno (limitación
de la herramienta en esta sesión) — las 13 pantallas permanecen accesibles
mediante `get_screen`/`list_screens` sobre el proyecto Stitch
`projects/8973448531701085715` en cualquier sesión con acceso al MCP de
Stitch.

## Cobertura de estados (sección 15 de la fase)

Representados porque son reales y aparecen en alguna pantalla maestra:
loading (no aplicable a ninguna maestra — se cubrió en el Lab, sección
15, no se repite aquí), empty/no-results (cubiertos en el Lab, no
re-generados como pantalla Stitch dedicada por ser exploración ya
congelada visualmente sin variación adicional), forbidden/error (ídem),
success/warning (badges en Ventas, Cotizaciones, Cobrar, Compras,
Autorizaciones), confirmation (ninguna pantalla real del ERP usa un
diálogo de confirmación aparte — las confirmaciones son `confirm()`
nativo, documentado en ERP MAP §09; Stitch no genera JS, por lo que este
comportamiento se preserva como nota funcional para FASE 5, no como
pantalla visual).
