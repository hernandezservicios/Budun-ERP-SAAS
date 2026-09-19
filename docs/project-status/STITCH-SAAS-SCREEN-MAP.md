# Mapa de pantallas SaaS en Stitch — Budun ERP

> Registro pantalla-por-pantalla del proyecto Stitch **"Budun ERP"** (`projectId 8473502236243200686`). Una pantalla solo se marca **Aprobada** cuando fue inspeccionada visualmente (captura real descargada y vista, no solo el texto de respuesta de la herramienta). Ver [STITCH-SAAS-DESIGN-PROPOSAL.md](STITCH-SAAS-DESIGN-PROPOSAL.md) para el sistema de diseño completo.

## Master Shell (congelado, FASE 1 — no modificar)

### 1. Dashboard Super Admin Billing (Master)
- **screenId**: `a7cf5c0731344ff1a1ce69e1b0e9022d`
- **URL real**: `billing_admin:dashboard`
- **View**: `DashboardView`
- **Funcionalidad**: 12 KPIs reales, gráfico de línea (ingresos 6 meses), dona (estado de suscripciones), actividad reciente, últimas facturas, próximos vencimientos — todo desde `apps/billing/services/reports.py`.
- **Master Pattern**: Dashboard (es el propio patrón de referencia).
- **Componentes**: KPI cards, gráfico de línea, gráfico de dona, feed de actividad, 2 tablas/listas.
- **Diálogos**: ninguno.
- **Estados**: n/a (sin estados vacíos aplicables — siempre hay datos de plataforma).
- **Observaciones**: es la referencia visual MASTER del Master Shell (sidebar/topbar) para todas las demás pantallas.
- **Estado de aprobación**: **Aprobada** (Master Shell congelado por el usuario).

### 2. Tenants (listado)
- **screenId**: `0319a8ca956947b18f09ecaf83f9dfaa`
- **URL real**: `billing_admin:tenants_list`
- **View**: `TenantsListView`
- **Funcionalidad**: listado de solo lectura, `Tenant.objects.all().order_by("name")`.
- **Master Pattern**: Listado.
- **Componentes**: tabla de 4 columnas (Nombre, Estado de facturación, Activo, Acción), botón primario "+ Nuevo tenant" (navegación hacia Venta manual, sin flujo nuevo).
- **Diálogos**: ninguno en este estado.
- **Estados**: vacío no diseñado todavía.
- **Observaciones**: sin búsqueda/filtro/paginación — no existen en el código real.
- **Estado de aprobación**: **Aprobada** (Master Shell congelado por el usuario).

### 3. Detalle de Tenant (Cancelar suscripción)
- **screenId**: `cebc37bd583a46e29d6b1a5011d22545`
- **URL real**: `billing_admin:tenant_detail`
- **View**: `TenantDetailView`
- **Funcionalidad**: detalle de tenant + suscripción + hasta 20 facturas; POST con 4 acciones condicionales (activar/suspender/reactivar/cancelar) gateadas por `subscription.status`.
- **Master Pattern**: Detalle.
- **Componentes**: tarjeta de suscripción, botones de acción condicional, tabla de facturas recientes (4 columnas).
- **Diálogos**: "Cancelar suscripción" (mostrado en esta captura, copy exacto verificado).
- **Estados**: n/a.
- **Observaciones**: existe un segundo diálogo real no capturado todavía en ninguna Master Screen — "Suspender" (ver `tenant_detail.html`) — pendiente para una vista secundaria futura si se decide documentar ese estado también.
- **Estado de aprobación**: **Aprobada** (Master Shell congelado por el usuario).

