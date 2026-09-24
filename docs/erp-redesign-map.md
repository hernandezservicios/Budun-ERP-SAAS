# ERP REDESIGN MAP

Inventario exhaustivo del ERP (Budun ERP SaaS) tal como existe HOY en el
código Django real — FASE 1 de discovery, previa a cualquier rediseño
visual. Ningún archivo de código fue modificado para producir este
documento. Todo lo que aquí aparece es lo que el código realmente hace;
donde algo no existe (buscador, exportación, permiso granular, modal),
se dice explícitamente que no existe — nunca se completa por
suposición.

**Fuente de verdad**: Django (modelos, vistas, URLs, templates reales).
El futuro Design System y Stitch determinarán únicamente el CÓMO se ve;
este documento es el QUÉ existe.

**Alcance**: el ERP tenant (shell `templates/layout_app.html`) y el
Portal de Billing del tenant (`/facturacion/`, mismo shell). Explícitamente
FUERA de alcance: el SaaS Super Admin (`templates/layout_saas_admin.html`,
`apps/billing/admin_*`, `apps/billing/platform_views.py`) — ya auditado
y migrado a Hybrid en fases anteriores (ver `docs/design-system-v1-hybrid.md`).

**Metodología**: 6 sub-agentes de exploración de solo lectura, cada uno
auditando un grupo de apps Django completo (urls.py, views.py, forms.py,
models.py, y cada template renderizado). Sus hallazgos se consolidan
aquí sin alterar su contenido, solo reorganizados en las 17 secciones
pedidas.

---

## 01. Arquitectura

- **21 apps Django** bajo `apps/`: `accounting`, `accounts`, `api`,
  `approvals`, `audit`, `backups`, `billing`, `core`, `customers`,
  `dashboard`, `expenses`, `hr`, `inventory`, `payroll`, `permissions`,
  `pos`, `purchases`, `reports`, `sales`, `tenants`.
- **Montaje de URLs** (`config/urls.py`): `/admin/`, `/cuentas/`
  (accounts), `/panel/` (dashboard), `/inventario/` (inventory), ``
  (customers + sales + approvals, montados en raíz porque sus propios
  `urls.py` ya definen el prefijo), `/pos/`, `/compras/` (purchases),
  `/gastos/` (expenses), `/rrhh/` (hr), `/nomina/` (payroll),
  `/contabilidad/` (accounting), `/reportes/` (reports),
  `/configuracion/permisos/` (permissions), `/configuracion/auditoria/`
  (audit), `/configuracion/api-inventario/` (api.config_urls),
  `/configuracion/integraciones/` (api.integration_urls),
  `/api/v1/catalog/` + `/api/v1/` (REST, fuera de alcance visual),
  `/plataforma/billing/paypal/` + `/webhooks/` + `/plataforma/billing/admin/`
  (SaaS Super Admin, fuera de alcance), `/facturacion/` (Portal de
  Billing del tenant, SÍ en alcance), `` (core, al final).
- **Dos shells completamente separados**: `templates/base.html` (raíz
  de todo el proyecto — navbar público + toasts) y
  `templates/layout_app.html` (extiende `base.html`, sobreescribe el
  bloque `body` completo con el shell real del ERP: sidebar fijo de 20
  ítems + navbar con badge de tenant + dropdown de usuario). Un tercer
  shell, `templates/layout_saas_admin.html`, es exclusivo del Super
  Admin de plataforma y está fuera de alcance de este documento.
- **Multi-tenancy**: `apps.tenants` no tiene ni una sola pantalla propia
  — es infraestructura pura (`TenantMiddleware` resuelve
  `request.tenant`/`request.membership` desde las membresías reales del
  usuario, nunca de datos enviados por el cliente; `TenantScopedModel`/
  `TenantManager` aíslan cada queryset automáticamente).
  **Hallazgo arquitectónico relevante**: el modelo de datos ya soporta
  que un usuario pertenezca a varios tenants (`active_tenant_id` en
  sesión), pero **no existe ninguna pantalla de "cambiar de empresa"**
  — ninguna vista real escribe esa clave de sesión.
- **Autorización**: tres mecanismos conviven, usados de forma desigual
  entre módulos (ver sección 10): `LoginRequiredMixin`+
  `TenantRequiredMixin` (mínimo común en casi todas las vistas),
  `PermissionRequiredMixin`/`require_permission` (catálogo granular
  código-definido, `apps.permissions.catalog.PERMISSION_CATALOG`), y
  `require_role`/`require_superuser` (para OWNER/Super Admin).
- **Design System actual** (FASE 5, `docs/design-system.md`):
  `static/css/base.css` (tokens) + `static/css/design-system.css`
  (componentes) + `static/js/ui.js` (sidebar/dropdown/modal/tabs/toasts)
  — el MISMO archivo que ya usa el SaaS Super Admin (con overrides
  `.shell--saas`). El rediseño del ERP debe decidir si reutiliza esta
  base de tokens/componentes o construye una paralela — pero cualquier
  cambio a estos 3 archivos compartidos puede afectar visualmente al
  Super Admin SaaS ya aprobado, y viceversa.
- **Iconografía real del ERP tenant**: **emoji Unicode inline** en
  prácticamente todos los estados vacíos de las 6 áreas auditadas (🧾
  📦 👥 💳 🔍 🕓 etc.) — a diferencia del SaaS Super Admin, que ya
  migró a un sistema de iconos SVG propio (`apps/core/templatetags/ui_icons.py`).
  El ERP tenant **nunca usa ese sistema SVG** en las pantallas reales
  auditadas.
- **Modales**: ver hallazgo cruzado en la sección 09 — el ERP tenant
  **no usa `<dialog>`/`.modal` en ninguna pantalla real** auditada,
  pese a que el componente existe en el Design System y se
  ejemplifica en `/estilo/`.

---

## 02. Módulos reales

Lista verificada contra `templates/layout_app.html` (sidebar real) +
URLs montadas. Solo se listan módulos con pantallas reales.

