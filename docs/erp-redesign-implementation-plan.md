# ERP REDESIGN — IMPLEMENTATION PLAN (FASE 5, ETAPA 0)

Auditoría de solo lectura del ERP Django real, a nivel de archivo, para
planificar cómo se traslada Atlas (`docs/erp-redesign-design-system.md`)
a producción sin alterar funcionalidad. Ningún archivo del ERP fue
modificado para producir este documento — auditoría vía lectura directa
de `static/css/base.css`, `static/js/ui.js`, `templates/layout_app.html`,
`apps/customers/templates/customers/_campo.html`, más 4 sub-agentes de
solo lectura para el resto de las 13 pantallas maestras.

---

## 1. Estado actual

El ERP ya tiene un Design System propio (FASE 5 original, antes de este
rediseño): `static/css/base.css` (tokens) + `static/css/design-system.css`
(componentes + shell) + `static/js/ui.js` (comportamiento). Es el **mismo
archivo físico** que usa hoy el Super Admin SaaS (con overrides
`.shell--saas`, ~2999 líneas en total, la mayoría del archivo dominada
por reglas `.shell--saas`). El ERP tenant usa las reglas **sin
prefijo** (`.shell`, `.sidebar`, `.btn`, `.campo`, `.tarjeta`, `.badge`,
`.tabla`, etc.) — nunca las `.shell--saas`. Esto confirma exactamente el
riesgo ya identificado en FASE 1 (Discovery, sección 17): cualquier
cambio a estos dos archivos compartidos puede afectar visualmente al
Super Admin SaaS ya aprobado, y viceversa.

No existe ningún sistema de tema oscuro en el código (confirmado por
grep: cero coincidencias de `[data-theme]` o de un color-scheme
condicional en `base.css`/`design-system.css`/`ui.js`) — el Modo Noche de
Atlas es 100% nuevo, consistente con el hallazgo de Discovery.

## 2. Arquitectura encontrada

- **Shell real**: `templates/layout_app.html` — grid CSS de dos columnas
  (`.shell { grid-template-columns: var(--ancho-sidebar) 1fr; grid-template-areas: "sidebar navbar" "sidebar main"; }`),
  sidebar `240px` fijo (`--ancho-sidebar`), navbar `60px`
  (`--alto-navbar`). El sidebar es una **lista plana sin agrupar**
  (`<ul class="sidebar__nav">` con 21 `<li>` directos, cada uno con su
  propia condición `aria-current` basada en `request.resolver_match`) —
  confirma que la agrupación en 8 dominios de Atlas es un cambio
  estructural de plantilla real, no solo CSS.
- **Responsive real**: `≤1024px` el sidebar pasa a `position:fixed` fuera
  de pantalla (`inset:0 25% 0 0; transform:translateX(-100%)`), activado
  por `.shell.sidebar-abierto` (clase que alterna `data-sidebar-toggle`
  vía `ui.js`); `≤640px` el sidebar ocupa `inset:0 15% 0 0` y `.main`
  reduce su padding. Sin breakpoint de tablet propio distinto del de
  móvil — un solo salto a off-canvas en 1024px.
- **JS real** (`static/js/ui.js`, progressive enhancement por
  `data-*`, sin build step, sin framework): `initSidebar` (off-canvas),
  `initSidebarAnchoToggle` (**exclusivo `.shell--saas`**, no aplica al
  ERP), `initDropdowns` (`data-dropdown`), `initModals`
  (`data-modal-open`/`dialog.modal` — sin ningún uso real en plantillas
  del ERP tenant, confirmado en FASE 1), `initTabs` (`data-tabs`, con
  navegación por flechas), `initToasts`, `initAutoGrowTextareas`
  (**exclusivo `.shell--saas`**). El ERP tenant es 100% server-rendered
  full-page POST+redirect — cero AJAX/fetch en cualquiera de las 13
  pantallas maestras auditadas.
- **Tokens reales** (`static/css/base.css`): ver mapeo completo en
  sección 5.

## 3. Mapa pantalla → código (13 pantallas maestras)

| # | Maestra Stitch | Ruta real | Template | View | Form | Modelos |
|---|---|---|---|---|---|---|
| 01 | Shell | (chrome global) | `templates/layout_app.html` | — (incluido por cada vista vía `{% extends %}`) | — | — |
| 02 | Dashboard | `dashboard:panel` | `apps/dashboard/templates/dashboard/panel.html` | `DashboardView` (`apps/dashboard/views.py`) | — | `Membership`, `Product` (vía `apps.dashboard.services.obtener_datos_del_panel`) |
| 03 | List | `sales:sale_list` | `apps/sales/templates/sales/sale_list.html` | `SaleListView` | — (GET crudo) | `Sale` |
| 04 | Detail | `sales:sale_detail` | `apps/sales/templates/sales/sale_detail.html` | `SaleDetailView` | `SaleItemForm`, `PaymentForm`, `SalesAttachmentForm` | `Sale`, `SaleItem`, `PaymentAllocation`, `SalesDocumentAttachment`, `SalesActivityLog`, `Return` |
| 05 | Form | `expenses:expense_create` | `apps/expenses/templates/expenses/expense_form.html` | `ExpenseCreateView` | `ExpenseForm` (13 campos) | `Expense`, `ExpenseCategory` |
| 06 | Finance | `pos:customer_collections` | `apps/pos/templates/pos/customer_collections.html` | `CustomerCollectionsView` + 5 vistas de acción | `CollectPaymentForm`, `CustomerAdvanceForm`, `ApplyCreditForm`, `IssueCreditNoteForm`, `RefundForm` | `Sale`, `Payment`, `PaymentAllocation`, `CreditNote`, `CreditNoteApplication`, `Customer` |
| 07 | Inventory | `inventory:product_list` (+ kardex en `product_detail`) | `apps/inventory/templates/inventory/product_list.html` + `product_detail.html` | `ProductListView`, `ProductDetailView` | — (GET crudo) | `Product`, `Category`, `StockMovement` |
| 08 | Sales | `sales:quotation_list` | `apps/sales/templates/sales/quotation_list.html` | `QuotationListView` | — (GET crudo) | `Quotation` |
| 09 | Purchases | `purchases:purchase_order_list` (+ detalle) | `apps/purchases/templates/purchases/purchase_order_list.html` + `purchase_order_detail.html` | `PurchaseOrderListView`, `PurchaseOrderDetailView` | `PurchaseOrderItemForm`, etc. | `PurchaseOrder`, `PurchaseOrderItem`, `PurchaseReceiptItem` |
| 10 | HR/Payroll | `hr:employee_detail` (+ `payroll_detail`) | `apps/hr/templates/hr/employee_detail.html` + `apps/payroll/templates/payroll/payroll_detail.html` | `EmployeeDetailView`/`EmployeeEditView`; vista de nómina | `EmployeeForm` + 6 más; — | `Employee`, `EmploymentContract`, `PayrollLine` |
| 11 | Reports | `reports:sales` | `apps/reports/templates/reports/sales_report.html` | `SalesReportView` | `SalesReportFilterForm` | `Sale` (agregados) |
| 12 | Configuration | `core:settings` + `api_config:config` | `apps/core/templates/core/settings_home.html` + `apps/api/templates/api/config.html` | `SettingsHomeView`; `ApiKeyConfigView`+5 | — | `ApiKey` |
| 13 | Approvals | `approvals:pending_list` | `apps/approvals/templates/approvals/pending_list.html` | `PendingApprovalsView`, `ApprovalResolveView` | `ResolveApprovalForm` | `ApprovalRequest` |