### 3B. Detalle de Tenant — Estado normal (complementa a #3, sin modal)
- **screenId (vigente)**: `450834e2cb1d4d57afa82b42eca06907`
- **URL real**: `billing_admin:tenant_detail` (misma URL/view que #3 — es el mismo template, capturado sin ningún `<dialog>` abierto, sin overlay ni desenfoque).
- **Funcionalidad**: idéntica a #3. Se generó específicamente porque #3 solo mostraba el estado con el modal "Cancelar suscripción" abierto (fondo parcialmente cubierto por el scrim) y no servía como referencia autónoma y 100% nítida del layout completo.
- **Estado representado**: suscripción `active` — muestra únicamente los 2 botones reales que corresponden a ese estado (`Suspender`/`Cancelar`; ni `Activar` ni `Reactivar` aplican a una suscripción activa, correctamente omitidos).
- **Componentes**: miga de pan, cabecera con badge de estado de facturación + enlace a Cliente SaaS, tarjeta de Plan y Suscripción (plan/badge/precio/frecuencia/período actual/próxima renovación/cobro recurrente PayPal), 2 botones de acción, tabla "Facturas recientes" (3 columnas + acción "Ver").
- **Diálogos**: ninguno visible en esta captura (a propósito — es el complemento "sin modal" de #3, que sí muestra "Cancelar suscripción" abierto).
- **Observaciones**: NO reemplaza a #3 (que sigue siendo la Master Screen congelada con el diálogo abierto) — es una pantalla adicional, independiente, que sirve como referencia visual completa del layout base sin depender de contenido desenfocado detrás de un modal.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 4. Transferencias por verificar (Aprobar comprobante)
- **screenId**: `4bff1829d4ec47a3af888c57fe036527`
- **URL real**: `billing_admin:transfers_queue` (cola) / `billing_admin:proof_detail` (diálogo)
- **View**: vista de cola + `ProofDetailView`
- **Funcionalidad**: cola de comprobantes bancarios por verificar; diálogo de aprobación con aplicación real de pago.
- **Master Pattern**: Listado con aprobación.
- **Componentes**: tabla de 7 columnas, diálogo modal.
- **Diálogos**: "Aprobar comprobante" (copy y campos exactos verificados).
- **Estados**: n/a.
- **Observaciones**: existe también un flujo de rechazo (`reject`) en el código real, no diseñado todavía.
- **Estado de aprobación**: **Aprobada** (Master Shell congelado por el usuario).

### 5. Venta manual
- **screenId**: `598fbca7485d498a8afc604c7a42d735`
- **URL real**: `billing_admin:manual_sale`
- **View**: `ManualTenantSaleView`
- **Funcionalidad**: crea SaaSCustomer + Tenant + Owner + Membership + Subscription + primera factura en una sola operación atómica.
- **Master Pattern**: Formulario.
- **Componentes**: formulario de 3 secciones, 5 campos, 1 botón primario.
- **Diálogos**: ninguno (formulario de un solo paso, sin wizard).
- **Estados**: n/a.
- **Observaciones**: campo `plan_version` es un `ModelChoiceField` real sobre `PlanVersion.objects.filter(is_current=True, plan__is_active=True)`.
- **Estado de aprobación**: **Aprobada** (Master Shell congelado por el usuario).

## Pantallas adicionales (construcción incremental, FASE 1)

### 6. Clientes SaaS (listado)
- **screenId**: `f9a0d1209c2a4d4889b265d402c25cba`
- **URL real**: `billing_admin:customers_list`
- **View**: `CustomersListView`
- **Funcionalidad**: listado de solo lectura, `SaaSCustomer.objects.all().order_by("name")`.
- **Master Pattern**: Listado (variante de Tenants, sin botón de creación).
- **Componentes**: tabla de 4 columnas (Nombre, Correo, País, acción "Ver").
- **Diálogos**: ninguno.
- **Estados**: vacío real en código ("Sin clientes SaaS todavía") — no diseñado todavía en esta pantalla.
- **Observaciones**: sin búsqueda/filtro/paginación ni botón de creación — no existen en el código real (los clientes SaaS solo se crean automáticamente vía Venta manual). La vista de **detalle de cliente** (`customer_detail.html`: 2 listas + formulario inline "Emitir nota de crédito", sin diálogos) es una vista secundaria real, auditada pero **todavía no generada** — queda pendiente para un bloque futuro.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 7. Planes
- **screenId (estado normal, vigente)**: `225cfabbac2442779bd0f69bd0a24879`
- **screenId (estado modal "Nuevo plan" abierto, vigente)**: `07aa8a54d0f34c5bbd1ad90c9ee57902`
- **screenIds superados** (conservados sin borrar, no usar como referencia): `f6b8d64e75264ccb899b09792ebf4431` (v1, tenía el formulario "Nuevo plan" permanentemente abierto al pie de página — corregido), `9c977bb6c88145c59d44706e72476a3a` (v2, tenía un subtítulo inventado bajo el título — corregido).
- **URL real**: `billing_admin:plans_list` (GET+POST) / `billing_admin:plan_version_create` (POST, por plan)
- **View**: `PlansListView` + `PlanVersionCreateView`
- **Funcionalidad**: lista todos los `Plan` (sin filtro); por cada uno, todas sus `PlanVersion` (incluido histórico); crea nuevas versiones de precio (nunca edita in-place — un `UniqueConstraint` real garantiza solo una vigente por plan+frecuencia); crea planes nuevos.
- **Master Pattern**: nuevo — "tarjeta de entidad con formulario inline" + patrón de creación **listado → botón "+ Nuevo X" → modal centrado** (mismo patrón de disparador que "+ Nuevo tenant", pero aquí el destino es un modal real en vez de navegación a otra pantalla, porque el formulario de creación de Plan es real e inline en el código — a diferencia de Tenants, donde no existe ningún formulario de creación propio). Ver sección 10 del design proposal.
- **Componentes**: N tarjetas de plan (nombre + badge "Inactivo" condicional + slug + descripción + lista de versiones de precio con badge "Vigente" condicional + formulario inline de 3 campos "Nueva versión de precio"), botón de cabecera "+ Nuevo plan".
- **Diálogos**: "Nuevo plan" — modal centrado con scrim, título, formulario real de 8 campos (Nombre, Slug, Descripción, Activo, Orden, Máximo de usuarios, Máximo de productos, Características), botón de cierre (X), botones "Cancelar"/"Crear plan". El formulario "Nueva versión de precio" por plan sigue siendo inline (no es un modal, así es en el código real).
- **Estados**: vacío real "No hay planes registrados" (no diseñado todavía); "Sin precios configurados." por plan sin versiones (no diseñado todavía).
- **Observaciones**: confirmado que **no existe** acción de activar/desactivar ni editar un plan ya creado en el código real — `is_active` solo se define al crear. No se diseñó ese control porque no existe. Corrección de FASE 1 (esta entrega): se cambió el patrón de creación de "formulario siempre visible al pie de página" a "botón + modal", por pedido explícito del usuario — es un cambio puramente visual/de interacción en Stitch, el formulario sigue teniendo exactamente los mismos 8 campos reales de `PlanForm`.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 8. Suscripciones
- **screenId**: `b47ae738f948446a917a2f4017ea6018`
- **URL real**: `billing_admin:subscriptions_list`
- **View**: `SubscriptionsListView` (GET único, sin POST, sin acciones)
- **Funcionalidad**: listado de solo lectura de todas las `Subscription` de todos los tenants, vía `report_services.get_subscriptions_report()`.
- **Master Pattern**: Listado (mismo patrón que Tenants/Clientes) — sin acciones propias, con drill-down externo.
- **Componentes**: tabla de 6 columnas (Tenant, Plan, Frecuencia, Estado, Fin de período, acción "Ver").
- **Diálogos**: ninguno.
- **Estados**: 6 estados reales de `Subscription.Status` (Pendiente, Activa, Pago vencido (en gracia), Suspendida, Cancelada, Expirada); vacío real "No hay suscripciones registradas" (no diseñado todavía).
- **Observaciones**: hallazgo importante de la auditoría — el servicio real calcula un resumen de conteos por estado (`summary`), pero el template **nunca lo renderiza**; se omitió deliberadamente en el diseño para no inventar un componente que no existe en la pantalla real, aunque el dato exista en el backend. La acción "Ver" navega a Detalle de Tenant (SAAS-03) — no existe una vista de detalle de suscripción propia. Las acciones de cancelar/suspender/reactivar viven en esa pantalla, no aquí.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 9. Facturas
- **screenId**: `c98adaa63a96442ea42a9acbe35c0fa6`
- **URL real**: `billing_admin:invoices_list` (GET único)
- **View**: `InvoicesListView` — `SaaSInvoice.all_objects.select_related("tenant").order_by("-issue_date")[:100]`
- **Funcionalidad**: listado de solo lectura de las últimas 100 facturas de todos los tenants.
- **Master Pattern**: Listado (mismo patrón que Tenants/Clientes/Suscripciones).
- **Componentes**: tabla de 6 columnas (Número, Tenant, Total con moneda, Vencimiento, Estado, acción "Ver").
- **Diálogos**: ninguno.
- **Estados**: 5 estados reales de `SaaSInvoice.Status` (Borrador, Pendiente, Pagada, Parcialmente pagada, Anulada); vacío real "Sin facturas todavía" (no diseñado todavía).
- **Observaciones**: el tope de 100 filas es un límite de código (`[:100]`), no una paginación de UI — no se diseñó ningún control de paginación porque no existe. Existe una vista de detalle real (`invoice_detail.html`: cabecera + líneas + resumen económico + pagos aplicados + notas de crédito aplicadas, GET único, sin acciones ni diálogos) — no se generó en este bloque por no tener ningún estado interactivo que verificar; queda como vista secundaria pendiente para un bloque futuro. Confirmado que no existen acciones de descargar/anular/marcar pagada/registrar pago/emitir nota de crédito en esta pantalla.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 10. Pagos
- **screenId**: `2462bada8e1947738933c6b50ef879d2`
- **URL real**: `billing_admin:payments_list` (GET) / `billing_admin:request_refund` (POST, por pago)
- **View**: `PaymentsListView` + `RequestRefundView`
- **Funcionalidad**: listado de solo lectura de los últimos 100 pagos de todos los tenants; solicita reembolso total de un pago (delegado a `refund_services.request_billing_refund`).
- **Master Pattern**: Listado con acción condicional + diálogo de confirmación (mismo patrón que Transferencias, SAAS-04).
- **Componentes**: tabla de 7 columnas (Tenant, Fecha, Método, Referencia, Monto, Estado, acción condicional "Reembolsar total").
- **Diálogos**: "Reembolsar pago" — modal de **solo confirmación, sin campos de formulario** (aunque `RefundRequestForm` acepta monto/motivo opcionales, el template real no los expone como inputs). Copy real: "Se solicitará el reembolso total de {monto} {moneda} ({método}) del tenant {tenant}. ¿Confirmas el reembolso?" — botones "Cancelar"/"Sí, reembolsar".
- **Estados**: 5 estados reales de `SaaSPayment.Status` (Pendiente, Confirmado, Fallido, Reembolsado, Parcialmente reembolsado). 3 métodos reales de `SaaSPayment.Method` (PayPal, Transferencia bancaria, Otro (manual)) — sin tratamiento visual diferenciado por método.
- **Observaciones**: el botón "Reembolsar total" es condicional — solo aparece si `status` es `confirmed` o `partially_refunded`; confirmado y respetado en el diseño (no todas las filas lo muestran). Sin resumen/KPIs, sin filtros, sin paginación, sin "Ver pago"/"Ver factura"/"Descargar comprobante"/"Anular" — ninguna de esas acciones existe en esta pantalla real.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 11. Transferencias — Detalle de comprobante
- **screenId**: `af93766957d040d1a04d87d09a195053`
- **URL real**: `billing_admin:proof_detail` (GET+POST)
- **View**: `ProofDetailView`
- **Funcionalidad**: muestra el detalle completo de un `PaymentProof`; aprueba (con `select_for_update()` real, protegido contra aprobar un ya `APPROVED` y contra condiciones de carrera) o rechaza (misma protección, exige motivo) el comprobante — distinto de SAAS-04 (que solo cubre la cola + el diálogo de aprobación superpuesto sobre la tabla).
- **Master Pattern**: Detalle con acciones condicionales + 1 diálogo modal + 1 acción inline sin modal (mismo espíritu que Tenant Detail, pero con una mezcla de modal y formulario inline que no existe en ninguna otra Master Screen).
- **Componentes**: tarjeta de detalle (tenant, factura, monto declarado, cuenta receptora, banco de origen declarado, referencia, fecha de envío, enlace real de descarga del archivo), badge de estado, "← Volver a transferencias".
- **Acciones reales**: "Aprobar" (abre modal) y "Rechazar" (formulario inline con input de motivo, SIN modal — confirmado en el template real) — ambas condicionadas a `status` en `submitted`/`under_review`.
- **Diálogos**: "Aprobar comprobante" — copy real: "Se aplicará un pago de {monto} a la factura {número} de {tenant}, activando su suscripción si corresponde. ¿Confirmas la aprobación?", botones "Cancelar"/"Sí, aprobar".
- **Estados**: 6 estados reales de `PaymentProof.Status` (Pendiente, Enviado, En revisión, Aprobado, Rechazado, Reversado); condicional muestra revisor+fecha+motivo si Rechazado, revisor+fecha si Aprobado.
- **Observaciones**: "Rechazar" NO tiene diálogo de confirmación en el código real — es un submit directo con un input de texto obligatorio (motivo). No se debe representar como modal aunque visualmente parezca más consistente hacerlo así. Descarga del comprobante es una acción real (enlace protegido, no archivo estático) y debe representarse.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 12. Notas de crédito
- **screenId**: `224eff0f2cab4a92b0d2e2f349bc7318` _(v2 — corregida por densidad visual, ver observación de ajuste)_
- **screenId superado** (conservado sin borrar, no usar como referencia): `5f893d9ea9e946a998f8fbc3f7cea8a6` (v1 — filas excesivamente espaciadas, con aspecto de tarjeta por fila; corregido)
- **URL real**: `billing_admin:credit_notes_list` (GET único)
- **View**: `CreditNotesListView`
- **Funcionalidad**: listado de solo lectura de las últimas 100 notas de crédito de todos los tenants, con saldo disponible calculado en tiempo real vía `credit_services.get_unapplied_credit_note_amount`.
- **Master Pattern**: Listado simple — sin ninguna acción por fila (la única Master Screen del bloque sin drill-down ni botón alguno).
- **Componentes**: tabla de 7 columnas (Número, Tenant, Fecha, Monto, Saldo disponible, Estado, Motivo) — sin columna de acción.
- **Diálogos / Formularios**: ninguno en esta pantalla. La emisión de notas de crédito ocurre desde otra pantalla (Detalle de Cliente, SAAS-06) y no se duplica aquí.
- **Estados**: 3 estados **derivados en el template** (no un campo real de `CreditNote`, que no tiene `status`): "Disponible" (verde), "Parcialmente aplicada" (ámbar), "Aplicada totalmente" (neutro/gris) — calculados comparando saldo disponible contra el monto.
- **Observaciones**: sin filtros/búsqueda/paginación/acciones — confirmado. `CreditNote` es inmutable una vez emitida (nunca se cancela), por eso no existe ningún estado de "cancelada" ni acción de anulación en esta pantalla. **Ajuste visual (v2, sin cambio funcional)**: la v1 mostraba filas demasiado espaciadas verticalmente (~200px/fila, aspecto de tarjeta individual); se corrigió a una tabla compacta y continua (~65-70px/fila, un solo borde sutil entre filas, misma tipografía, mismos 7 campos/estados/datos), en línea con la densidad de Suscripciones/Facturas/Pagos.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 13. Reembolsos
- **screenId**: `e30f24f004304345bf7beee1792aded9`
- **URL real**: `billing_admin:refunds_list` (GET) / `billing_admin:complete_refund` (POST, por reembolso)
- **View**: `RefundsListView` + `CompleteManualRefundView`
- **Funcionalidad**: listado de solo lectura de los últimos 100 reembolsos de todos los tenants; marca un reembolso manual pendiente como completado (`refund_services.complete_manual_refund`).
- **Master Pattern**: Listado con acción condicional + diálogo de confirmación (mismo patrón que Transferencias/Pagos).
- **Componentes**: tabla de 7 columnas (Tenant, Pago, Fecha, Monto, Motivo, Estado, acción condicional "Marcar completado").
- **Diálogos**: "Marcar reembolso como completado" — copy real: "Confirma que el reembolso de {monto} del tenant {tenant} ya fue procesado manualmente (ej. transferencia bancaria) fuera del sistema. Esta acción marca el pago original como reembolsado y no se puede deshacer. ¿Confirmas?" — botones "Cancelar"/"Sí, marcar completado", sin campos de formulario.
- **Estados**: 3 estados reales de `BillingRefund.Status` (Pendiente, Completado, Fallido).
- **Observaciones**: la condición real del botón "Marcar completado" es doble — `status == "pending"` **Y** `not paypal_transaction_id` (solo reembolsos manuales pendientes; los de PayPal no muestran este botón aquí). Sin filtros/búsqueda/paginación/KPIs.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 14. Cuentas bancarias
- **screenId (estado normal, vigente)**: `1ea96a5527f046528b0099b29a026bd4`
- **screenId (modal "Nueva cuenta" abierto, vigente)**: `1bc1d91c79b84ec3ac218d5393ad94c4`
- **screenIds superados** (conservados sin borrar, no usar como referencia): `4c0283ddc8904642b2f97bbc633d5673` (v4 normal) y `7fe7e1eac3164b2095b35e94cf1100fd` (v4 modal) — números de cuenta enmascarados con puntos (ej. "····15616"), corregido por pedido explícito del usuario (mostrar visible-pero-enmascarado NO es "completo"); `af9259e966a24398817e02fe179c880b` (intento v5-a, normal) — al desenmascarar el número perdió por completo la columna "Acciones" (sin botones); `9b17884bc0234ce295505ff33b72fdba` (intento v5-a, modal, mismo problema de fondo); `42b3d2e4ee8346b385bcc1bf144647be` (intento v5-b, normal) — la columna "Acciones" quedó parcialmente cortada por overflow horizontal de la tabla; `2887ed4d248643688b11570e1c82974f` (v2 — formulario "Nueva cuenta" siempre visible al pie en vez de modal, corregido), `c0cfc4903d02436285e5453fff8ae9b4` (v1 — 2 subtítulos inventados, corregido)
- **URL real**: `billing_admin:bank_accounts_list` (GET+POST, crear) / `billing_admin:bank_account_update` (POST, por cuenta) / `billing_admin:bank_account_toggle_active` (POST, por cuenta)
- **View**: `BankAccountsListView` + `BankAccountUpdateView` + `BankAccountToggleActiveView`
- **Funcionalidad**: lista todas las `BankAccount` (nivel plataforma, no tenant-scoped); crea una cuenta nueva (`BankAccountForm`, mismo formulario que editar); edita una cuenta existente (modal real); activa/desactiva una cuenta (acción directa, sin confirmación) — nunca borrado físico (protegido por `PaymentProof.bank_account` con `on_delete=PROTECT`).
- **Master Pattern**: Listado con 2 acciones por fila (una con modal de edición, una sin confirmación) + patrón de creación **listado → botón "+ Nueva cuenta" → modal centrado** (mismo patrón que Planes/"+ Nuevo plan" — corrección de FASE 1 sobre la v2, que presentaba el formulario siempre visible al pie en vez de modal; el formulario real de creación sigue siendo exactamente el mismo, solo cambió su presentación visual de inline a modal, por decisión explícita del usuario).
- **Componentes**: tabla compacta de 7 columnas (Banco, País, Moneda, Titular, Cuenta, Estado, acción con 2 botones) con `table-layout` fijo por presupuesto de ancho (Banco 14%, País 11%, Moneda 7%, Titular 16%, Cuenta 26%, Estado 9%, Acciones 17% con mínimo de 180px reservados) — Banco/Titular pueden truncar con ellipsis si el nombre es largo, Cuenta y Acciones nunca; párrafo explicativo real bajo la tabla, botón de cabecera "+ Nueva cuenta".
- **Formularios reales**: `BankAccountForm` (9 campos: bank_name, country, currency, account_holder, account_number, account_type, is_active, priority, notes) — el mismo formulario se reutiliza para crear (ahora en modal) y para editar (modal, ya existente en el código real).
- **Diálogos**: "Nueva cuenta" — modal centrado con scrim, título, los 9 campos reales, botón de cierre (X), botones "Cancelar"/"Crear". "Editar cuenta bancaria" (modal real del código, mismos 9 campos, no capturado visualmente en este bloque — análogo al de creación).
- **Estados**: solo `is_active` booleano (Activa/Inactiva) — no hay más estados reales.
- **Observaciones**: el botón "Activar" es azul sólido `#2563EB` y "Desactivar" es rojo sólido `#DC2626` (sin confirmación para ninguno — acción directa, correcto). CORRECCIÓN FINAL de máscara: el usuario aclaró que un número visible-pero-enmascarado (ej. "····15616") NO cuenta como "completo" — se regeneró la columna "Cuenta" para mostrar el dato íntegro (todos los dígitos, sin `***`/`····`/`••••`/`...`/ellipsis/truncamiento CSS de ningún tipo), verificado por inspección visual directa (zoom sobre la captura real) de ambas vistas. Al desenmascarar el número, dos intentos previos rompieron la columna "Acciones" (desapareció por completo en un caso, quedó cortada por overflow horizontal en otro) — la versión vigente resuelve esto con un presupuesto de ancho fijo por columna (`table-layout: fixed`, ver Componentes) que reserva 180px mínimo intocables para Acciones y permite truncar con ellipsis únicamente Banco/Titular (nunca Cuenta) si hace falta liberar espacio. Verificado visualmente que la tabla no genera overflow/scroll horizontal y que ambos botones de cada fila ("Editar" + "Activar"/"Desactivar") se ven completos, con su tamaño, color y posición sin cambios respecto a la versión previamente aprobada.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 15. Reportes
- **screenId (vigente)**: `921073fb9c7e4aaabfc93e08420e61c3`
- **URL real**: `billing_admin:reports` → `/plataforma/billing/admin/reportes/` (`apps/billing/admin_urls.py:31`)
- **View**: `ReportsView` (`apps/billing/admin_views.py:529-541`) — solo GET, solo superusuario (`SuperuserRequiredMixin`), sin queryset/filtro propio (delega en `apps.billing.services.reports`).
- **Funcionalidad**: pantalla de solo lectura, sin filtros, sin exportación, sin paginación, sin acciones, sin modales, sin formularios. Agrega datos de TODOS los tenants (`all_objects`, vista de plataforma).
- **Master Pattern**: Listado de solo lectura, 2 secciones independientes (cada una con línea resumen + tabla continua), sin acción alguna en ninguna fila — patrón nuevo, distinto a todos los anteriores (ningún otro Master Screen carece de acción por completo).
- **Componentes**: Sección "Ingresos" (resumen "Total: $ · Pagos: N" + tabla 5 columnas: Fecha, Tenant, Plan, Método, Monto) y Sección "Antigüedad de facturas pendientes de pago" (resumen de 4 buckets de días, con formato moneda aplicado visualmente aunque el template real no le aplica el filtro `|monto` — decisión de fidelidad visual, no de funcionalidad — + tabla 5 columnas: Número, Tenant, Vencimiento, Total, Días vencido).
- **Formularios reales**: ninguno.
- **Diálogos**: ninguno.
- **Estados**: sin badges de estado condicional en ninguna fila; datos de ejemplo usados solo para composición visual (no representan el estado vacío real, que es "Sin pagos." / "Sin facturas pendientes.").
- **Observaciones**: la vista calcula además `resumen_dashboard` y `suscripciones`, pero el template real nunca los renderiza — deliberadamente omitidos del diseño (código muerto en la vista real, no un componente a construir). No existe exportación PDF/XLSX en esta pantalla (esa capacidad vive únicamente en `apps.reports`, dominio ERP tenant-scoped no relacionado).
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 16. PayPal
- **screenId (vigente)**: `939a54322d804cb0916af7ffe7ebe718`
- **URL real**: `billing_platform:status` → `/plataforma/billing/paypal/` (`apps/billing/urls.py`) — **namespace `billing_platform`, NO `billing_admin`** (hallazgo de auditoría: el link "PayPal" del sidebar apunta a un árbol de URLs hermano y separado, `apps/billing/platform_views.py`, aunque comparte el mismo shell visual).
- **View**: `GatewayStatusView` (`apps/billing/platform_views.py`) — GET+POST, solo superusuario (`SuperuserRequiredMixin`). POST con `accion=probar_conexion` o `accion=alternar_habilitado`.
- **Funcionalidad**: estado del gateway PayPal de plataforma (singleton `PayPalGatewayStatus`) + últimas 20 `PayPalTransaction`. Probar conexión real (OAuth2 contra PayPal), habilitar/deshabilitar el checkout, iniciar un cobro de prueba (navega a una pantalla aparte, `checkout_create.html`, no incluida en este screenId), ver detalle de una transacción (`transaction_detail.html`, no incluida en este screenId — pantalla aparte con reembolso condicional).
- **Master Pattern**: Tarjeta de estado (labels + valores + badges + 3 acciones sin confirmación) + tabla continua de solo lectura con acción "Ver" por fila.
- **Componentes**: banner de advertencia de una línea (herramienta de operación/prueba, no activa suscripciones), tarjeta "Estado del gateway" (Ambiente/Checkout/Última prueba + botones "Probar conexión"/"Deshabilitar checkout"/"Iniciar un cobro de prueba"), tabla "Últimas transacciones" (7 columnas: Tenant, Plan, Propósito, Monto, Estado, Creada, acción "Ver").
- **Formularios reales**: ninguno en esta pantalla (los botones de la tarjeta de estado son POST con input oculto, no Django Forms; `CheckoutCreateForm`/`RefundForm` pertenecen a las pantallas aparte de crear cobro / detalle de transacción).
- **Diálogos**: ninguno — ni "Probar conexión" ni "Deshabilitar/Habilitar checkout" tienen confirmación en el código real (a diferencia de otras acciones destructivas del proyecto).
- **Estados**: `PayPalTransaction.Status` tiene 8 valores reales (Creada, Captura pendiente, Confirmada, Fallida, Cancelada, Reembolso pendiente, Reembolsada, Reembolso fallido) — se representaron 4 de ejemplo (Confirmada, Captura pendiente, Fallida, Reembolsada) para mostrar variedad de badges sin inventar un 9° estado.
- **Observaciones — corrección de texto explicativo**: se eliminó el subtítulo largo real bajo el h1 ("Estado del gateway, prueba de conexión y transacciones de PayPal de la plataforma.") y se condensó el banner de advertencia real (3 frases) a una sola línea, por pedido explícito del usuario ("regla visual limpia") — el contenido funcional (la advertencia de que esta herramienta no activa suscripciones) se conservó, solo se redujo la redacción.
- **⚠️ Hallazgo crítico pendiente de decisión del usuario, aplicable a TODAS las pantallas SaaS (no solo esta)**: `templates/layout_saas_admin.html` (verificado línea por línea) tiene una estructura de sidebar real distinta a la usada en el Master Shell congelado de SAAS-01 a SAAS-16: marca real "Budun SaaS" + subtítulo "Plataforma — Super Admin" (no "Budun ERP" sin tagline); grupos reales "Clientes y empresas" (Clientes/Tenants/**Venta manual**), "Suscripciones y planes" (Suscripciones/Planes — sin Venta manual), "Facturación" (igual), "Reportes" (igual), "Configuración" (Cuentas bancarias **+** PayPal (plataforma), mismo grupo) — no existen grupos "COMERCIAL"/"FINANZAS"/"INTEGRACIONES" ni un ítem final solitario "Configuración" en el código real. El usuario decidió explícitamente (2026-09-15) mantener el Master Shell ya congelado para SAAS-16 por consistencia visual con las pantallas anteriores, dejando esta corrección para una fase dedicada futura — no se modificó ninguna pantalla anterior.
- **✅ Corrección funcional real aplicada (2026-09-15, fuera de Stitch)**: durante la auditoría de SAAS-17 se confirmó que "Mi perfil" en el menú del avatar llevaba a `accounts:perfil` (shell ERP, `layout_app.html`) y existía un enlace "Salir a mi ERP" (`dashboard:panel`) — ambos mezclaban el contexto SaaS con el del ERP del tenant, algo que el propio comentario del código en `layout_saas_admin.html` prohíbe explícitamente. Por instrucción directa del usuario, se corrigió el CÓDIGO REAL (no Stitch): se eliminó "Salir a mi ERP"; se agregó `SuperAdminProfileView` (`apps/billing/admin_views.py`, reutiliza 100% de `apps.accounts.views.ProfileView` — mismo `ProfileForm`/mismos 3 campos, sin duplicar lógica) montada en `billing_admin:profile` (`/plataforma/billing/admin/perfil/`), con su propio template `apps/accounts/templates/accounts/perfil_saas.html` (extiende `layout_saas_admin.html`, sin la tarjeta de tenant/empresa — perfil del Super Admin nunca mezcla datos de tenant); "Mi perfil" en `layout_saas_admin.html` ahora apunta ahí. `accounts:perfil`/`ProfileView`/`perfil.html` originales quedaron sin ningún cambio (siguen sirviendo igual a los usuarios ERP normales). Archivos modificados (ronda 1): `templates/layout_saas_admin.html`, `apps/billing/admin_urls.py`, `apps/billing/admin_views.py`, `apps/accounts/templates/accounts/perfil_saas.html` (nuevo), `apps/billing/tests/test_ui_saas_shell.py` (+4 tests).
- **✅ Corrección funcional real, ronda 2 (2026-09-15)**: la ronda 1 dejó "Mi perfil" dentro del shell SaaS, pero "Cambiar contraseña" seguía usando `accounts:password_change`/`password_change_form.html` (extiende `base.html`, sin sidebar) cuyo "volver" y cuyo `password_change_done.html` regresaban a `accounts:perfil` (shell ERP) — una fuga de navegación residual. Corregido con el mismo patrón: `SuperAdminPasswordChangeView`/`SuperAdminPasswordChangeDoneView` (`apps/billing/admin_views.py`, reutilizan 100% el `PasswordChangeForm`/lógica real de Django vía `apps.accounts.views.AccountPasswordChangeView`/`...DoneView` — sin duplicar lógica de autenticación) montadas en `billing_admin:password_change`/`billing_admin:password_change_done`, con templates nuevos `password_change_form_saas.html`/`password_change_done_saas.html` (extienden `layout_saas_admin.html`, "volver" siempre apunta a `billing_admin:profile`, nunca a `accounts:perfil`). El menú del avatar y el pie de `perfil_saas.html` ahora enlazan a `billing_admin:password_change`. `accounts:password_change`/`accounts:perfil`/sus templates originales quedaron sin ningún cambio (el ERP sigue exactamente igual, verificado con test dedicado). Archivos adicionales modificados: `apps/accounts/templates/accounts/password_change_form_saas.html` (nuevo), `apps/accounts/templates/accounts/password_change_done_saas.html` (nuevo), `templates/layout_saas_admin.html`, `apps/accounts/templates/accounts/perfil_saas.html`, `apps/billing/tests/test_ui_saas_shell.py` (+5 tests más). Verificado con `manage.py check` + suite completa (136 tests, todos en verde: 127 originales + 9 nuevos entre ambas rondas). El menú del avatar SaaS ahora contiene exactamente 3 ítems (Mi perfil/Cambiar contraseña/Cerrar sesión), los 3 dentro del contexto SaaS, sin ningún "Salir a mi ERP". El resto del hallazgo de arriba (agrupación de "COMERCIAL"/"FINANZAS"/"INTEGRACIONES" vs. la agrupación real del código) sigue pendiente, sin tocar.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 16B. PayPal — Detalle de transacción
- **screenId (vigente)**: `66a19f469aaa4eb393f05f61fe2ea806`
- **URL real**: `billing_platform:transaction_detail` → `/plataforma/billing/paypal/transacciones/<int:pk>/` (destino real del botón "Ver" de la tabla de SAAS-16).
- **View**: `TransactionDetailView` (`apps/billing/platform_views.py:94-125`) — GET+POST, solo superusuario. POST solo para el formulario de reembolso.
- **Funcionalidad**: detalle de una `PayPalTransaction` (identificación, estado, monto interno y reportado por PayPal, IDs de orden/captura/reembolso), aviso condicional si no tiene un `SaaSPayment` real asociado (`tiene_saas_payment=False`), reembolso condicional (solo si `status == "confirmed"`), historial de hasta 20 `PayPalWebhookEvent` de esa transacción.
- **Master Pattern**: Detalle administrativo de solo datos + 1 acción condicional sin confirmación (mismo espíritu que Tenant Detail, pero sin diálogo modal — el reembolso es un submit directo, a diferencia de Suspender/Cancelar en Tenant Detail que sí confirman).
- **Componentes**: tarjeta de detalle (título + badge de estado + Tenant/Plan/Propósito + Ambiente + Monto interno + Monto reportado por PayPal condicional + Orden/Captura/Reembolso en formato código), banner ámbar condicional ("sin SaaS Payment asociado"), tarjeta "Reembolsar" condicional (`RefundForm`: Monto opcional + Motivo opcional + botón rojo), tabla "Eventos de webhook" (4 columnas: Tipo, Estado, Recibido, Procesado).
- **Formularios reales**: `RefundForm` (2 campos: `amount` opcional, `reason` opcional) — el único formulario de esta pantalla, solo visible si la transacción está `confirmed`.
- **Diálogos**: ninguno — el botón "Reembolsar" es un submit directo, sin confirmación modal (confirmado en el template real).
- **Estados**: los 8 valores reales de `PayPalTransaction.Status` (se representó "Confirmada"/verde); los 6 valores reales de `PayPalWebhookEvent.Status` (se representaron "Procesado"/verde y "Recibido"/ámbar).
- **Observaciones — corrección de color de badge encontrada durante esta auditoría**: `apps/core/templatetags/ui_extras.py` mapea `refunded` → **azul** ("informativo, dinero devuelto, ni éxito ni error"), no gris/neutro. La pantalla SAAS-16 (screenId `939a54322d804cb0916af7ffe7ebe718`) usó gris para su fila de ejemplo "Reembolsada" — **color incorrecto, pendiente de corrección en una pasada dedicada futura**, no se tocó esa pantalla en este turno por instrucción explícita del usuario ("no tocar la pantalla principal salvo que sea estrictamente necesario para identificar el destino del botón Ver"). Aplicado correctamente aquí: no se usó "refunded" en esta pantalla (se representó "confirmed", que sí es verde).
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 17A. Mi perfil (Super Admin, contexto SaaS)
- **screenId (vigente)**: `4eaa69ab687b4d928822e5855bf2cc56`
- **URL real**: `billing_admin:profile` → `/plataforma/billing/admin/perfil/` (`SuperAdminProfileView`, agregada en la corrección funcional documentada en la entrada #16 — reutiliza `apps.accounts.views.ProfileView`/`ProfileForm` al 100%). GET+POST, solo superusuario.
- **Funcionalidad**: editar los datos personales del Super Admin. Se alcanza desde el menú del avatar del topbar, no desde el sidebar — por eso ningún ítem del sidebar aparece activo en esta pantalla.
- **Master Pattern**: Formulario simple de una sola tarjeta (label+valor+campo), sin acciones condicionales.
- **Componentes**: tarjeta "Datos personales" con el `ProfileForm` real (3 campos: Nombre, Apellido, Correo electrónico), botón "Guardar cambios", enlace "Cambiar contraseña" en el pie de la tarjeta.
- **Formularios reales**: `ProfileForm` (`first_name`/`last_name`/`email` — sin más campos; sin avatar, sin tenant/empresa, confirmado por auditoría directa del form).
- **Diálogos**: ninguno.
- **Estados**: ninguno (no hay badges ni estados condicionales en esta pantalla).
- **Observaciones**: deliberadamente NO incluye la tarjeta de tenant/empresa que sí tiene el `perfil.html` original del ERP (el perfil del Super Admin nunca mezcla datos de tenant, por instrucción explícita del usuario).
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 17B. Cambiar contraseña (Super Admin, contexto SaaS)
- **screenId (vigente)**: `c9105581bd684818b59be1b414de4737`
- **URL real**: `billing_admin:password_change` → `/plataforma/billing/admin/perfil/contrasena/` (`SuperAdminPasswordChangeView`, reutiliza `django.contrib.auth.forms.PasswordChangeForm` estándar de Django al 100%). GET+POST, solo superusuario.
- **Funcionalidad**: cambiar la contraseña del Super Admin sin salir del contexto SaaS.
- **Master Pattern**: Formulario simple de una sola tarjeta.
- **Componentes**: tarjeta con el `PasswordChangeForm` real (3 campos: Contraseña actual, Contraseña nueva, Confirmación de la contraseña nueva — el template no renderiza `field.help_text`, así que no se muestran requisitos de contraseña), botón "Cambiar contraseña", enlace "← Volver a mi perfil".
- **Formularios reales**: `PasswordChangeForm` (estándar de Django, sin `form_class` propio).
- **Diálogos**: ninguno.
- **Estados**: ninguno.
- **Observaciones**: ningún medidor de fortaleza, checkbox "mostrar contraseña", ni 2FA — ninguno existe en el código real.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### 17C. Contraseña actualizada (confirmación, contexto SaaS)
- **screenId (vigente)**: `d634c64ce3064074a27302bf1733e13a`
- **URL real**: `billing_admin:password_change_done` → `/plataforma/billing/admin/perfil/contrasena/completado/` (`SuperAdminPasswordChangeDoneView`). GET, solo superusuario.
- **Funcionalidad**: confirmación tras cambiar la contraseña exitosamente.
- **Master Pattern**: Confirmación administrativa simple (mensaje + 1 acción), sin celebración/ilustración.
- **Componentes**: tarjeta con el mensaje real ("Tu contraseña se cambió correctamente. Tu sesión sigue activa.") y botón "Volver a mi perfil".
- **Formularios reales**: ninguno.
- **Diálogos**: ninguno.
- **Estados**: ninguno.
- **Estado de aprobación**: **Verificada visualmente por el agente — pendiente de aprobación del usuario.**

### Configuración (SaaS)
**No existe como pantalla independiente; es únicamente un título de grupo del sidebar.** Confirmado por auditoría directa de `templates/layout_saas_admin.html`: `<p class="sidebar__grupo-titulo">Configuración</p>` no es un enlace (`<a>`), solo agrupa visualmente "Cuentas bancarias" (SAAS-14) y "PayPal (plataforma)" (SAAS-16), ambas ya diseñadas. No se buscó ni se creó ninguna URL/vista/template adicional de "configuración general de la plataforma" porque ninguna existe en el código real.

---

## Lote de cierre — 5 pantallas faltantes identificadas en la auditoría final (2026-09-16)

Verificado contra el estado REAL de `list_screens` en Stitch (no memoria de generaciones anteriores) antes de generar cualquiera de estas 5 — el proyecto tenía 21 screenIds vigentes al momento de esta auditoría; varias generaciones intermedias de rondas anteriores ya no existen (ver hallazgos críticos abajo).

### — Detalle de Cliente
- **screenId (vigente)**: `6f1bfc8c86c840e9a1797178d6b7e4a9`
- **URL real**: `billing_admin:customer_detail` → `/plataforma/billing/admin/clientes/<int:pk>/` (`CustomerDetailView`, GET-only).
- **Funcionalidad**: detalle de un `SaaSCustomer` — lista de Tenants asociados (enlaces reales a `tenant_detail` + badge de estado de facturación) y lista de Suscripciones asociadas (SOLO TEXTO, nunca enlaces — confirmado por lectura directa del template) + formulario **inline** (NUNCA modal) para "Emitir nota de crédito" (`issue_credit_note`, 3 campos: Monto, Moneda, Motivo).
- **Master Pattern**: Detalle con 2 listas simples + formulario inline al pie (mismo espíritu que Cuentas bancarias antes de la corrección a modal, pero aquí SÍ es inline en el código real y así se mantuvo).
- **Estado de aprobación**: Verificada visualmente por el agente — pendiente de aprobación del usuario.

### — Detalle de Factura
- **screenId (vigente)**: `e66eff104da64612b70870d59b6cdc78`
- **URL real**: `billing_admin:invoice_detail` → `/plataforma/billing/admin/facturas/<int:pk>/` (`InvoiceDetailView`, GET-only, sin ningún POST).
- **Funcionalidad**: 100% de solo lectura — Líneas (3 columnas), tarjeta de totales (subtotal/descuento+cupón/impuesto/total), Pagos aplicados (4 columnas), Notas de crédito aplicadas (2 columnas, con estado vacío real "Ninguna.").
- **Master Pattern**: Detalle puramente informativo, sin ninguna acción salvo "Volver" — ni editar, ni eliminar, ni descargar PDF (ninguno existe en el código real).
- **Estado de aprobación**: Verificada visualmente por el agente — pendiente de aprobación del usuario.

### — Editar cuenta bancaria (modal)
- **screenId (vigente)**: `b0f76733e8814b589f92b8fa1b0a0a92`
- **URL real**: `billing_admin:bank_account_update` → `/plataforma/billing/admin/cuentas-bancarias/<int:pk>/editar/` (POST-only, modal real `modal-editar-cuenta-{pk}` en `bank_accounts_list.html`).
- **Funcionalidad**: modal de edición con los mismos 9 campos reales de `BankAccountForm` que el modal de creación, pre-llenados con los datos de la cuenta. Botón "Guardar cambios" (no "Crear").
- **Corrección de visibilidad aplicada**: el campo "Cuenta" y la columna "Cuenta" de la tabla de fondo muestran el número **completo, sin ninguna máscara** — siguiendo la decisión visual corregida ya establecida, aunque el estado actual de la pantalla base "Cuentas bancarias" en Stitch haya vuelto a mostrar números enmascarados (ver hallazgo crítico abajo). No se tocó esa pantalla base.
- **Estado de aprobación**: Verificada visualmente por el agente — pendiente de aprobación del usuario.

### — PayPal: Iniciar un cobro (checkout_create)
- **screenId (vigente)**: `7ad36d2a97584ba48406f11cc592b73f`
- **URL real**: `billing_platform:checkout_create` → `/plataforma/billing/paypal/cobrar/` (`CheckoutCreateView`, GET+POST).
- **Funcionalidad**: formulario de 3 campos reales (`CheckoutCreateForm`: Tenant, Plan, Propósito) para iniciar una orden de PayPal de prueba/operación. Banner de advertencia real sobre el alcance de la herramienta.
- **Master Pattern**: Formulario simple de una tarjeta, consistente con "PayPal — herramienta de plataforma".
- **Estado de aprobación**: Verificada visualmente por el agente — pendiente de aprobación del usuario.

### — PayPal: Resultado del cobro (checkout_result)
- **screenId (vigente)**: `b6f42f8d9138405981fdf03fc7fa77ab`
- **URL real**: `billing_platform:checkout_return`/`checkout_cancel` → ambos renderizan `checkout_result.html` (mismo template, estado dinámico vía badge). GET, destinos de redirección de PayPal.
- **Funcionalidad**: confirmación de resultado (Tenant/Plan/Monto + badge de estado + motivo de fallo condicional) con 2 acciones: "Ver detalle" → `transaction_detail`, "← Volver a PayPal" → `status`.
- **Nota de diseño**: se diseñó como UNA sola pantalla state-driven (badge "Confirmada" como estado representativo) — no se crearon 2 pantallas separadas para return/cancel, ya que es literalmente el mismo template real.
- **Estado de aprobación**: Verificada visualmente por el agente — pendiente de aprobación del usuario.

### — Pagos — Estado normal (complementa a SAAS-10, sin modal)
- **screenId (vigente)**: `38683034b45b4ce483778f51fd145083`
- **URL real**: `billing_admin:payments_list` (misma URL/view que SAAS-10 `2462bada8e1947738933c6b50ef879d2`, que solo mostraba el modal "Reembolsar pago" abierto con el listado desenfocado detrás).
- **Funcionalidad**: idéntica a SAAS-10. Tabla de 7 columnas (Tenant/Fecha/Método/Referencia/Monto/Estado/acción), botón "Reembolsar total" (rojo `#DC2626`) SOLO en filas con estado "Confirmado" o "Parcialmente reembolsado" — celda vacía en el resto, confirmado fiel a `{% if payment.status == "confirmed" or payment.status == "partially_refunded" %}`.
- **Corrección aplicada durante la verificación**: el primer intento (`890817b2b26941ad82ac26a6f3681c29`, descartado, no usar como referencia) tenía el botón "Reembolsar total" cortado en el borde derecho de la tarjeta (overflow horizontal) — corregido con `table-layout: fixed` y presupuesto de ancho por columna (acción con mínimo 170px reservado), verificado con zoom sobre la captura real que el texto ahora se lee completo con margen.
- **Estado de aprobación**: Verificada visualmente por el agente — pendiente de aprobación del usuario.

### — Transferencias — Estado normal / cola (Master-4)
- **screenId (vigente)**: `f3f33d37ea5e4d01b11f91bde88ad0a8`
- **URL real**: `billing_admin:transfers_queue` → `/plataforma/billing/admin/transferencias/` (`TransfersQueueView`).
- **Funcionalidad**: cola real de comprobantes de transferencia. Tabla de 6 columnas (Referencia/Tenant/Fecha/Cuenta bancaria/Monto declarado/Estado) + botón "Revisar" (contorno) SIEMPRE presente en cada fila (sin condición de estado, a diferencia de Pagos) → navega a `proof_detail` (SAAS-11, ya existente, pantalla distinta — NO se mezclaron).
- **Título real**: "Transferencias por verificar" (no "Transferencias" a secas — verificado literal en el `<h1>` del template).
- **Esto resuelve el Master-4 faltante** identificado en la auditoría anterior — se generó por instrucción explícita del usuario en esta ronda (antes estaba marcado como "no recrear automáticamente"; ahora sí se solicitó y se creó).
- **Estado de aprobación**: Verificada visualmente por el agente — pendiente de aprobación del usuario.

### ⚠️ Hallazgos críticos de la auditoría final (2026-09-16, requieren tu decisión)
1. ~~Master-4 (Transferencias — cola) faltante~~ — **RESUELTO en esta ronda**, ver entrada arriba (`f3f33d37ea5e4d01b11f91bde88ad0a8`).
2. **SAAS-14 (Cuentas bancarias) sigue con números enmascarados.** Los screenIds de la corrección final (`1ea96a5527f046528b0099b29a026bd4`/`1bc1d91c79b84ec3ac218d5393ad94c4`) ya no existen; lo vigente hoy (`4c0283ddc8904642b2f97bbc633d5673`/`7fe7e1eac3164b2095b35e94cf1100fd`) es la versión anterior con máscara. El modal "Editar cuenta bancaria" (`b0f76733e8814b589f92b8fa1b0a0a92`) sí usa números completos, creando una inconsistencia entre esa pantalla base y ese modal hasta que se decida regenerar SAAS-14 — **sigue pendiente de tu decisión**.

## Pendientes (siguiente orden de trabajo, cada una con auditoría previa)

Queda pendiente, sin generar: la corrección de SAAS-14 (números sin máscara) — fuera de alcance de esta ronda, a la espera de una decisión posterior.

**Nota abierta**: corrección pendiente del Master Shell (ver hallazgo crítico en la entrada #16) — afecta potencialmente a todas las pantallas SaaS. Requiere una decisión y fase dedicada del usuario antes de ejecutarse.

## FASE 7.3 — Implementación visual real del diseño Stitch (2026-09-16)

Corrección de fondo tras verificación real en navegador: el Master Shell (FASE 7.2) ya usaba la marca/agrupación correctas, pero el CSS real (`static/css/base.css`/`design-system.css`) seguía usando tokens antiguos (sidebar azul `#172554` en vez de `#0B0F14`, indicador activo con borde blanco en vez de azul, tipografía `system-ui` en vez de Geist/Inter, tabla con thead gris en vez de tarjeta blanca) — es decir, la estructura HTML ya coincidía con Stitch pero el estilo visual real (colores/fuentes/espaciados) no. Confirmado descargando y leyendo el HTML/CSS real generado por Stitch para el Dashboard (Master, screenId `a7cf5c0731344ff1a1ce69e1b0e9022d`) y para Clientes SaaS (screenId `f9a0d1209c2a4d4889b265d402c25cba`), no solo la captura.

Cambios reales aplicados, todos acotados a `.shell--saas`/`.sidebar--saas`/`.navbar--saas` (cero impacto en el ERP, verificado — ningún selector sin el modificador `--saas` fue tocado):
- **Tipografía**: Geist (encabezados)/Inter (cuerpo) vía Google Fonts, cargadas solo en `layout_saas_admin.html` (`{% block extra_head %}`).
- **Color de marca**: `--color-primario`/`--color-primario-hover` redefinidos a `#2563EB`/`#1D4ED8` (antes `#1d4ed8`/`#1e40af`) dentro de `.shell--saas` — afecta todos los botones/enlaces/badges de las 30 pantallas a la vez.
- **Sidebar**: fondo `#0B0F14` (antes `--color-azul-950` = `#172554`), borde `#1E2630`; ítem activo ahora usa borde izquierdo azul de 3px + fondo blanco 10% (antes `box-shadow` blanco, color equivocado); marca con icono de cuadrícula en caja azul (antes solo texto).
- **Topbar**: eliminado el buscador decorativo (`input disabled`, sin funcionalidad real, no existe en ningún screenId de Stitch); bloque de usuario ahora es avatar sólido azul + nombre + "Super Admin" (antes botón fantasma con avatar tenue); altura 64px.
- **Tablas de listado** (Clientes/Tenants/Planes/Suscripciones/Facturas/Pagos/Transferencias/Notas de crédito/Reembolsos/Cuentas bancarias/PayPal — todas comparten `.tabla`/`.tabla-envoltorio`): envoltorio ahora es tarjeta blanca con sombra sutil, encabezado blanco con borde inferior (antes gris sólido), celdas con más espaciado (`py-4 px-6`), fila con hover sutil.
- **Enlace "Ver" de listados de nivel superior** (Clientes/Tenants/Suscripciones/Facturas/PayPal): cambiado de botón con contorno a enlace de texto azul + flecha (`chevron-derecha`, ícono nuevo en `ui_icons.py`), igual que Stitch. **Diferenciado a propósito** de las tablas anidadas de una pantalla de Detalle (ej. "Facturas recientes" dentro de Detalle de Tenant), donde Stitch sí usa un botón con contorno — verificado descargando el HTML real de esa pantalla (screenId `450834e2cb1d4d57afa82b42eca06907`) antes de decidir, no se generalizó a ciegas.
- **Badges**: punto de color antes del texto (`::before` con `currentColor`, sin tocar ninguna plantilla) — mismo indicador visual que Stitch usa en cada badge de estado.
- **Planes**: filas de "Versiones de precio" ahora en caja con fondo sutil (antes texto plano), con etiqueta "VERSIONES DE PRECIO"/"NUEVA VERSIÓN DE PRECIO" — verificado contra el HTML real de Stitch (screenId `225cfabbac2442779bd0f69bd0a24879`).

Verificado: `manage.py check` limpio; suite completa (`apps.billing apps.accounts.tests`) relanzada tras estos cambios. Verificación de render real (no solo HTTP 200) vía Django test Client contra las 22 rutas únicas del mapa — confirmado en las 21 accesibles con datos de prueba: `sidebar--saas` presente, fuente Geist cargada, buscador ausente, marca con icono presente.

**Honestidad sobre el alcance real de esta ronda**: esto corrige el shell y el patrón de tabla/badge compartido por la gran mayoría de las 30 pantallas — el gap más visible que reportaste (Clientes con "diseño anterior"). No es una migración pixel-por-pixel de las 30 pantallas a Tailwind exacto de Stitch (eso implicaría reescribir el sistema de diseño completo, algo desproporcionado frente a reproducir fielmente estructura/paleta/tipografía/spacing, que es lo que se hizo). Diferencias menores que quedan sin tocar en esta ronda (documentadas, no corregidas): variantes de botón "+" con icono real en vez de carácter "+" de texto; el detalle fino del formulario inline "Nueva versión de precio" (inputs en fila con anchos fijos vs. apilados); consistencia exacta de `border-radius` (`--radio-lg` = 10px vs. `rounded-xl` de Tailwind = 12px, visualmente casi idéntico).

## FASE 7.4 — Corrección visual real: breadcrumbs, scroll, y hallazgo de conflicto en Tenant Detail (2026-09-16)

Corrección de fondo tras rechazo explícito del cierre de FASE 7.3: los cambios CSS globales de esa fase eran mayormente correctos (ver justificación por evidencia abajo), pero dos problemas reales quedaron sin detectar porque nunca se auditó el HTML descargado de las 30 pantallas una por una — solo un puñado.

**1. Breadcrumbs — auditadas las 30 pantallas Stitch descargando su HTML real (no solo la captura).** Hallazgo: **ninguna de las 30 pantallas tiene un breadcrumb visualmente renderizado.** Cada pantalla que menciona "miga de pan" en un comentario HTML (`<!-- MIGA DE PAN -->`) lo hace sobre un bloque vacío o un `<nav>` con separadores `›` sin texto entre ellos — un patrón de generación de Stitch que nunca se completa (confirmado en 5 pantallas independientes: Cambiar contraseña, Pagos, Detalle de Cliente, Detalle de Transacción PayPal, Detalle de Tenant). El patrón real de navegación secundaria de Stitch es:
- **Pantallas de listado** (Dashboard, Clientes, Tenants, Planes, Suscripciones, Facturas, Pagos, Transferencias, Notas de crédito, Reembolsos, Cuentas bancarias, Reportes, PayPal estado): sin ningún elemento de navegación adicional — solo el `<h1>`, navegación vía sidebar únicamente.
- **Pantallas de detalle/formulario** (Detalle de Tenant, Detalle de Cliente, Detalle de Factura, Venta manual, Cambiar contraseña, Contraseña actualizada, Detalle de transacción PayPal, Iniciar cobro PayPal, Resultado del cobro, Comprobante/Proof Detail): un enlace "← Volver a X" (no una migas de varios niveles).

Corrección aplicada: eliminado `<nav class="migas">...</nav>` de las 23 plantillas reales del shell SaaS que lo tenían (20 en `apps/billing/templates`, 3 en `apps/accounts/templates/accounts/*_saas.html`) — **ninguna se tocó en `billing_portal`** (Portal del tenant, shell ERP, 4 plantillas `portal_*.html` con migas intactas) ni en `accounts/perfil.html` (ERP). En casi todos los casos de detalle/formulario el enlace real "← Volver a X" **ya existía** en el template (agregado en fases anteriores) — solo se quitó el breadcrumb redundante que Stitch nunca mostró, sin tocar ese enlace.

**2. Scroll/layout — corregido el mecanismo real del shell SaaS.** El shell compartía con el ERP un layout de CSS Grid + `.sidebar{position:sticky}`, mientras que el HTML real de Stitch usa `.sidebar{position:fixed}` + `margin-left` en el contenido — técnicas distintas que pueden producir una barra de scroll adicional alrededor del sidebar en páginas largas. Corregido con una regla `@media (min-width:1025px)` acotada a `.shell--saas` que reproduce el mecanismo `fixed`/`margin-left` real de Stitch, sin tocar el comportamiento móvil (`@media max-width:1024px`, ya usaba `fixed`+`transform` para el menú de hamburguesa, intacto) ni el `.shell`/`.sidebar` compartido con el ERP.

**3. ⚠️ Hallazgo crítico sin resolver — conflicto real entre dos "Master Screens" de Detalle de Tenant.** Al descargar el HTML completo de `cebc37bd583a46e29d6b1a5011d22545` (la Master Screen "Cancelar suscripción", marcada **Aprobada** desde el inicio del proyecto) se descubrió que su estructura es **sustancialmente distinta** a `450834e2cb1d4d57afa82b42eca06907` (la screen "Estado normal", generada después, marcada solo "verificada por el agente, pendiente de aprobación"), sobre la cual se basó toda la implementación real de `tenant_detail.html`:
   - `cebc37bd...` (Aprobada): grid de 2 columnas (`lg:col-span-5`/`lg:col-span-7`), botones "Suspender"/"Cancelar" con estilo de **contorno claro** (blanco/gris y rojo-50 respectivamente, NO sólidos), y aparecen **dos veces** (una junto al título, otra dentro de la tarjeta de suscripción).
   - `450834e2...` (pendiente de aprobación, usada como referencia real): una sola columna (`max-w-xl`), botones "Suspender"/"Cancelar" **sólidos rojos** (`#DC2626`), una sola vez.
   
   Ambas comparten el enlace "← Volver a tenants" y el patrón general de tarjeta blanca — pero difieren en layout y en el color/estilo de los botones de acción, que es justo el tipo de detalle que esta fase pidió no generalizar sin verificar. **No se reescribió `tenant_detail.html` a un grid de 2 columnas** por esta única evidencia contradictoria y no confirmada por el usuario — el riesgo de inventar una estructura nueva sobre una señal ambigua parecía mayor que mantener la implementación actual (ya verificada, consistente con la screen "pendiente" y con el resto del patrón "Detalle" del proyecto). **Los botones Suspender/Cancelar de `tenant_detail.html` siguen sólidos rojos (`btn--peligro`)** — coincide con la mitad de la evidencia, no con la otra. Se necesita tu decisión: ¿cuál de las dos Master Screens es la vigente para Detalle de Tenant?

**4. Re-verificación de las generalizaciones de FASE 7.3** (fuente, no descripción de memoria): se descargó el HTML real de las 30 pantallas y se confirmó, por evidencia repetida en generaciones independientes, que SÍ son genuinamente compartidas por Stitch (no una generalización inventada): tipografía Geist/Inter (idéntica en el `<head>` de las 30 pantallas), azul `#2563EB` y fondo de sidebar `#0B0F14`/borde `#1E2630` (idénticos en Dashboard y Clientes, generadas independientemente), tarjeta blanca de tabla con `rounded-xl`/`border-slate-200`/`shadow-sm` (idéntica en Clientes, Pagos y la subtabla de Facturas recientes de Detalle de Tenant), punto de color en cada badge de estado (idéntico en Detalle de Tenant, Pagos y Planes). La diferenciación entre el enlace "Ver" con flecha azul (listados de nivel superior) y el botón con contorno "Ver" (subtablas de una pantalla de Detalle) **ya se había verificado y diferenciado correctamente en FASE 7.3**, antes de este hallazgo.