| # | Módulo (nombre en sidebar) | App Django | Entra por |
|---|---|---|---|
| 1 | Panel | `dashboard` | `dashboard:panel` |
| 2 | Inventario | `inventory` | `inventory:product_list` |
| 3 | Clientes | `customers` | `customers:customer_list` |
| 4 | Proveedores | `customers` | `customers:supplier_list` |
| 5 | Cotizaciones | `sales` | `sales:quotation_list` |
| 6 | Proformas | `sales` | `sales:proforma_list` |
| 7 | Ventas | `sales` | `sales:sale_list` |
| 8 | Compras | `purchases` | `purchases:purchase_order_list` |
| 9 | Facturas de proveedor | `purchases` | `purchases:supplier_invoice_list` |
| 10 | POS | `pos` | `pos:terminal_start` |
| 11 | Cobros | `pos` | `pos:collections_search` |
| 12 | Cajas | `pos` | `pos:register_list` |
| 13 | Gastos | `expenses` | `expenses:expense_list` |
| 14 | RRHH | `hr` | `hr:employee_list` |
| 15 | Nómina | `payroll` | `payroll:period_list` |
| 16 | Contabilidad | `accounting` | `accounting:period_list` |
| 17 | Reportes | `reports` | `reports:index` |
| 18 | Autorizaciones | `approvals` | `approvals:pending_list` |
| 19 | Configuración | `core` + `permissions` + `audit` + `api` | `core:settings` (hub) |
| 20 | Mi Facturación | `billing` (Portal) | `billing_portal:status` |
| 21 | Mi perfil | `accounts` | `accounts:perfil` |

**No enlazados desde el sidebar pero reales y navegables**: Landing
pública (`core:home`), Design System de referencia (`core:design_system`,
solo enlazado desde el footer de la Landing), todo el flujo de
autenticación (`accounts`: registro/login/onboarding/recuperar
contraseña/activación — públicos o pre-tenant), Reservas (`sales:reservation_list`,
alcanzable solo desde el botón "Reservas" dentro de la propia pantalla
de Ventas, no desde el sidebar).

**`apps/tenants`**: sin URLs, sin pantallas — infraestructura pura (ver
sección 01).

---

## 03. URLs — mapa completo

> Nota: tablas completas por módulo (patrón, namespace:name, vista,
> template, métodos, permiso, efecto) están documentadas íntegramente
> en las secciones **04-09** de este archivo, organizadas por pantalla
> — repetirlas todas aquí duplicaría ~150 filas. Los namespaces reales
> confirmados son: `core`, `accounts`, `dashboard`, `inventory`,
> `customers`, `sales`, `pos`, `purchases`, `expenses`, `hr`, `payroll`,
> `accounting`, `reports`, `approvals`, `permissions`, `audit`,
> `api_config`, `api_integrations`, `billing_portal`.

Resumen de volumen por módulo (URLs reales contadas por los agentes):

| Módulo | URLs |
|---|---|
| core | 3 |
| accounts | 15 |
| dashboard | 1 |
| inventory | 21 |
| customers | 15 |
| sales (cotizaciones+proformas+ventas+reservas) | ~46 |
| pos | 20 |
| purchases | 27 |
| expenses | 21 |
| hr | 24 |
| payroll | 9 |
| accounting | 15 |
| reports | 13 |
| approvals | 5 |
| audit | 3 |
| permissions | 3 |
| api (solo pantallas HTML) | 14 |
| billing_portal | 14 |

**Total aproximado: ~270 URLs reales** en el ERP tenant (sin contar
`/admin/` de Django ni los endpoints REST de `apps/api`).

---

## 04-05. Pantallas y Acciones (por módulo)

### Shell compartido
`templates/base.html` (raíz, navbar público + toasts) y
`templates/layout_app.html` (shell ERP: sidebar de 21 ítems, navbar con
badge de tenant + dropdown Panel/Mi perfil/Cambiar contraseña/Cerrar
sesión). `templates/layout_saas_admin.html` existe pero es del Super
Admin, fuera de alcance.

### core
- **Landing pública** (`/`, `core:home`) — marketing puro: hero, "¿Para
  quién es?", "Problemas que resuelve", "Qué incluye", "Cómo funciona",
  "Ventajas", "Seguridad", "Integración con agentes CRM IA" (badge
  "Próximamente"), "Precios" (3 planes desde `apps/core/pricing.py`,
  **valores placeholder explícitamente marcados como no reales**),
  FAQ (acordeón `<details>`), CTA final.
- **Design System de referencia** (`/estilo/`, `core:design_system`) —
  página interna dentro del shell ERP, cataloga TODOS los componentes
  con datos de ejemplo (no reales): botones, formularios, badges,
  alerts, toasts, cards, tablas, tabs, dropdown, **modal** (el único
  lugar del ERP donde `<dialog class="modal">` aparece en el código
  fuente), breadcrumbs, empty state, loading states, error states. No
  enlazada desde ningún menú real.
- **Configuración (hub)** (`/configuracion/`, `core:settings`) — 4
  tarjetas de navegación pura: Roles y Permisos → `permissions:index`;
  Auditoría → `audit:search`; API de Inventario → `api_config:config`;
  Integraciones (Catalog API) → `api_integrations:list`. Sin contenido
  propio.

### accounts
Flujo completo de autenticación — 13 pantallas, todas `.auth-card`
sobre `base.html` (navbar público) EXCEPTO `perfil.html` (shell ERP
completo): Crear cuenta, Iniciar sesión, Configura tu empresa
(onboarding — un solo campo, nombre de empresa), Mi perfil (datos
personales + botón Cambiar contraseña), Activa tu cuenta (3 variantes:
válido/expirado/inválido), Cuenta activada, Reenviar activación (+
pantalla de confirmación), Recuperar contraseña (+ confirmación
anti-enumeración), Elegir nueva contraseña, Contraseña actualizada,
**Cambiar contraseña** (`password_change_form.html`/`_done.html` —
**hallazgo**: extienden `base.html`, NO `layout_app.html`, pese a
exigir sesión iniciada — el usuario "sale" visualmente del ERP).
Ninguna acción de estas pantallas usa un modelo con estado — el
"pendiente de activación" se infiere de `has_usable_password()==False`,
no es un campo persistido.

### dashboard
Una sola pantalla, "Panel" (`dashboard:panel`) — 6 secciones: Resumen
(4 KPIs, 2 de ellos SIEMPRE vacíos: "Ventas del mes"/"Gastos del mes",
con ayuda "Se activará con el módulo de Ventas/Gastos" **pese a que
`apps.sales`/`apps.expenses` ya existen y están activos**), Tendencias
(barras 100% decorativas, alturas hardcodeadas en CSS inline, sin datos
reales), Alertas (reales: miembros del equipo, stock bajo), Actividad
reciente (altas de miembros reales), Acciones rápidas (2 botones reales
+ 2 botones **deshabilitados** "Agregar producto"/"Registrar venta" con
tooltip "Disponible cuando se active el módulo de..." — **desactualizado**,
ambos módulos ya existen).