Detalle de dificultad, permisos y dependencia funcional exacta de cada
una está en `docs/erp-redesign-migration-matrix.md`.

## 4. Componentes reutilizables identificados (sin crear nada todavía)

| Clase CSS real hoy | Componente Atlas equivalente | Migración |
|---|---|---|
| `.shell`/`.sidebar`/`.navbar`/`.main` (grid) | Sidebar + Topbar | **Estructural**: `layout_app.html` necesita agrupar los 21 `<li>` en 8 `<div class="sidebar__grupo">` — cambio de plantilla real, no solo CSS |
| `.btn` + `--primario`/`--secundario`/`--contorno`/`--fantasma`/`--peligro`/`--sm`/`--lg`/`--bloque`/`--cargando` | Buttons | Directo — mismos 9 modificadores que ya define Atlas, solo re-skin de valores |
| `.campo` (vía `_campo.html`) | FormFields | Directo |
| `.tarjeta` | Cards | Directo |
| `.badge` + `--verde`/`--neutro`/`--azul`/`--advertencia`/`--peligro` | Badges | Directo — 5 colores semánticos ya existen |
| `.alerta` + `--info`/`--exito`/`--advertencia`/`--peligro` | Alerts | Directo |
| `.tabla-envoltorio`/`.tabla` | TableStandard | Directo |
| — (no existe variante densa) | TableFinancial | **Nuevo modificador** `.tabla--densa` (o equivalente) — ningún componente de tabla densa existe hoy |
| `.paginacion` | Paginación (parte de Tables) | Directo |
| `.dropdown` | Menú de usuario (Topbar) | Directo |
| `.estado-vacio` (+ícono emoji) | PageStates (empty) | Requiere reemplazar emoji por ícono SVG de línea en **cada** plantilla que lo usa (decenas) — contenido, no solo CSS |
| `.kpi-grid`/`.kpi` | KpiCards | Directo, pero sin fuente monoespaciada tabular hoy — se agrega en CSS |
| `.migas` | Breadcrumbs | Directo |
| `.encabezado-pagina` | Page header | Directo |
| `data-tabs`/`[role=tab]` (JS ya en `ui.js`) | Tabs | **JS se reutiliza sin cambios** — la lógica ARIA ya es correcta; solo CSS |
| — | Modal | No aplica — Atlas (FASE 2) no introduce modales en el ERP, consistente con que ninguna pantalla real los usa hoy |
| — | Progress bar (Recepción, aprobado FASE 4) | **Nuevo** — ver sección 9 |

## 5. Design tokens — Atlas → CSS Django

| Token Atlas | Valor Atlas | Token real hoy (`base.css`) | Acción |
|---|---|---|---|
| `radius-sm`/`md`/`lg`/`pill` | 4/6/10/999px | `--radio-sm`/`md`/`lg`/`completo` = **4/6/10/999px** | **Ya coincide exactamente** — no requiere ningún token nuevo, se hereda tal cual |
| `space-1..9` | 4/8/12/16/20/24/32/40/48px | `--espacio-1..12` = 4/8/12/16/20/24/32/40/48px (mismos saltos, distinta numeración de índice) | Se hereda tal cual — no crear una escala paralela |
| `space-10` | 64px | No existe ningún paso de 64px hoy | Único paso nuevo a agregar si se necesita |
| `shadow-sm`/`md` | 2 niveles | `--sombra-sm`/`md`/`lg` (3 niveles) | Se heredan `--sombra-sm`/`md` tal cual; `--sombra-lg` queda sin uso por Atlas (reservado) |
| `primary` | `#1D4E89` | `--color-primario` = `--color-azul-700` = `#1d4ed8` | **Requiere override** — es el único valor de identidad que realmente difiere |
| tipografía | IBM Plex Sans + IBM Plex Mono | `--fuente-base`: system-ui (sin mono dedicada) | **Requiere override** + `<link>` de Google Fonts nuevo |
| resto de color (success/warning/danger/neutral/superficies/texto) | valores Atlas exactos | `--color-verde-*`/`--color-peligro-*`/`--color-advertencia-*`/`--gris-*` (paleta distinta) | **Requiere override** — reemplazo completo de la paleta cromática, radio/spacing/sombra se heredan |

**Estrategia recomendada** (misma ya usada por el Super Admin SaaS para
su propio aislamiento, mismo archivo, mismo patrón): un archivo nuevo
`static/css/design-system-erp.css`, cargado solo por `layout_app.html`,
que define un bloque `.shell--erp { --color-primario: #1D4E89; ... }`
— redeclarando únicamente color y tipografía (lo que realmente cambia),
nunca tocando `:root` en `base.css` (compartido con el SaaS) ni
redeclarando radio/spacing/sombra (que ya coinciden). Esto es
exactamente la misma técnica de aislamiento que `.shell--saas` ya usa
hoy en el mismo archivo compartido — sin inventar un patrón nuevo.

## 6. Modo Día / Modo Noche

No existe ningún soporte de tema hoy — ni `data-theme`, ni clases, ni
`prefers-color-scheme` para color, ni persistencia, ni detección del
sistema (confirmado por grep en los 3 archivos base). Implementarlo
requiere: (1) duplicar el bloque de tokens de color bajo un selector
`.shell--erp[data-theme="noche"]` (mismo patrón `.shell--saas` +
atributo que ya usa el toggle de ancho del sidebar SaaS,
`data-sidebar-modo`, como precedente real de un atributo persistido en
`localStorage` vía `ui.js`), (2) un botón de alternancia nuevo + una
función `initTemaToggle()` en `ui.js` siguiendo el mismo patrón exacto
de `initSidebarAnchoToggle` (persistencia en `localStorage`, aplicación
vía atributo). No se implementa en esta etapa — el Modo Noche del POS
específicamente queda fuera de FASE 5 por instrucción explícita.

## 7. Responsive

Lo que ya existe y debe conservarse: el mecanismo off-canvas completo
(`.shell.sidebar-abierto`, `data-sidebar-toggle`/`data-sidebar-backdrop`,
transición `transform`), el único breakpoint real de colapso (1024px) y
el ajuste secundario de 640px. Lo que Atlas necesita adaptar:
reagrupación del sidebar en 8 grupos también en el estado off-canvas
(mismo mecanismo, más contenido), y el tratamiento de tablas/formularios
en pantallas angostas (hoy sin un patrón explícito de "colapsar
columnas" — las tablas dependen únicamente de `.tabla-envoltorio{overflow-x:auto}`
para no romper el layout, sin una versión "tarjeta por fila" en móvil).
No se implementa en esta etapa.

## 8. Funcionalidad que no debe romperse (por módulo, confirmada a nivel de código)