### inventory
**Categorías**: lista (sin buscador/paginación) + alta/edición + baja
física protegida contra `ProtectedError` (si tiene productos).
**Productos**: lista (buscador, filtro categoría, filtro stock bajo,
filtro inactivos, paginación 20) + alta/edición + desactivar (nunca
borrado) + **Importar/Exportar Excel** (plantilla, subida con vista
previa de nuevos/actualizados/errores/advertencias antes de confirmar,
reporte de errores descargable) + ficha de producto (KPIs, imágenes de
Catalog API). Dos ramas según `inventory_tracking_type`: **por
cantidad** (entrada/salida/ajuste de stock, historial de movimientos)
o **serializado** (registrar unidad IMEI/serie, cambiar estado de
unidad vía máquina de estados completa — ver sección 06).

### customers
**Clientes** y **Proveedores** son estructuralmente idénticos: lista
(buscador, orden, mostrar inactivos, paginación) + alta/edición + baja
lógica (nunca física) + pestañas de detalle (Datos, Documentos con
subida/descarga/eliminación validada, **Historial — SIEMPRE vacío
codificado**: "estará disponible desde FASE 10/12" pese a que
`apps.sales`/`apps.purchases` ya existen, Actividad). El partial
`customers/_campo.html` es el componente de campo de formulario
reutilizado por prácticamente TODO el proyecto (ver sección 14).

### sales
**Cotizaciones** → **Proformas** → **Ventas**, flujo de conversión
completo (cotización→proforma, cotización→venta, proforma→venta), cada
uno con lista+alta+detalle+líneas+adjuntos+actividad+impresión.
Proformas añade "Reservar stock". Ventas añade Confirmar (aplica
inventario real), Cancelar (solo en borrador), Pagos (registrar/revertir),
Devoluciones (mercancía, formulario dedicado), Recibo imprimible.
**Reservas**: lista simple (sin buscador) + Liberar. **Hallazgo mayor**:
Notas de Crédito y Reembolsos tienen modelo + máquina de estados +
servicios + tests completos, pero **CERO pantallas** — no hay URL, vista
ni template para ninguno de los dos en todo `apps/sales`.

### pos
Ver sección 12 (dedicada, ya exhaustiva).

### purchases
**Órdenes de compra**: lista + alta + detalle con 6 pestañas (Líneas,
Recepciones, Facturas, Devoluciones, Documentos, Actividad) + Enviar
(con aprobación automática si excede límite) + Cancelar + Cerrar +
Recibir línea (cantidad o serializado por unidad) + Devolución a
proveedor. **Facturas de proveedor**: lista + alta + detalle con 4
pestañas + Confirmar (asiento automático) + Cancelar + Pagar + Aplicar
anticipo + Reversar asignación. **Anticipo a proveedor**: pantalla
completa construida pero **sin ningún enlace real** en todo el proyecto
que apunte a ella.

### expenses
Lista (buscador, filtro estado, paginación) + alta + detalle con 4
pestañas (Detalle editable si borrador/rechazado, Pagos, Documentos,
Actividad) + Enviar a aprobación + Aprobar (con aprobación automática
si excede límite) + Rechazar + Cancelar + Registrar/Anular pago.
Categorías (con "sugeridas") y Recurrencias (con generación manual, sin
Celery) como catálogos propios.

### hr
Lista de empleados (buscador, filtro estado, paginación) + alta +
detalle con **7 pestañas** (Datos —con gating de sensibles—, Contratos,
Documentos, Asistencia, Ausencias, Incidentes, Actividad) + Cambiar
estado (transiciones validadas server-side, `<select>` no las filtra
visualmente) + Registrar entrada/salida de asistencia + Solicitar/
Aprobar/Rechazar/Cancelar ausencia + Reportar incidente. Catálogos:
Departamentos, Cargos, Horarios de trabajo, Tipos de ausencia (con
"sugeridos"). **Hallazgo**: `IncidentUpdateStatusView` existe (vista +
form) pero sin ningún botón que la invoque — un incidente queda
"congelado" en Abierto para siempre desde la UI.

### payroll
Períodos (lista + alta + detalle) + Aprobar + Cancelar + Cerrar +
Calcular nómina de un empleado. Detalle de nómina de empleado —
**página completa gateada por el permiso `payroll.sensitive.view`**
(a diferencia de RRHH, donde solo columnas específicas se ocultan) +
Agregar línea + Registrar/Anular pago.

### accounting
Plan de cuentas (jerárquico, recursivo) + activar/desactivar. Períodos
(abrir/cerrar/reabrir con motivo obligatorio). Asientos (crear
**siempre contabiliza de inmediato**, el estado `draft` es solo
transitorio internamente) + Reversar (nunca edita, crea asiento nuevo).
Mapeo de cuentas (evento de negocio → cuenta). 5 reportes de solo
lectura (Balance de Comprobación, Libro Mayor, Libro Diario, Balance
General, Estado de Resultados) — **ninguno tiene exportación**.

### reports
Índice ejecutivo (resumen + 16 tarjetas de acceso, incluye 5 enlaces
directos a reportes de `accounting`). 13 reportes de dominio (Ventas,
Inventario, Caja, CxC, CxP, Compras, Gastos, RRHH, Nómina —con gating
de sensibles server-side—, Clientes, Proveedores, + 2 Estados de Cuenta
individuales). Exportación real: 6 reportes con CSV+PDF+XLSX, 1 solo
CSV, 6 sin ninguna exportación (ver matriz completa en sección 11).

### approvals
Pendientes + historial (aprobar/rechazar de un clic, sin modal ni
captura de motivo pese a que el form lo soporta). Políticas por rol
(jerarquía usuario→rol→tenant→negar, documentada explícitamente en la
UI). **Hallazgo**: `approval_cancel` existe como endpoint activo sin
ningún botón en ninguna plantilla del proyecto.

### audit
Búsqueda federada (9 orígenes vía UNION SQL: 7 logs de dominio + audit
transversal + inventory) con 7 filtros GET + paginación 50/página +
exportación CSV (única, hasta 10 000 filas). Detalle de evento
(estructura de `<dl>` distinta según origen). Solo lectura absoluta,
sin ninguna acción de escritura.

### permissions
Índice de roles (excluye OWNER, siempre autorizado) + tabla de
usuarios/overrides. Permisos por rol (checkboxes agrupados por dominio
— **única pantalla del proyecto que NO reutiliza `customers/_campo.html`**,
usa `<label style="">` inline). Overrides por usuario (conceder/denegar/
quitar, con motivo opcional).

### api (solo pantallas de config)
**API de Inventario**: una sola clave por tenant (generar/rotar/revocar/
scopes/probar conexión), secreto mostrado una única vez. **Integraciones
(Catalog API)**: lista + crear + detalle (mismo patrón, pero un tenant
puede tener varias). Las 14 vistas de este submódulo son las **más
estrictamente protegidas** del ERP — todas usan `require_permission`
granular, sin excepción.

### billing (Portal del tenant, `/facturacion/`)
Mi Facturación (estado de suscripción, método de cobro, saldo a favor,
facturas recientes con acciones de pago condicionadas, historial de
comprobantes) + Elegir plan + Cambiar de plan (con prorrateo) +
Cancelar (**sin modal, sin exponer los campos reales del form** —
siempre cancela "al finalizar el período" sin opción de inmediato ni
motivo) + Transferencia bancaria (subir comprobante; **cuenta bancaria
mostrada SIN enmascarar**, a diferencia del admin) + Checkout PayPal
(único/recurrente, sin plantilla propia, solo mensajes flash + redirect).

---

## 06. Estados reales — catálogo completo

Todos los `TextChoices`/`IntegerChoices` reales encontrados, con su
código, etiqueta en español, y transiciones válidas cuando se
documentaron explícitamente en `services.py`.

**inventory**: `Product.TrackingType` (quantity/serialized, no
intercambiable una vez con historial) · `StockMovement.MovementType`
(in/out/adjustment, append-only) · `InventoryUnit.Status` (9 valores:
en_stock, reservado, vendido, devuelto, reparacion, garantia, danado,
perdido, devuelto_proveedor — máquina de estados completa documentada
en `services.ALLOWED_UNIT_TRANSITIONS`, el `<select>` de la UI **no
filtra** por transición válida) · `ProductImportBatch.Status`
(pending_review/confirmed/failed).

**customers**: `party_type` (persona/empresa) · `identification_type`
(5 valores) · `payment_terms` (5 valores) · `DocumentCategory` (7
valores, compartido con Ventas/Compras/RRHH/Gastos) · `is_active` (bool,
baja lógica).

**sales**: `Quotation.status` (7 valores, draft único editable) ·
`ProformaInvoice.status` (5 valores) · `Sale.status` (5 valores) ·
`Sale.payment_status` (5 valores, **refunded/partially_refunded son
código muerto** — el cálculo automático nunca los produce) ·
`Payment.status` (confirmed/voided) · `PaymentAllocation.status`
(active/reversed) · `Refund.status` (pending/completed/failed — **sin
UI**) · `CreditNote.status` (5 valores, máquina de estados completa —
**sin UI**) · `CreditNoteApplication.status` (active/reversed) ·
`Reservation.status` (4 valores) · `PaymentMethod` (cash/card/transfer/
other, reutilizado por POS/Compras/Nómina/Portal de Billing).
`EXPIRED` de Cotización/Proforma/Reserva es **inalcanzable en uso
normal** (las funciones que lo asignarían no están conectadas a ningún
cron/comando/señal).

**pos**: `CashRegister.Status` (active/inactive) · `CashSession.Status`
(open/closed, con constraints DB reales de unicidad) ·
`CashMovement.MovementType` (12 valores, solo 3 seleccionables
directamente por el cajero).

**purchases**: `PurchaseOrder.Status` (6 valores, `RECEIVED` es
automático nunca manual, `CLOSED` es manual y terminal) ·
`SupplierInvoice.Status` (draft/confirmed/canceled) ·
`SupplierPayment.Status` (confirmed/voided — **anular sin UI**) ·
`SupplierPaymentAllocation.Status` (active/reversed).

**expenses**: `Expense.Status` (7 valores) · `ExpensePayment.Status`
(confirmed/voided) · `ExpenseRecurrence.Frequency` (4) ·
`ExpenseRecurrence.Status` (active/paused/canceled).

**hr**: `Employee.Status` (5 valores, transiciones validadas
server-side, `<select>` no las filtra) · `EmploymentContract.ContractType`
(4) · `EmploymentContract.Status` (4, nunca dos ACTIVE simultáneos) ·
`Attendance.Source` (manual/system, solo manual se genera hoy) ·
`Leave.Status` (4) · `Incident.IncidentType`/`Severity`/`Status` (4/4/4
— **Status nunca cambia desde la UI**, congelado en "Abierto").

**payroll**: `PayrollPeriod.Status` (6, con auto-transiciones
draft→processing y approved→paid) · `Payroll.Status` (4, recalculado
automáticamente en cada pago) · `PayrollLine.Category`/`Concept`
(2/9, una sola tabla deliberadamente, nunca 4 tablas separadas).

**accounting**: `Account.AccountType`/`NormalBalance` (6/2) ·
`AccountingPeriod.Status` (4 — **`CLOSING` nunca se asigna en ningún
flujo real**) · `JournalEntry.Status` (draft/posted, **nunca queda en
draft desde la UI** — siempre contabiliza en el mismo submit) ·
`AccountMapping.Key` (14 eventos de negocio contabilizables).

**approvals**: `ApprovalPolicy.Scope` (user/role/tenant) ·
`ApprovalRequest.ActionType` (13 valores) · `ApprovalRequest.Status`
(pending/approved/rejected/canceled/expired — **canceled sin botón,
expired sin flujo de UI en este módulo**).

**audit**: `AuditLog.Action` (28 valores, evento inmutable append-only,
`tenant` nullable a propósito).

**permissions**: sin `TextChoices` — configuración booleana
(`RolePermission.is_granted`/`UserPermissionOverride.is_granted`),
catálogo de permisos código-definido (`PERMISSION_CATALOG`, no en BD).

**api**: `ApiKey.Status`/`Integration.Status` (active/revoked, terminal)
· `Integration.Provider` (budun/other_erp/future, solo budun con
soporte real) · `Integration.is_enabled` (bool, reversible, independiente
del status).

**billing (Portal)**: `Subscription.Status` (6) · `SaaSInvoice.Status`
(5) · `PaymentProof.Status` (6, el Portal solo lee/crea, nunca cambia).

**tenants**: `Tenant.BillingStatus` (7, nunca editable desde un
formulario directo) · `Membership.Role` (6, sin pantalla de cambio de
rol en el alcance auditado).

---

## 07. Formularios — patrones transversales

- **Ningún módulo de negocio usa `ModelForm`** salvo `customers`
  (`CustomerForm`/`SupplierForm`) — el resto (`sales`, `pos`,
  `purchases`, `expenses`, `hr`, `payroll`, `accounting`) usa
  exclusivamente `forms.Form` planos; el guardado real SIEMPRE ocurre
  en `services.py`, nunca en `form.save()` — patrón deliberado y
  documentado con el mismo comentario textual en varios módulos.