- **Dashboard**: las 2 KPI placeholder ("Ventas del mes"/"Gastos del
  mes" = `"—"`) y los 2 botones deshabilitados ("Agregar producto"/
  "Registrar venta") están hardcodeados en `services.py`/`panel.html`
  con ayuda textual explícita ("Se activará con el módulo de...") — la
  migración visual **debe preservar este estado placeholder tal cual**,
  nunca "arreglarlo" activándolo silenciosamente (sería una
  funcionalidad nueva, no una migración visual).
- **Ventas (List/Detail)**: `apps/sales/views.py` no usa
  `PermissionRequiredMixin` en ninguna vista (solo `LoginRequiredMixin`+
  `TenantRequiredMixin`) — la migración no debe agregar ni quitar
  gating de permisos, solo reestilizar. Los 3 `confirm()` reales
  (Confirmar venta, Cancelar venta, Revertir pago) deben preservarse
  exactamente, con el mismo texto.
- **Gastos (Form)**: los 13 campos exactos de `ExpenseForm` en el mismo
  orden — la migración a 2 columnas/secciones (decisión ya congelada en
  FASE 4) reorganiza visualmente, nunca agrega/quita un campo.
- **Cobros (Finance)**: la distribución de pago tipo "cascada" (el monto
  único se reparte entre las facturas marcadas, en orden de queryset,
  hasta agotarse) y la aplicación de saldo a favor hardcodeada a la
  factura más antigua (`pending_sales.0`) son comportamientos reales que
  la migración visual **nunca debe alterar** — son candidatos a mejora
  funcional futura (selector de factura, montos editables por fila),
  pero eso es una decisión de producto fuera de esta fase, no una
  consecuencia del rediseño visual.
- **Inventario**: el kardex real tiene 7 columnas (Fecha/Tipo/Cantidad/
  Stock anterior/Stock posterior/Usuario/Notas) — más columnas que la
  versión simplificada de 4 columnas usada en el Lab/Stitch (ver
  discrepancia, sección 9 de este documento en conjunto con el screen
  map) — la implementación real debe mostrar las 7 columnas reales,
  nunca recortar a las 4 de la referencia visual.
- **Compras**: ningún dato de recepción por orden (agregado/porcentaje)
  existe hoy — ver sección 9, crítico.
- **RRHH**: el gate de datos sensibles es servidor (`puede_ver_sensible`
  controla tanto el bloque de datos como si `edit_form` existe;
  `EmployeeEditView.post()` lanza `PermissionDenied` si se intenta
  igual) — la migración solo cambia CÓMO se muestra "oculto" (de un
  `.alerta.alerta--info` de texto a un ícono de candado, patrón
  aprobado en FASE 4), nunca la lógica de permiso subyacente. Las 7
  pestañas reales (Datos/Contratos/Documentos/Asistencia/Ausencias/
  Incidentes/Actividad) deben preservarse todas — la referencia visual
  simplificaba a 4.
- **Reportes**: los botones de exportación son enlaces GET simples
  (`?...&export=csv|pdf|xlsx`) manejados por la misma vista — la
  migración no debe convertirlos en botones JS/POST sin necesidad.
- **Configuración**: "Revocar" es la única acción con `confirm()` hoy
  (Rotar y Probar conexión no lo tienen) — preservar exactamente esa
  asimetría.
- **Autorizaciones**: Aprobar/Rechazar son dos `<form>` HTML separados
  (no un solo formulario con radio/select), ninguno con `confirm()` —
  preservar ambos hechos exactamente.

## 9. Componente — Progress / Receipt Progress (Compras)

Hallazgo crítico de la auditoría, exactamente el tipo de caso que pide
"documentar, no inventar" (instrucción §9): **no existe ningún dato de
recepción a nivel de orden completa hoy.** Lo que sí existe:

- `apps.purchases.services.get_purchase_order_item_received_quantity(item)`
  — recibido de UNA línea (agrega sobre `PurchaseReceiptItem`).
- `apps.purchases.services.get_purchase_order_item_pending_quantity(item)`
  — pendiente de una línea.
- `apps.purchases.services.get_purchase_order_items_received_bulk(items)`
  — recibido de VARIAS líneas en una sola consulta (`{item.pk: recibido}`),
  ya usado hoy en `PurchaseOrderDetailView` para mostrar Recibido/
  Pendiente por línea como texto plano (sin barra, sin porcentaje).

Lo que **no existe y debe construirse** para alimentar la barra de
progreso aprobada: un agregado a nivel de ORDEN completa (suma de
recibido / suma de pedido × 100), en ningún lugar del código hoy —
tampoco en el listado (`purchase_order_list.html` no toca
`PurchaseReceiptItem` en absoluto). Esto significa que implementar la
barra de progreso en el listado de Compras no es un cambio puramente
visual: requiere una función de servicio nueva y aditiva (ej.
`get_purchase_order_received_percent(order)`), construida sobre las
funciones ya existentes y ya probadas para el detalle — **sin modelo
nuevo, sin migración, sin campo desnormalizado**, pura agregación de
lectura. Se documenta aquí para tu aprobación explícita en Etapa 1;
no se implementa en esta etapa.

## 10. Riesgos

| Pantalla | Riesgo | Razón |
|---|---|---|
| 01 Shell | **ALTO** | Cambio principalmente visual, pero de radio de impacto máximo — toca la única plantilla que envuelve las 21 rutas del ERP; requiere reestructurar el `<ul>` plano en 8 grupos sin romper ninguna condición `aria-current` existente |
| 02 Dashboard | BAJO | Pantalla aislada, sin interacción JS propia, sin acciones destructivas |
| 03 List (Ventas) | BAJO | Solo lectura + filtros GET, sin JS propio |
| 04 Detail (Venta) | **MEDIO** | 5 pestañas reales + 3 formularios de sub-acción + 3 `confirm()` — más superficie de interacción que el resto |
| 05 Form (Gasto) | BAJO | Formulario plano de un solo POST, sin JS propio |
| 06 Finance (Cobrar) | **ALTO** | Lógica financiera real (distribución en cascada, aplicación de saldo hardcodeada, 5 sub-acciones) — mayor riesgo de alterar comportamiento sin querer al reestructurar el layout |
| 07 Inventory | BAJO | Listado + kardex de solo lectura |
| 08 Sales (Cotizaciones) | BAJO | Mismo patrón que List, un solo color de badge hoy (discrepancia menor, ver Screen Map) |
| 09 Purchases | **MEDIO** | Visualmente similar a List, pero requiere la función de servicio nueva de la sección 9 antes de poder mostrar el componente aprobado |
| 10 HR/Payroll | **MEDIO** | Gating de datos sensibles servidor+plantilla en dos patrones distintos (HR vs. Payroll) que deben unificarse visualmente sin tocar ninguno de los dos gates reales |
| 11 Reports | BAJO | Filtros GET + tabla de solo lectura; exportación ya es un enlace simple |
| 12 Configuration | BAJO | Hub de navegación + una tarjeta de acciones simples |
| 13 Approvals | BAJO | Dos formularios por fila, sin JS propio |

Ningún ranking de "mejor/peor" — la clasificación es solo para
priorizar cuidado y revisión, tal como pediste.

## 11. Orden de migración propuesto

El orden sugerido en la instrucción (tokens → shell → navegación →
componentes comunes → Dashboard → List → Detail → Forms → financieros →
Inventario → Ventas → Compras → RRHH/Nómina → Reportes → Configuración →
Autorizaciones) **se confirma técnicamente correcto** con un solo ajuste
justificado: mover **Compras** después de **Inventario** pero **antes**
de construir la función de servicio de la sección 9 como un sub-paso
explícito propio (no implícito dentro del paso "Compras") — de modo que
la aprobación de esa función nueva sea un punto de control aparte,
nunca mezclada silenciosamente con el resto del re-estilo de esa
pantalla. Con ese único matiz, el orden queda:

1. Design tokens (`design-system-erp.css`, sección 5)
2. Layout / Shell (`layout_app.html`, agrupación de 8 dominios)
3. Navegación (activo/colapso responsive dentro del shell ya migrado)
4. Componentes comunes (Buttons/Badges/Alerts/Cards/FormFields/Tables — reutilizados por todo lo siguiente)
5. Dashboard
6. List (Ventas)
7. Detail (Venta)
8. Forms (Gasto)
9. Finance (Cobrar) — módulo financiero de mayor riesgo, primero de ese grupo mientras el contexto está fresco
10. Inventario
11. Ventas — Cotizaciones (Sales)
12. **Compras — función de servicio de recepción (sección 9), aprobación explícita, luego re-estilo**
13. RRHH / Nómina
14. Reportes
15. Configuración
16. Autorizaciones

## 12. Estrategia

Basada en la arquitectura real encontrada, no en preferencia:
migración progresiva pantalla por pantalla (ya es el patrón probado en
todo este proyecto desde FASE F del SaaS), un único archivo CSS nuevo
por capa de identidad (`design-system-erp.css`, aislado del SaaS por el
mismo mecanismo `.shell--saas` ya en uso — nunca duplicar el enfoque de
variables CSS, ya es el correcto), reutilización literal de `ui.js`
para todo lo que ya usa `data-tabs`/`data-dropdown` (sin reescribir JS
que ya funciona), y el partial compartido `customers/_campo.html` se
mantiene como la única fuente de verdad de renderizado de campo —
cualquier ajuste visual a un campo de formulario se hace en ESE
archivo una sola vez, nunca duplicado por app.

## 13. Plan de verificación (por pantalla, mínimo)

- **Visual**: comparar contra la pantalla Stitch correspondiente
  (`docs/erp-redesign-stitch-screen-map.md`), con los valores de color
  EXACTOS del spec, nunca los renderizados por Stitch (ver nota de
  fidelidad de color en ese documento).
- **Funcional**: cada acción/formulario/botón real listado en la
  sección 8 de este documento debe seguir funcionando idéntico
  (`manage.py test` de la app correspondiente, verde antes y después).
- **Datos**: los valores mostrados siguen viniendo de los mismos
  servicios/modelos reales — ninguna cifra nueva, ninguna cifra
  eliminada.
- **Permisos**: acceso autorizado/no autorizado se comprueba igual que
  hoy (login+tenant en la mayoría, `PermissionRequiredMixin` donde ya
  exista — confirmado que Ventas/Compras/Gastos no lo tienen hoy, no se
  agrega como parte de esta migración).
- **Responsive**: desktop (grid de 2 columnas) + el único breakpoint
  real de colapso (1024px) + el ajuste de 640px — no inventar
  breakpoints de tablet que no existen hoy.
- **Estados**: badges con los 5 colores semánticos reales, estados
  vacíos con el texto real (solo el ícono cambia de emoji a SVG).
- **Navegación**: cada uno de los 21 `aria-current` del sidebar sigue
  apuntando y activándose igual tras la reagrupación en 8 dominios.

## 14. Elementos que NO deben modificarse en Etapa 1 en adelante

- Ningún modelo, migración, vista de lógica de negocio, `services.py`,
  formulario (campos/validación), URL, o permiso — salvo la única
  excepción explícitamente documentada y pendiente de aprobación de la
  sección 9 (función de agregación de recepción, puramente aditiva).
- El comportamiento financiero de Cobros (cascada, saldo a favor a la
  factura más antigua) — candidato a mejora futura, no a tocar ahora.
- Las 2 KPIs placeholder y los 2 botones deshabilitados del Dashboard.
- La ausencia de `confirm()` en Aprobar/Rechazar y en Rotar/Probar
  conexión — no agregar confirmaciones que no existen hoy.
- El archivo `static/css/design-system.css`/`static/js/ui.js`
  compartidos con el SaaS — solo lectura, nunca edición directa; todo
  cambio de identidad del ERP vive en el nuevo `design-system-erp.css`.

---

## 15. Resultado real de ETAPA 1 (ejecutada)

Implementada y verificada — ver `docs/erp-redesign-stage1-verification.md`
para el detalle completo de pruebas, responsive y comparación con
Stitch. Resumen:

- **Archivos creados**: `static/css/design-system-erp.css` (tokens Atlas
  exactos + sidebar/topbar agrupados, todo bajo `.shell--erp`).
- **Archivos modificados**: `templates/layout_app.html` (clase
  `shell--erp`, sidebar reagrupado en 8 dominios con íconos, toggle de
  ancho, bloque `extra_head` con fuentes + CSS nuevo), `static/js/ui.js`
  (función nueva y aislada `initSidebarAnchoToggleErp`, sin tocar la del
  SaaS).
- **No se tocó**: `static/css/base.css`, `static/css/design-system.css`,
  ninguna función existente de `ui.js`, ningún modelo/vista/form/URL/
  permiso, la función de servicio de recepción de Compras (sigue
  PENDIENTE — decisión funcional separada, sección 9).
- **Verificación**: suite completa de Django (1446 tests, todas las
  apps incluidas `apps/billing` del SaaS) — `OK`, cero regresiones.
- **Pendiente explícito**: validación visual en navegador real (sin
  herramienta de captura en este entorno — mismo criterio ya usado en
  todo este proyecto), aplicación de `.u-cifra` a cifras reales de cada
  pantalla (queda para Etapa 2, pantalla por pantalla), Modo Noche (no
  autorizado en esta etapa).

## 16. Resultado real de ETAPA 2 (Dashboard, List, Detail, Form)

Las 4 familias maestras están **VERIFICADA** en
`docs/erp-redesign-migration-matrix.md`. Resumen:

- **Dashboard** (`apps/dashboard/templates/dashboard/panel.html`):
  `.u-cifra` en los 4 valores de KPI reales (`.kpi__valor`); 2 íconos de
  estado vacío (✅/🕓) reemplazados por SVG de línea. Cero cambios a
  `apps/dashboard/services.py` — las 2 KPI placeholder y los 2 botones
  deshabilitados se conservaron exactamente.
- **List** (`apps/sales/templates/sales/sale_list.html`): columna Total
  alineada a la derecha (`.u-num`) con `.u-cifra`; ícono de estado
  vacío (🧾) reemplazado. La lógica condicional de badges
  (confirmed/canceled/otro → verde/peligro/neutro) ya era semántica —
  no se tocó.