- **Validación de negocio vive en `services.py`, no en `clean()`** en
  la mayoría de los casos — los `clean_*` de los forms cubren solo
  forma/tipo/unicidad simple; las reglas de transición de estado,
  solapamiento de fechas, límites de aprobación, etc. se validan al
  llamar al servicio y se reportan vía `messages.error`.
- **Un único partial de campo domina el proyecto**:
  `customers/_campo.html` (label + widget + ayuda + errores) es
  incluido por CASI todos los módulos auditados — Ventas, Compras,
  Gastos, RRHH, Nómina, Contabilidad, Reportes, Aprobaciones, API,
  Portal de Billing. Única excepción confirmada:
  `permissions/role_permissions.html`, que renderiza checkboxes con
  `<label style="">` inline.
- **Formsets** aparecen en: Notas de precio de Plan (fuera de alcance,
  SaaS), Checkout del POS (2 filas de pago), Recepción serializada de
  Compras (10 filas), Devoluciones de Ventas/Compras (una fila por
  línea elegible), Asientos contables (4 filas).
- **Validación de archivos adjuntos** centralizada:
  `apps.customers.file_validation.validar_archivo_adjunto` (extensión +
  firma binaria + máx. 10 MB) reutilizada literalmente por Ventas,
  Compras, Gastos, RRHH.

---

## 08. Tablas — patrón transversal

Todas las tablas de listado del ERP siguen el mismo esqueleto:
`.tabla-envoltorio` > `table.tabla` > `thead`/`tbody`, columna de
estado con `.badge` semántico, columna de acciones al final,
`.estado-vacio` (icono emoji + texto) cuando no hay filas. Paginación
real (`.paginacion`, 20/página) solo en listados con `ListView` +
`paginate_by` — confirmada en: Productos, Clientes, Proveedores,
Gastos, Empleados, Auditoría (50/página). Listados de catálogo simple
(Categorías, Departamentos, Cargos, Horarios, Tipos de ausencia,
Reservas, Facturas de proveedor sin filtro de estado) **no tienen
paginación ni buscador** — asumen volumen bajo.

Alineación de cifras monetarias: **ninguna tabla del ERP tenant usa
fuente tabular/monoespaciada** para montos — a diferencia del SaaS
Super Admin (ya migrado a `.u-cifra`/tabular-nums en FASE F-siguiente
de este mismo proyecto). Es una diferencia real de tratamiento
tipográfico a decidir en el rediseño del ERP.

---

## 09. Modales / diálogos — hallazgo cruzado crítico

**El ERP tenant NO usa modales (`<dialog>`/`.modal`) en ninguna
pantalla real auditada.** Confirmado explícitamente por 4 de los 6
agentes (POS, Inventory/Purchases — grep negativo en todo el árbol de
templates) y por ausencia de mención en los otros 2. El único lugar
donde `<dialog class="modal">` aparece en código real es
`core/design_system.html` — la página de REFERENCIA del Design System,
nunca una pantalla de negocio real.

**Todas las confirmaciones destructivas/irreversibles del ERP usan
`confirm()` nativo de JavaScript** inline en el botón (cancelar
carrito, eliminar categoría, desactivar producto/cliente/proveedor,
cancelar orden de compra, reversar asiento, cerrar período, cancelar
suscripción, etc.) — nunca un componente modal propio con overlay,
título, cuerpo e icono de alerta como sí existe y se usa extensamente
en el SaaS Super Admin (`.modal__encabezado--alerta`, ya documentado en
`docs/design-system-v1-hybrid.md`).

**Consecuencia directa para el rediseño**: introducir modales reales en
el ERP tenant (reutilizando el componente ya construido y aprobado
para el SaaS) sería una MEJORA DE UX real, no una migración 1:1 de algo
existente — debe tratarse explícitamente como tal, no asumirse como
"solo cambiar el estilo de lo que ya hay".

---

## 10. Permisos — matriz de protección real

| Módulo | Mecanismo dominante | Cobertura granular |
|---|---|---|
| core (Configuración) | `require_permission` manual | Solo la vista `SettingsHomeView` (`settings.view`) |
| accounts | Ninguno (login/pública) | N/A |
| dashboard | Ninguno (solo login, `TenantRequiredMixin` deliberadamente omitido) | Ninguna |
| inventory | `PermissionRequiredMixin` solo en import/export | 2 de ~21 vistas (`products.import`/`products.export`) |
| customers | `PermissionRequiredMixin` en TODAS las vistas | 15/15 vistas |
| sales | Ninguno más allá de login+tenant | 0 vistas |
| pos | `require_permission` solo en caja | 3 de ~20 (`cash.open`/`cash.close`/`cash.move`); `pos.use`/`cash.view` definidos en el catálogo pero **nunca invocados** |
| purchases | Ninguno más allá de login+tenant | 0 vistas |
| expenses | Ninguno más allá de login+tenant (autorización por monto vía `apps.approvals`, no por permiso) | 0 vistas |
| hr | Ninguno más allá de login+tenant (gating de sensibles es un caso especial, ver abajo) | 0 vistas de permiso granular |
| payroll | `require_permission` en TODAS las vistas | 100% (`payroll.view`/`.process`/`.approve`/`.pay`/`.sensitive.view`) |
| accounting | `require_permission` solo en 4 acciones sensibles | 4 de ~13 (`accounting.close_period`/`.reopen_period`/`.post`/`.reverse`) |
| reports | Ninguno (gating de nómina sensible es funcional, no un permiso) | 0 vistas |
| approvals | `can_user_approve()`/`require_role(OWNER)`, no `require_permission` | Mecanismo propio, no el catálogo estándar |
| audit | `require_permission` en TODAS las vistas | 100% (`audit.view`/`audit.export`) |
| permissions | `require_permission` en TODAS las vistas | 100% (`settings.manage`) |
| api (config+integraciones) | `require_permission` en TODAS las vistas | 100% — el módulo más estrictamente protegido del ERP |
| billing (Portal) | `require_permission` en TODAS las vistas | 100% (`billing.saas.view`/`.manage`) |

**Gating de datos sensibles** (mecanismo distinto de `require_permission`,
propio de cada dominio): `apps.hr.services.can_view_sensitive_employee_data`
(salario/banco — oculta el bloque Y el formulario de edición
server-side; **pero el formulario de ALTA de empleado no aplica el
mismo gate**, asimetría real) y `apps.payroll.services.can_view_sensitive_payroll_data`
(desglose de nómina — en RRHH solo se ocultan columnas, en Nómina la
página de detalle ENTERA exige el permiso, dos criterios deliberadamente
distintos y documentados como tales en el código).