- **Detail** (`apps/sales/templates/sales/sale_detail.html`): `.u-num`
  + `.u-cifra` en las 5 columnas numéricas de la tabla de líneas, en
  las 4 cifras KPI de totales, en las 2 KPI de pagos y en la columna
  "Monto aplicado" de la tabla de pagos; los 5 íconos de estado vacío
  (🧾/💳/↩️/📎/🕓) reemplazados por SVG. **No se tocó** el badge de
  estado en el encabezado (hoy fijo en azul/advertencia, sin reflejar
  `sale.status`/`sale.payment_status` como sí hace el listado) — ver
  discrepancia documentada abajo, decisión de no tocarlo esta etapa.
- **Form** (`apps/expenses/templates/expenses/expense_form.html`):
  reestructurado de una sola columna sin secciones a 3 secciones
  (Información general, Monto, Excepcionalidad) + una sección final de
  Notas, grilla de 2 columnas — patrón FormLayout de Atlas (FASE 4,
  decisión 4). **Los 13 campos reales de `ExpenseForm` se preservaron
  exactamente, mismo orden relativo, ningún campo agregado ni
  eliminado, ningún `name` cambiado.** No se agregó un botón
  "Cancelar" (no existía antes).
- **Archivos modificados**: los 4 templates de arriba, más
  `static/css/design-system-erp.css` (utilidades nuevas `.u-num`,
  tamaño de ícono SVG en `.estado-vacio__icono`), más
  `apps/dashboard/tests.py` (2 aserciones de test actualizadas — ver
  "Problemas encontrados" abajo).
- **Discrepancia documentada, no corregida**: el badge de estado del
  encabezado de Detalle de venta usa color fijo en vez de reflejar
  `sale.status`/`sale.payment_status` como ya hace el listado — se deja
  intencionalmente sin tocar por ser un cambio de lógica condicional,
  no de presentación pura; candidato a corrección futura si se aprueba
  explícitamente.
- **Discrepancia documentada, no corregida**: `.kpi`/`.kpi-grid` real
  usa una barra de acento izquierda (3px), no la tarjeta con sombra que
  mostraban las pantallas maestras de Stitch — se conservó el patrón
  real existente (ya hereda el azul Atlas correctamente) en vez de
  reescribir el componente para igualar la composición exacta de
  Stitch.
- **Pruebas**: `manage.py test apps.dashboard apps.sales apps.expenses`
  → 217 tests, `OK` (tras corregir 2 aserciones que verificaban el
  markup exacto del KPI, rotas por el `.u-cifra` intencional).
  `manage.py test` completo → 1446 tests, `OK`, 0 regresiones.
- **Cotizaciones, Reportes, Compras (recepción), Modo Noche, POS**: sin
  tocar, tal como exigía esta etapa.

---

## 17. Resultado real de ETAPA 3A (Finance, Inventory, Sales/Cotizaciones)

**Finance** (`apps/pos/templates/pos/customer_collections.html`):
`.u-num`+`.u-cifra` en Saldo a favor/Facturas pendientes (KPI), en la
tabla de facturas pendientes (Total/Saldo pendiente) y en la tabla de
pagos/reembolsos (Monto/Disponible sin aplicar); 2 íconos de estado
vacío (✅/💳) reemplazados por SVG. **Cero cambios** a la distribución en
cascada, a la aplicación de saldo a favor hardcodeada a la factura más
antigua, ni a `apps/pos/services.py`/`apps/sales/services.py`. El
formulario de reembolso se dejó exactamente como estaba (campos sin
`_campo.html`, sin etiquetas visibles) — se documenta como discrepancia
de accesibilidad preexistente, no se tocó por requerir reestructurar el
layout compacto de esa fila, fuera del alcance de "migración
puramente visual" de esta etapa.

**Inventory** (`apps/inventory/templates/inventory/product_list.html` +
`product_detail.html`): `.u-num`+`.u-cifra` en Precio de venta/Stock
actual del listado; en las 4 KPI del detalle; en Costo unitario de la
tabla de unidades serializadas; **en el Kardex, las 7 columnas reales
(Fecha/Tipo/Cantidad/Stock anterior/Stock posterior/Usuario/Notas) se
preservaron exactamente, sin reducir a 4** — solo las 3 numéricas
(Cantidad/Stock anterior/Stock posterior) recibieron alineación y
tipografía mono. 4 íconos de estado vacío reemplazados (📦/🔖/🕓/🖼️).
Cero cambios a `services.py`, a la máquina de estados de
`InventoryUnit`, ni a las consultas de `list_products_with_stock`/
`get_product_movements`.

**Sales — Cotizaciones** (`apps/sales/templates/sales/quotation_list.html`):
`.u-num`+`.u-cifra` en Total; badge de estado migrado de un solo color
fijo (`badge--azul` siempre) a coloración semántica basada en los 7
estados reales verificados en `Quotation.Status`
(`apps/sales/models.py`): Aceptada/Convertida→verde, Rechazada/Vencida/
Cancelada→peligro, Enviada→azul, Borrador→neutro — mismo técnica
condicional ya usada y aprobada en `sale_list.html` para `Sale.status`,
aplicada aquí por primera vez tras verificar el enum real (no se
inventó ningún estado). Ícono de estado vacío reemplazado. Cero cambios
a `QuotationListView`, a `apps/sales/forms.py`, ni a la lógica de
conversión cotización→venta.

**Archivos modificados**: los 5 templates de arriba, más
`docs/erp-redesign-implementation-plan.md`/`migration-matrix.md`. Sin
cambios a `design-system-erp.css` (las utilidades `.u-num`/`.u-cifra`
ya existían de Etapa 2).

**Pruebas**: `manage.py test apps.pos apps.inventory apps.sales` → 399
tests, `OK`, sin necesidad de ajustar ninguna aserción esta vez.
`manage.py test` completo → 1446 tests, `OK`, 0 regresiones.

**No tocado, confirmado**: Purchases, recepción de Compras
(`get_purchase_order_received_percent`), HR/Payroll, Reports,
Configuration, Approvals, Modo Noche, POS productivo (solo se tocó UNA
plantilla de `apps/pos` — `customer_collections.html`, parte explícita
de la familia Finance — nunca el Terminal/carrito ni ninguna otra
pantalla operativa del POS), SaaS Super Admin.

---

## 18. Resultado real de ETAPA 3B (Purchases, HR/Payroll)

**Purchases** (`apps/purchases/templates/purchases/purchase_order_list.html`
+ `purchase_order_detail.html`): `.u-num`+`.u-cifra` en Total del
listado; en Cantidad/Recibido/Pendiente/Costo unitario/Total de la
tabla de líneas del detalle; en Total de la tabla de facturas; 6 íconos
de estado vacío reemplazados por SVG (líneas/recepciones/facturas/
devoluciones/documentos/actividad). **Confirmación explícita: NO se
creó `get_purchase_order_received_percent` ni ninguna función de
servicio, consulta agregada o cálculo nuevo. NO se modificó ningún
modelo ni migración.** Verificado antes de tocar nada: el listado
(`purchase_order_list.html`) no consulta `PurchaseReceiptItem` en
absoluto hoy; el detalle solo tiene `item.recibido`/`item.pendiente`
POR LÍNEA (cantidades, ya calculadas por
`get_purchase_order_items_received_bulk`), nunca un porcentaje ni un
agregado por orden — se dejaron exactamente como números alineados,
sin convertir a fracción ni porcentaje. **Componente visual aprobado
(barra de progreso de recepción); lógica de porcentaje de recepción
pendiente de autorización funcional** — no implementada en ninguna
pantalla de esta etapa, tal como exigía la instrucción.

**HR/Payroll** (`apps/hr/templates/hr/employee_detail.html` +
`apps/payroll/templates/payroll/payroll_detail.html`): **las 7
pestañas reales confirmadas y preservadas exactamente** (Datos,
Contratos, Documentos, Asistencia, Ausencias, Incidentes, Actividad —
verificado leyendo el archivo completo antes de tocarlo, ninguna
reducida ni renombrada). Gating de datos sensibles migrado al patrón
Atlas ya aprobado en FASE 4 (ícono de candado + texto en `text-muted`)
— **el `{% if puede_ver_sensible %}` original permanece carácter por
carácter idéntico**, el texto mostrado en la rama oculta es el mismo,
no se expuso ningún dato adicional, no se tocó `apps/hr/views.py` ni
`can_view_sensitive_employee_data`. `.u-num`+`.u-cifra` en Salario
(contratos), Retraso/Horas (asistencia), Días (ausencias), Monto
(líneas y pagos de nómina), Neto/Bruto/Deducciones/Saldo pendiente. 6
íconos de estado vacío reemplazados en HR.

**Discrepancia nueva documentada**: en la tabla de Contratos de
`employee_detail.html`, la columna Salario **no está protegida por
`puede_ver_sensible`** (a diferencia del salario base del empleado, que
sí lo está) — se aplicó `.u-cifra` a la cifra tal como ya se
renderizaba, sin tocar ese gating preexistente (no es parte del alcance
de esta etapa modificar autorización); queda documentado para que se
evalúe como posible corrección de permisos en una fase futura,
explícitamente fuera de esta migración visual.

**Discrepancia ya conocida, repetida**: los badges de estado en los
encabezados de Detalle de orden de compra y Detalle de empleado
siguen fijos (`badge--azul` siempre) sin reflejar el estado real —
mismo patrón ya documentado y dejado sin tocar en Detalle de venta
(Etapa 2), por ser cambio de lógica condicional, no de presentación
pura.

**Archivos modificados**: 4 templates (`purchase_order_list.html`,
`purchase_order_detail.html`, `employee_detail.html`,
`payroll_detail.html`). Ningún archivo de `models.py`/`views.py`/
`forms.py`/`urls.py`/`services.py`/migraciones.

**Pruebas**: `apps.purchases` → 52 tests, `OK`. `apps.hr apps.payroll`
→ 70 tests, `OK` (tras corregir una colisión de nombre de base de datos
de test por haberlos corrido en paralelo con Purchases — se
re-ejecutaron de forma secuencial). Suite completa → **1446 tests,
`OK`, 0 regresiones** (una primera corrida reportó 1 error que resultó
ser la salida truncada por un `tail` en el comando, no un fallo real —
la re-corrida con salida íntegra confirmó `OK` limpio, con el mismo
artefacto de bloqueo de archivo temporal de Windows ya visto y
documentado en Etapa 1, no relacionado con estos cambios).

**No tocado, confirmado**: Reports, Configuration, Approvals, Modo
Noche, POS (ni operativo ni Lab), SaaS Super Admin.

---

## 19. Resultado real de ETAPA 3C (Reports, Configuration, Approvals)

**Reports** (`apps/reports/templates/reports/sales_report.html`):
`.u-num`+`.u-cifra` aplicado a las 8 filas del resumen KPI y a la
columna Total del listado de resultados; ícono de estado vacío
reemplazado. **El resumen KPI permanece exactamente como tabla
(`<table class="tabla"><tbody><tr><th>Etiqueta</th><td>Valor</td></tr>...`)
— NO se convirtió a KpiCards**, tal como exigía la instrucción; se
verificó antes de tocar nada que ninguna consulta, agregación ni
cálculo de `SalesReportView`/`SalesReportFilterForm` fue modificado.
Los 3 enlaces de exportación (CSV/PDF/XLSX) y el formulario de filtros
(`date_from`/`date_to`/`customer`/`status`) ya usaban componentes
compartidos (`.tarjeta`, `_campo.html`, `.btn`) — heredan Atlas
automáticamente, sin cambios de estructura. La columna "Estado" del
listado de resultados **no tenía badge antes y se dejó como texto
plano** — no se introdujo un componente nuevo donde no existía.

**Configuration** (`apps/core/templates/core/settings_home.html` +
`apps/api/templates/api/config.html`): las 4 tarjetas del hub pasaron
de apiladas a una grilla responsiva (`auto-fit minmax`); los 4 emoji de
encabezado (🔑📋🔌🛒) reemplazados por íconos SVG de línea — mismos 4
enlaces, mismo texto, ninguna tarjeta agregada ni quitada. En la
pantalla de API de Inventario, `.u-cifra` en Base URL y en la clave
enmascarada; el resto del archivo ya usaba `.tarjeta`/`.alerta`/
`.badge`/`_campo.html` correctamente, sin necesitar cambios
estructurales. **Cero cambios** a `name`/`id`/`required`/validaciones/
choices de ningún campo, a los 3 formularios POST (Generar/Rotar/
Revocar/Actualizar scopes), ni a `require_permission` en
`apps/api/config_views.py`.

**Approvals** (`apps/approvals/templates/approvals/pending_list.html`):
`.u-num`+`.u-cifra` en Solicitado/Límite (pendientes) y Solicitado/
Aprobado (historial); 2 íconos de estado vacío reemplazados. **Cero
cambios** a los 2 formularios separados de Aprobar/Rechazar (mismo
`decision` oculto, mismo endpoint `approval_resolve`, sin agregar
`confirm()` donde no existía), a `puede_resolver`, a
`can_user_approve`, ni a ningún estado de `ApprovalRequest.Status`. El
badge del historial ya era semántico (verde/peligro/neutro) — sin
tocar.

**Discrepancia documentada, no corregida**: el subtítulo del hub de
Configuración sigue diciendo "(próximamente) la API de Inventario"
pese a que está completamente implementada y enlazada dos tarjetas más
abajo en la misma página (ya señalado en el ERP REDESIGN MAP) — es una
corrección de texto/contenido, no de presentación visual, fuera del
alcance de esta etapa; se deja para una decisión explícita futura.

**Archivos modificados**: 4 templates
(`sales_report.html`, `settings_home.html`, `config.html`,
`pending_list.html`). Ningún archivo de `models.py`/`views.py`/
`forms.py`/`urls.py`/`services.py`/migraciones/permisos.