---

## 11. Reportes — matriz de exportación real

| Reporte | Módulo | CSV | PDF | XLSX | Filtros preservados en el link de exportación |
|---|---|---|---|---|---|
| Ventas | reports | ✅ | ✅ | ✅ | Sí |
| Gastos | reports | ✅ | ✅ | ✅ | Sí |
| Cuentas por Cobrar | reports | ✅ | ✅ | ✅ | No |
| Cuentas por Pagar | reports | ✅ | ✅ | ✅ | No |
| Estado de Cuenta (Cliente) | reports | ✅ | ✅ | ✅ | No |
| Estado de Cuenta (Proveedor) | reports | ✅ | ✅ | ✅ | No |
| Inventario | reports | ✅ | ❌ | ❌ | — |
| Auditoría | audit | ✅ (máx. 10 000 filas) | ❌ | ❌ | — |
| Caja | reports | ❌ | ❌ | ❌ | — |
| Compras | reports | ❌ | ❌ | ❌ | — |
| RRHH | reports | ❌ | ❌ | ❌ | — |
| Nómina | reports | ❌ | ❌ | ❌ | — |
| Clientes (listado) | reports | ❌ | ❌ | ❌ | — |
| Proveedores (listado) | reports | ❌ | ❌ | ❌ | — |
| Balance de Comprobación | accounting | ❌ | ❌ | ❌ | — |
| Libro Mayor | accounting | ❌ | ❌ | ❌ | — |
| Libro Diario | accounting | ❌ | ❌ | ❌ | — |
| Balance General | accounting | ❌ | ❌ | ❌ | — |
| Estado de Resultados | accounting | ❌ | ❌ | ❌ | — |

Implementación real: `apps/reports/exports.py` — `pdf_response()`
(`reportlab`, A4/landscape según nº columnas, encabezado azul `#1e3a5f`,
filas alternas) y `xlsx_response()` (`openpyxl`) son **funciones
genéricas** (header+rows), nunca un exportador por-reporte; ambas pasan
cada celda por `sanitize_cell_value` (protección contra CSV/XLSX
Formula Injection). Toda exportación exitosa se audita
(`AuditLog.Action.EXPORT_PERFORMED`, resiliente — nunca rompe la
descarga). El PDF no incluye logo de tenant (`Tenant` no tiene campo de
branding todavía).

**Si el rediseño estandariza "todo reporte tiene exportación en 3
formatos", 12 de 18 reportes necesitan backend nuevo, no solo UI.**

---

## 12. POS — inventario completo

*(Sección íntegra ya producida por el agente dedicado — reproducida sin
alterar, es la fuente primaria para la futura FASE de rediseño profundo
del POS.)*

### Pantallas
1. **Terminal de venta (carrito)** — `pos:terminal_detail`. El carrito
   ES una `Sale` en `draft` (nunca sesión/memoria). Búsqueda de
   producto por texto/SKU/código de barras/IMEI-serie exacto (recarga
   completa de página, sin AJAX). Alertas de sesión de caja y de
   autorizaciones aprobadas pendientes de reintentar. Tabla de
   resultados con mini-form de agregar por fila. Tabla de carrito
   (Producto/Unidad/Cant./Precio/Descuento/Impuesto/Total/Quitar — sin
   edición de línea, solo agregar/quitar). KPIs de totales. Tarjetas
   de Cliente y Descuento global. Formset de pago (checkout).
2. **Cajas** (`pos:register_list`) — solo OWNER puede ver/crear.
3. **Abrir caja** / **Cerrar caja** / **Resumen de sesión**.
4. **Registrar movimiento de caja** — sin template ni botón en ninguna
   pantalla (URL huérfana).
5. **Cobros (buscar cliente)** / **Cobros de un cliente** — cuentas por
   cobrar: cobrar facturas pendientes (selección múltiple, distribución
   en orden), registrar anticipo, emitir nota de crédito, aplicar saldo
   a favor (**hardcodeado a la factura pendiente más antigua**, sin
   selector), reembolsar pagos (efectivo o convertir a saldo).

### Estados reales
`CashRegister.Status`, `CashSession.Status` (con constraints DB reales
de unicidad por caja y por usuario, incluso cruzando tenants),
`CashMovement.MovementType` (12 valores, solo 3 elegibles por el
cajero), más los estados de `Sale`/`Payment` reutilizados de `apps.sales`.

### Productos, carrito, clientes, pago, descuentos, impuestos
Ver detalle completo en el reporte del agente (ya trasladado en
secciones 04-07 de este documento) — puntos clave: sin categorías/
navegación visual, cambio calculado y restado del efectivo ANTES de
crear los Payments reales, descuento por línea y global con el mismo
flujo de aprobación "bloquear→solicitar→aprobar en otra pantalla→
reintentar" (nunca override in-context con PIN), sin desglose de
impuesto multi-tasa en el POS.

### Apertura/cierre de caja
Flujo completo documentado: abrir (valida caja activa + usuario
autorizado + sin sesión duplicada) → movimientos durante la sesión →
efectivo esperado siempre recalculado desde el ledger de `CashMovement`
(nunca un campo editado a mano) → cerrar (monto único tecleado,
**conteo por denominaciones NO implementado** — solo especificación en
`docs/currency.md`, cero código real) → genera asiento contable
Cash Over/Short.

### Tickets, devoluciones, modales, atajos
**Sin plantilla de ticket propia** (redirige a `sales:sale_receipt`,
fuera de `apps.pos`). **Sin devolución de mercancía** dentro de POS
(vive en `apps.sales`). **Cero modales.** **Cero JavaScript propio** —
todo el POS es server-rendered puro, cada acción es un POST+redirect de
página completa, sin AJAX/HTMX, sin atajos de teclado, sin indicador de
carga.

### Hallazgos específicos de POS
15 inconsistencias documentadas por el agente — las más relevantes para
el rediseño: (1) `cash_movement_create` sin botón en la UI; (2) `pos.use`/
`cash.view` definidos pero nunca aplicados; (3) aplicar saldo a favor
hardcodeado a una sola factura; (4) reembolso sin usar el partial de
campo estándar; (5) **el POS entero carece de cualquier capa de
interactividad cliente** — el hallazgo más relevante de cara al
rediseño, ya que hoy la experiencia del cajero implica múltiples
recargas completas de página por cada acción del carrito.

---

## 13. Integraciones — API de Inventario y Catalog API (pantallas de config)

Dos submódulos gemelos bajo `apps/api`, ambos dentro de Configuración:

- **API de Inventario** (`/configuracion/api-inventario/`) — UNA sola
  clave por tenant (`UniqueConstraint`), generar/rotar (reescribe la
  misma fila)/revocar (terminal)/scopes/probar conexión. Secreto
  mostrado en texto plano una única vez, en un `<pre>` copiable.
- **Integraciones (Catalog API)** (`/configuracion/integraciones/`) —
  un tenant puede tener VARIAS integraciones. Mismo patrón de
  secreto-una-vez, más `is_enabled` (interruptor reversible,
  independiente de `status`). Provider: solo `budun` tiene soporte
  real hoy (`other_erp`/`future` son valores de catálogo sin
  implementación).

Ambos submódulos son los más estrictamente protegidos por permisos
granulares de todo el ERP (14/14 vistas con `require_permission`). El
patrón "secreto mostrado una sola vez" está duplicado literalmente
entre las dos pantallas de detalle — candidato directo a componente
compartido en el rediseño.

Los endpoints REST reales (`/api/v1/`, `/api/v1/catalog/`) están fuera
de alcance de este documento (no son pantallas HTML).

---

## 14. Componentes compartidos actuales (inventario técnico, NO inspiración visual)

Confirmados por los 6 agentes de forma consistente en prácticamente
todos los módulos:

- **Layout**: `.shell`/`.sidebar`/`.sidebar__nav`/`.sidebar__enlace`,
  `.navbar`/`.navbar__toggle`/`.navbar__acciones`, `.main`/`.main__contenido`,
  `.migas` (breadcrumbs), `.encabezado-pagina`/`__descripcion`/`__acciones`.
- **Contenedores**: `.tarjeta`/`.tarjeta__cuerpo`/`.tarjeta__encabezado`/
  `.tarjeta__pie`, `.panel-seccion`/`.panel-seccion__titulo`.
- **Tablas**: `.tabla-envoltorio`/`.tabla`, `.paginacion`.
- **Formularios**: `.campo`/`.campo__ayuda`/`.errores` (vía
  `customers/_campo.html`, ver sección 07), `.visualmente-oculto`.
- **Estados/feedback**: `.badge` + 5 variantes (`--verde`/`--neutro`/
  `--azul`/`--advertencia`/`--peligro`) — vocabulario de color YA
  consistente en las 6 áreas auditadas; `.alerta` + 4 variantes;
  `.estado-vacio`/`.estado-vacio__icono` (emoji); `.toast` (mensajes
  flash de Django).
- **Navegación secundaria**: `data-tabs`/`.tabs__lista`/`.tabs__boton`/
  `.tabs__panel` (patrón ARIA completo, usado en detalles de Cliente,
  Proveedor, Cotización, Proforma, Venta, Gasto, Empleado, Orden de
  compra, Factura de proveedor); `.dropdown`/`.dropdown__menu`/
  `.dropdown__item` (solo en el navbar); `.kpi-grid`/`.kpi`/`.kpi__etiqueta`/
  `.kpi__valor` (Dashboard, POS, Contabilidad, Reportes, RRHH, Nómina).
- **Actividad**: `.lista-actividad`/`.actividad-lista` (bitácora por
  módulo — 7 tablas `*ActivityLog` casi idénticas, ver sección 15).
- **Botones**: `.btn` + variantes `--primario`/`--secundario`/
  `--contorno`/`--fantasma`/`--peligro`/`--sm`/`--lg`/`--bloque`/`--cargando`.
- **Confirmación destructiva**: `confirm()` nativo de JavaScript —
  NUNCA un modal (ver sección 09).
- **Iconografía**: emoji Unicode inline — NUNCA el sistema SVG
  (`ui_icons`) ya construido para el SaaS Super Admin.
- **Componente NO reutilizado consistentemente**: `role_permissions.html`
  es la única pantalla que no usa `_campo.html`.

---

## 15. Dependencias entre módulos

- `customers/_campo.html` — dependencia cruzada de CASI todo el
  proyecto (ver sección 07).
- `apps.sales.PaymentMethod` — reutilizado literalmente por `apps.pos`,
  `apps.purchases` (vía `SupplierPaymentForm`), `apps.payroll`.
- `DocumentCategory` (definido en `customers`) — reutilizado por
  Ventas, Compras, RRHH, Gastos para clasificar adjuntos.
- `validar_archivo_adjunto`/`nombre_original_seguro` (`apps.customers.file_validation`)
  — reutilizado por Ventas, Compras, Gastos, RRHH.
- `estado_badge` (filtro central, `apps/core/templatetags/ui_extras.py`)
  — mapea CUALQUIER estado crudo de CUALQUIER modelo (`Tenant.billing_status`,
  `Subscription.status`, `SaaSInvoice.status`, `PaymentProof.status`,
  `Sale.status`, etc.) al mismo vocabulario de 5 colores — punto único
  a tocar si el rediseño cambia la paleta semántica.
- `apps.approvals` — consumido por Compras (OC sobre el límite,
  sobre-recepción), Gastos (monto excedido), POS (descuento/crédito
  excedido), RRHH (aprobación de ausencias, por autoridad no por
  monto), Nómina (aprobación de período, por autoridad).
- `apps.hr.services.can_view_sensitive_employee_data` — consumido
  también por `apps.reports` (Reporte de RRHH/Nómina).
- 7 tablas `*ActivityLog` independientes (Sales, Customers→`ActivityLog`,
  Accounting, Expenses, HR, Payroll, Purchases) con forma casi idéntica
  — federadas por `apps.audit.services.search_audit_events` vía UNION
  SQL, nunca copiadas a una tabla nueva.
- Todos los formularios de reporte (`apps.reports.forms`) son
  `DateRangeFilterForm` o extensiones de él.

---

## 16. Inconsistencias — listado consolidado

**Funcionalidad construida sin UI (candidatos a pantalla nueva, no a
rediseño de algo existente):**
1. Notas de Crédito (`apps.sales.CreditNote`) — modelo + máquina de
   estados + servicios + tests completos, cero URL/vista/template.
2. Reembolsos (`apps.sales.Refund`) — mismo caso.
3. Anticipo a proveedor (`purchases:supplier_advance_create`) — pantalla
   completa construida, cero enlaces reales hacia ella.
4. `void_supplier_payment` — servicio+tests, sin vista/URL/botón.
5. `IncidentUpdateStatusView`/`IncidentResolutionForm` (RRHH) — existen,
   sin ningún control en la UI.
6. `pos:cash_movement_create` — URL/vista activa, sin formulario que
   apunte a ella en ninguna plantilla.