**Pruebas**: `apps.reports` → 29 tests, `OK`. `apps.core apps.api
apps.approvals` → 142 tests, `OK` (corridos secuencialmente tras el
reporte, evitando la colisión de base de datos de test de la etapa
anterior). Suite completa → **1446 tests, `OK`, 0 regresiones**.

**No tocado, confirmado**: Modo Noche, POS (operativo ni Lab), SaaS
Super Admin, lógica de recepción de Purchases
(`get_purchase_order_received_percent` sigue sin crearse).

Con esta etapa, **las 13 familias maestras de la matriz de migración
quedan `VERIFICADA`** — FASE 5, Etapa 3 completa.

---

## 20. Resultado real de ETAPA 4 (QA visual, responsive, estados, consistencia)

Auditoría de código completa sobre las 13 familias ya `VERIFICADA`
(sin volver a tocar lógica, permisos, modelos ni URLs). Metodología:
lectura y `grep` sistemático de los archivos reales — no hay
herramienta de navegador en este entorno, por lo que esta es una **QA
de código, no una validación visual en navegador real** (mismo
criterio ya declarado en todas las fases anteriores de este proyecto).

### Defectos encontrados y corregidos
**Responsive roto (real)**: 4 grillas de 2 columnas con
`style="display:grid; grid-template-columns: 1fr 1fr;"` en línea —
3 en `expense_form.html` (Form) y 1 en `customer_collections.html`
(Finance) — no colapsaban a 1 columna en móvil porque un `style=""`
en línea no puede llevar un `@media`. Se creó la utilidad
`.shell--erp .u-grid-2col` (`static/css/design-system-erp.css`, mismas
2 columnas en escritorio, 1 columna bajo 640px) y se aplicó en esas 4
ubicaciones — mismos campos, mismo orden, solo el layout ahora colapsa
de verdad. **`pos/terminal.html` tiene el mismo patrón pero NO se
tocó** (POS operativo, explícitamente fuera de alcance).

### Sin defectos (verificado, no requirió corrección)
- Los otros 3 usos de grilla en pantallas migradas (`settings_home.html`,
  `reports/index.html`, `audit/search.html`) ya usan
  `repeat(auto-fit/auto-fill, minmax(...))` — responsivos por diseño,
  ninguno tocado.
- `.kpi-grid` (usado en Dashboard/Detail/Finance/Inventory) ya era
  `auto-fit` — responsivo sin cambios.
- `.tabla-envoltorio{overflow-x:auto}` (compartido, sin tocar) sigue
  cubriendo cualquier tabla más ancha que el viewport en las 13
  familias.

### Tipografía y color — confirmado limpio
Grep en las 13 familias migradas: **cero** referencias a "Google Sans"/
"Public Sans" (fuentes de Stitch) en ningún template ni CSS — la única
tipografía real es IBM Plex Sans + IBM Plex Mono
(`templates/layout_app.html`, un solo `<link>` de Google Fonts con
exactamente esas dos familias). `--color-primario: #1D4E89` confirmado
como único valor en `design-system-erp.css`, correctamente aislado
bajo `.shell--erp` — verificado que `base.css` (`#1d4ed8`, compartido)
y `design-system.css` (`#2A4CD6`, bajo `.shell--saas`) permanecen
intactos y nunca se mezclan con el del ERP.

### Íconos — confirmado consistente
Barrido completo de emoji en las 13 pantallas migradas: **cero
restantes** (confirmado con `grep` de rango Unicode de emoji sobre los
16 archivos tocados). Los otros ~127 templates reales del ERP (fuera
de alcance de FASE 5) conservan sus emoji intactos, tal como
corresponde. Trazo de ícono: 1.75px para navegación (sidebar/topbar,
23 usos) vs. 1.5px para contenido (estados vacíos/encabezados de
tarjeta, 36 usos) — diferenciación consistente dentro de cada
categoría, no una inconsistencia. Los 2 únicos `stroke-width="12"`/`"2"`
del proyecto pertenecen a `apps/billing/templates/billing/admin/` y
`apps/core/templatetags/ui_icons.py` (Super Admin SaaS) — confirmado
que nunca se cruzan con el ERP.

### Tabs y columnas — recontados directamente sobre el código real
Venta: **5** `role="tab"` (confirmado por grep). Compras: **6**.
RRHH: **7**. Kardex de Inventario: **7** columnas reales
(Fecha/Tipo/Cantidad/Stock anterior/Stock posterior/Usuario/Notas,
confirmado línea por línea) — ninguno reducido.

### Componentes — consistencia por construcción
Todo el trabajo de las 13 familias reutilizó exclusivamente las clases
compartidas ya existentes (`.btn`, `.tarjeta`, `.badge`, `.tabla`,
`.campo`, `.kpi`, `.alerta`), que heredan los mismos tokens Atlas por
estar dentro de `.shell--erp` — no hay radios, paddings ni sombras
divergentes posibles porque nunca se declararon valores nuevos fuera
de `design-system-erp.css` (un solo archivo, una sola fuente de
verdad para lo nuevo).

### Discrepancias que permanecen (documentadas, sin tocar — confirmadas otra vez)
KPI summary de Reportes sigue siendo tabla · Kardex 7 columnas ·
HR 7 tabs · Compras 6 tabs · Venta 5 tabs · barra de recepción de
Compras sin lógica · badges fijos de encabezado en Detalle de
Venta/OC/Empleado · columna Salario de Contratos sin gating · subtítulo
"(próximamente)" en Configuración · formulario de reembolso en Cobrar
sin `_campo.html`. Ninguna se tocó esta etapa (son de contenido/lógica,
no de QA visual).

### Observación nueva (no un defecto introducido por Atlas)
El `.navbar` compartido no tiene `flex-wrap`/`overflow-x` propio para
un nombre de tenant muy largo en viewport angosto — comportamiento
**preexistente** de la clase compartida, no modificado por esta
migración; no se tocó `.navbar` (clase compartida con el SaaS) para
"solucionarlo" sin autorización explícita — queda documentado como
observación, no como regresión de FASE 5.

**Archivos modificados esta etapa**: `static/css/design-system-erp.css`
(+utilidad `.u-grid-2col`), `apps/expenses/templates/expenses/expense_form.html`,
`apps/pos/templates/pos/customer_collections.html`. Ningún archivo de
lógica.

**Pruebas**: `apps.expenses apps.pos` → 117 tests, `OK`. Suite completa
→ **1446 tests, `OK`, 0 regresiones** (mismo número de tests que en
Etapa 3C — ninguno eliminado ni agregado).

**No tocado, confirmado**: Modo Noche, POS (operativo ni Lab, salvo la
única clase CSS reutilizable aplicada a `customer_collections.html`,
ya en alcance desde Etapa 3A), SaaS Super Admin, lógica de recepción
de Purchases, cualquier modelo/vista/form/URL/permiso/servicio.

---

## 21. Resultado real de ETAPA 5 (verificación final y cierre de FASE 5)

### Validación visual real en navegador
**Validación visual real en navegador no disponible.** Se buscó
explícitamente una herramienta de navegador/captura (`ToolSearch`,
consulta "browser screenshot playwright visual render") antes de
declarar esta conclusión — el entorno no expone ninguna herramienta de
renderizado/captura de pantalla real (solo `WebFetch`, que convierte
una URL a markdown/texto y no renderiza ni captura píxeles, y las
herramientas de configuración de proyecto de Stitch, no relacionadas).
Mismo hallazgo, confirmado de nuevo, que en todas las fases anteriores
de esta iniciativa. Por lo tanto esta etapa es, por diseño,
**auditoría estática de cierre** — no una validación visual pixel a
pixel.

### Auditoría estática de cierre
- `grep '!important'` sobre `design-system-erp.css` → **0 resultados**
  (ninguna regla fuerza especificidad por encima del árbol de cascada
  compartido).
- `grep` de `style="..."` con color hexadecimal inline sobre todo
  `*.html` del proyecto → **0 resultados** (ningún color hardcodeado
  fuera de los tokens Atlas en ningún template).
- `grep 'shell--saas'` sobre `design-system-erp.css` → aparece
  únicamente dentro de comentarios explicativos (líneas 6/10/13,
  documentando el aislamiento), **cero reglas CSS reales** apuntan a
  `.shell--saas` — aislamiento `.shell--erp` / `.shell--saas` / `:root`
  compartido confirmado limpio una vez más.
- `python manage.py check` → `System check identified no issues (0
  silenced)`.
- `git status --porcelain` → exactamente el mismo conjunto de 19
  archivos modificados + 10 archivos nuevos de documentación/CSS que
  en cada etapa anterior — **ningún archivo de lógica
  (`models.py`/`views.py`/`forms.py`/`urls.py`/`services.py`/
  migraciones/permisos) aparece en la lista**, confirmado por última
  vez antes del cierre.

### Corrección documental (no de código)
La fila `Shell` de `erp-redesign-migration-matrix.md` había quedado
con `Estado = PENDIENTE` desde la Etapa 0, nunca actualizada tras
implementarse en Etapa 1 y auditarse en Etapa 4 — un olvido de
documentación, no un defecto de código (el Shell real —
`layout_app.html`, sidebar de 8 grupos/21 rutas, topbar, toggle
compacto/expandido — está implementado, probado y ya cubierto por la
suite completa desde Etapa 1). Corregida a `VERIFICADA` en esta etapa,
junto con la nota de cabecera del documento. Es la única edición de
esta etapa: no se tocó ninguna fila de contenido/riesgo/componentes de
las otras 12 familias.

### Re-confirmación de las 13 familias (Shell, Dashboard, List, Detail,
Form, Finance, Inventory, Sales-Cotizaciones, Purchases, HR-Payroll,
Reports, Configuration, Approvals)
Sin hallazgos nuevos frente a Etapa 4 — se reconfirma cada punto ya
auditado: Kardex 7 columnas, HR 7 tabs, Compras 6 tabs, Venta 5 tabs,
KPI summary de Reportes como tabla, cero emoji restantes en las 16
pantallas migradas, trazo de ícono 1.75/1.5 consistente, tipografía
IBM Plex Sans/Mono única, `--color-primario: #1D4E89` único y aislado,
`.u-grid-2col` cubriendo las 4 grillas que antes no colapsaban,
`.tabla-envoltorio{overflow-x:auto}` cubriendo toda tabla ancha.

### Discrepancias que permanecen (mismas de Etapa 4, ninguna nueva, ninguna tocada)
KPI summary de Reportes sigue siendo tabla · Kardex 7 columnas · HR 7
tabs · Compras 6 tabs · Venta 5 tabs · badges fijos de encabezado en
Detalle de Venta/OC/Empleado · columna Salario de Contratos sin
gating · subtítulo "(próximamente)" en Configuración · formulario de
reembolso en Cobrar sin `_campo.html`. **Barra/porcentaje de recepción
de Compras**: componente visual aprobado previamente (columnas
Cantidad/Recibido/Pendiente ya migradas con tokens Atlas); lógica
funcional de porcentaje de recepción pendiente de decisión/
autorización independiente — no implementada en FASE 5, tal como se
instruyó explícitamente.

### Pruebas (evidencia de cierre)
No se modificó ningún archivo de lógica ni de template desde la última
corrida completa de Etapa 4 (única edición de esta etapa: 2 líneas de
`erp-redesign-migration-matrix.md`, documentación pura). La última
corrida completa sigue siendo válida como evidencia de cierre: suite
completa → **1446 tests, `OK`, 0 regresiones** (mismo total que Etapa
3C/4); subconjunto `apps.expenses apps.pos` → **117 tests, `OK`**.
Únicos artefactos observados en ambas corridas: el `PermissionError
[WinError 32]` intermitente y ya documentado como inofensivo (bloqueo
de archivo temporal de Windows al borrar un PDF de prueba en
`apps.expenses`, no relacionado con este trabajo) y un `RuntimeError:
boom` que es un mock deliberado de un test de manejo de errores del
Dashboard, no un fallo real. `python manage.py check` → sin problemas.

### No tocado, confirmado por última vez
Modo Noche (no implementado en ningún template ni CSS), POS operativo
(terminal/carrito/caja/apertura/cierre — intactos, salvo la única
clase `.u-grid-2col` ya en alcance desde Etapa 3A/4 en
`customer_collections.html`, que es Finanzas/Cuentas por Cobrar, no
POS), SaaS Super Admin (`.shell--saas`, cero reglas nuevas), lógica de
recepción de Compras, y cualquier modelo/vista/form/URL/permiso/
servicio del proyecto.

### Recomendación técnica de cierre
Las 13 familias maestras están implementadas, auditadas a nivel de
código (dos rondas independientes, Etapa 4 y Etapa 5) y cubiertas por
1446 tests en verde sin regresiones. El único componente pendiente
(barra de recepción de Compras) es una decisión de negocio explícitamente
diferida, no un defecto. No hay hallazgos abiertos de esta etapa.

**FASE 5 — CERRADA / APROBADA.** Cierre formal recibido del usuario:
las 8 sub-etapas (0 a 5) y las 4 fases previas (1-4) quedan cerradas.
Ningún cambio de código adicional en este cierre — únicamente
verificación de que la documentación reflejara el estado correcto.

**Archivos modificados esta etapa**: `docs/erp-redesign-migration-matrix.md`
(2 líneas, corrección de estado documental) + este mismo documento
(§21). Ningún archivo de código.

**No se re-ejecutó la suite completa** (5574s en la corrida previa,
cero cambios de código desde entonces) — se reutiliza como evidencia
válida de cierre, respaldada por `manage.py check` fresco y la
auditoría estática fresca de esta misma etapa.

---

*Ver también `docs/erp-redesign-migration-matrix.md`: las 13 familias
maestras (Shell, Dashboard, List, Detail, Form, Finance, Inventory,
Sales-Cotizaciones, Purchases, HR-Payroll, Reports, Configuration,
Approvals) están `VERIFICADA`. Nota de Purchases: sin barra de
progreso de recepción, pendiente de autorización funcional separada.
FASE 5 — CERRADA / APROBADA (§21). Siguiente fase (candidato: FASE 7
— POS Lab profundo) sin iniciar, pendiente de autorización explícita
separada.*