7. `approvals:approval_cancel` — mismo caso.
8. Conteo de caja por denominaciones (`CashDenominationCount`) —
   solo especificación en `docs/currency.md`, cero código real.

**Textos/UI desactualizados respecto al backend real:**
9. Dashboard: KPIs "Ventas del mes"/"Gastos del mes" y botones "Agregar
   producto"/"Registrar venta" siguen marcados "próximamente" pese a
   que Inventario y Ventas ya son módulos activos.
10. `core/settings_home.html`: subtítulo dice "(próximamente) la API de
    Inventario" pese a que esa pantalla ya está implementada y enlazada
    dos tarjetas más abajo en la misma página.
11. Historial de Cliente/Proveedor: estado vacío codificado
    permanentemente ("estará disponible desde FASE 10/12") pese a que
    `apps.sales`/`apps.purchases` ya existen.

**Estados de modelo nunca alcanzables desde la UI actual:**
12. `AccountingPeriod.Status.CLOSING`.
13. `ApprovalRequest.Status.EXPIRED` (sin flujo de UI en `apps.approvals`).
14. `Quotation`/`ProformaInvoice`/`Reservation` `.EXPIRED` — las
    funciones que los asignarían no están conectadas a ningún
    cron/comando/señal.
15. `Sale.payment_status` `refunded`/`partially_refunded` — el cálculo
    automático nunca los produce.

**Asimetrías de seguridad/gating:**
16. `EmployeeCreateView` (alta) NO aplica `can_view_sensitive_employee_data`
    pese a incluir salario/banco en el mismo formulario que sí lo gatea
    en edición.
17. Permisos granulares muy desiguales entre módulos (ver matriz
    completa, sección 10) — Ventas, Compras, Contabilidad (mayoría),
    Reportes, RRHH (permiso genérico), Dashboard sin protección
    granular pese a exponer acciones financieras sensibles en varios
    de ellos.

**Patrones de UI duplicados/rotos:**
18. `role_permissions.html` es la única pantalla que no reutiliza
    `customers/_campo.html`.
19. CSS de impresión (`.documento-imprimible`/`@media print`) copiado
    literalmente 3 veces (Cotización, Proforma, Recibo de venta) en vez
    de un partial compartido.
20. Patrón "secreto mostrado una vez" duplicado entre API de Inventario
    e Integraciones.
21. `password_change_form.html`/`_done.html` salen del shell ERP
    (`base.html` en vez de `layout_app.html`) pese a requerir sesión.
22. `<select>` de cambio de estado (Empleado, Unidad de inventario) no
    filtra opciones por transición válida — siempre muestra todas, el
    rechazo llega recién tras el submit.
23. Botones "Cancelar" de Orden de Compra/Factura de proveedor sin
    campo de motivo visible, aunque el backend lo acepta y audita.
24. Columna "Usuario" en Auditoría muestra el ID numérico crudo, no el
    nombre/email.
25. Nombres de dominio y códigos de permiso mostrados crudos (sin
    traducir) en `role_permissions.html`/`user_overrides.html`.
26. Cuenta bancaria del Portal de Billing mostrada sin enmascarar (a
    diferencia del admin, que sí la enmascara).
27. `IntegrationCreateView` renderiza directo en vez de redirigir tras
    POST exitoso — riesgo de reenvío de formulario al refrescar.

**Exportación desigual** — ver matriz completa, sección 11.

---

## 17. Riesgos para las fases siguientes (Design System / Design Lab / Implementación)

1. **Archivos CSS/JS compartidos con el SaaS Super Admin ya aprobado**
   (`static/css/base.css`, `static/css/design-system.css`,
   `static/js/ui.js`) — cualquier cambio de token/componente global
   para el ERP puede romper visualmente pantallas del SaaS ya cerradas
   y aprobadas fase por fase. El rediseño del ERP debe decidir
   explícitamente: ¿extiende este archivo con un modificador tipo
   `.shell--erp` (mismo patrón que `.shell--saas`), o construye tokens
   nuevos completamente aislados? Cualquiera de las dos opciones debe
   ser una decisión consciente, no un efecto secundario.
2. **Introducir modales reales en el ERP es una mejora de
   funcionalidad/UX, no una migración visual** (sección 09) — debe
   presentarse y aprobarse como tal, nunca colarse dentro de un
   "rediseño visual" sin que el usuario lo autorice explícitamente.
3. **Sustituir emoji por el sistema de iconos SVG ya construido** para
   el SaaS es deseable por consistencia, pero implica tocar CADA
   plantilla con un estado vacío (decenas) — alcance grande, a
   planificar como su propio bloque de trabajo, no como un cambio
   incidental.
4. **Las 8 funcionalidades construidas sin UI** (Notas de Crédito,
   Reembolsos, Anticipo a proveedor, anular pago de proveedor,
   resolución de incidentes, movimiento de caja manual, cancelar
   autorización, conteo por denominaciones) son trabajo NUEVO si se
   decide exponerlas — el rediseño no debe asumir que "ya existen en
   alguna parte" solo porque el modelo/servicio existe.
5. **Homogeneizar exportación de reportes** (12 de 18 sin algún
   formato) implica backend nuevo (`reportlab`/`openpyxl`, ya usados en
   el proyecto, sin dependencias nuevas) además de UI — no es un
   cambio solo visual.
6. **Homogeneizar permisos granulares** entre módulos es un cambio de
   seguridad/autorización real, fuera del alcance de un rediseño
   puramente visual — señalar la inconsistencia (ya documentada,
   sección 10) pero no "corregirla" dentro de una fase de diseño sin
   autorización explícita separada.
7. **El shell del Portal de Billing y el shell del ERP son el mismo**
   (`layout_app.html`) — cualquier cambio al shell del ERP afecta
   automáticamente las 4 pantallas del Portal de Billing; deben
   auditarse juntas cuando llegue su turno.
8. **`apps/tenants` no tiene pantallas pero sí un hueco de producto
   real** (selector de tenant activo) — si el rediseño decide agregar
   uno al navbar, es una funcionalidad nueva a diseñar desde cero, sin
   ninguna base de UI existente que "adaptar".
9. **POS es 100% server-rendered sin ninguna capa de interactividad
   cliente** — cualquier mejora de UX ahí (AJAX, atajos, edición de
   línea sin recarga) es trabajo funcional nuevo, reservado
   explícitamente para la FASE 7 (POS Lab + rediseño profundo) según el
   plan ya acordado, nunca para el rediseño visual general.

---

*Fin del ERP REDESIGN MAP. Generado a partir de 6 auditorías de solo
lectura ejecutadas en paralelo sobre el código Django real. Ningún
archivo de código fue modificado.*
