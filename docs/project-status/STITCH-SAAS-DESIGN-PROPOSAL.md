# Propuesta de diseño visual — Bloque SaaS (Stitch) — FASE 1 (vigente)

> **Este documento es exclusivamente de diseño.** No describe cambios de código, no autoriza cambios de código, y no fue producido modificando Django en ningún momento. Documenta el trabajo hecho en la herramienta externa Stitch (Google) sobre el proyecto **"Budun ERP"** (`projectId 8473502236243200686`). Sustituye la versión anterior (FASE 0.2, sidebar azul `#1E3A8A`) — esa identidad fue reemplazada por decisión explícita del usuario en FASE 0 (reinicio) por la identidad negra descrita abajo. Ver también [STITCH-SAAS-SCREEN-MAP.md](STITCH-SAAS-SCREEN-MAP.md) para el registro pantalla-por-pantalla con su estado de aprobación.

## 1. Objetivo

Modernizar visualmente la consola Super Admin del SaaS de Budun ERP (`apps.billing`, superficie `/plataforma/billing/admin/`) sin alterar la funcionalidad real que ya existe en Django. Regla vigente: **CÓDIGO REAL = fuente de verdad funcional; STITCH = fuente de verdad visual**. Cada pantalla se audita en Django antes de diseñarse; nada se inventa (campos, columnas, filtros, botones, KPIs, modales, estados).

## 2. Fuente de verdad

Cada pantalla se audita releyendo directamente `apps/billing/admin_views.py`, `apps/billing/admin_forms.py`, `apps/billing/services/*.py` y su template real en `apps/billing/templates/billing/admin/`, más `templates/layout_saas_admin.html` para la navegación. Todo dato mostrado (KPIs, columnas, botones, textos de diálogo, campos de formulario) traza a uno de estos archivos — nunca se inventa.

## 3. Master Shell SaaS — CONGELADO (FASE 1)

Los siguientes 5 screenIds son el Master Shell aprobado y **no deben modificarse**; toda pantalla nueva debe reutilizar exactamente su sidebar/topbar:

| # | Pantalla | screenId vigente | Origen real |
|---|---|---|---|
| 1 | Dashboard Super Admin Billing (Master) | `a7cf5c0731344ff1a1ce69e1b0e9022d` | `DashboardView` + `reports.py` + `dashboard.html` |
| 2 | Tenants (listado) | `0319a8ca956947b18f09ecaf83f9dfaa` | `TenantsListView` + `tenants_list.html` |
| 3 | Detalle de Tenant (con diálogo "Cancelar suscripción") | `cebc37bd583a46e29d6b1a5011d22545` | `TenantDetailView` + `tenant_detail.html` |
| 4 | Transferencias por verificar (con diálogo "Aprobar comprobante") | `4bff1829d4ec47a3af888c57fe036527` | cola de transferencias + `proof_detail.html` |
| 5 | Venta manual | `598fbca7485d498a8afc604c7a42d735` | `ManualTenantSaleView` + `admin_forms.py` + `manual_sale.html` |

Nota histórica: estas pantallas pasaron por varias iteraciones (sidebar azul → negro, eliminación de "Cerrar sesión" del sidebar, eliminación del tagline "Plataforma SaaS", unificación del tratamiento del ítem activo). Los screenIds de esas iteraciones intermedias quedaron ocultos (`hidden: true`) en el canvas del proyecto Stitch — no fueron borrados (el MCP no expone borrado de pantallas individuales) pero no deben tomarse como referencia.

Pantallas SaaS adicionales en construcción incremental por bloques (ver sección 21 y el mapa de pantallas): actualmente **Clientes**, **Planes**, **Suscripciones**, **Facturas**, **Pagos**, **Transferencias — Detalle de comprobante**, **Notas de crédito**, **Reembolsos**, **Cuentas bancarias**, **Reportes**, **PayPal**, **PayPal — Detalle de transacción**, **Mi perfil**, **Cambiar contraseña**, **Contraseña actualizada**, **Detalle de Cliente**, **Detalle de Factura**, **Editar cuenta bancaria**, **PayPal — Iniciar un cobro** y **PayPal — Resultado del cobro** han sido auditadas y generadas — ver el screen map para su estado. "Configuración" del sidebar SaaS no es una pantalla real (es solo un título de grupo) y no tiene entrada propia. Pendientes fuera de alcance por decisión explícita del usuario: Master-4 (Transferencias — cola, posiblemente eliminado de Stitch) y la corrección de números sin máscara de SAAS-14.

## 4. Dirección visual

Producto SaaS comercial premium terminado — deliberadamente distinto de Django Admin, de Bootstrap sin personalizar y de una plantilla genérica de dashboard de IA. Estilo sobrio: contornos nítidos, contraste tipográfico claro, mucho aire, sin gradientes ni efectos decorativos. El bloque SaaS tiene identidad propia (sidebar **negro/casi negro**) deliberadamente distinta de la futura identidad visual del bloque ERP (que usará sidebar azul claro) — ambos bloques comparten el mismo Design System base (tipografía, spacing, componentes) pero nunca el mismo color de sidebar.

## 5. Paleta

| Token | Valor | Uso |
|---|---|---|
| Primario | `#2563EB` (hover `#1D4ED8`) | Botones primarios, enlaces, foco |
| **Sidebar SaaS (fondo)** | **`#0B0F14`** (negro/casi negro sólido) | Exclusivo del bloque SaaS — nunca azul/navy/gris |
| Texto sidebar (reposo) | `#9CA3AF` | — |
| Texto sidebar (activo/hover) | `#FFFFFF` | — |
| Superficie activa sidebar | `rgba(255,255,255,0.10)` + borde izquierdo `#2563EB` | Píldora de ancho completo |
| Separador de sidebar | `rgba(255,255,255,0.08)` | Línea horizontal antes de "Configuración" |
| Canvas | `#F8FAFC` | Fondo general del contenido |
| Tarjeta | `#FFFFFF` + borde `#E2E8F0` | Sin sombras pesadas |
| Éxito | `#059669` / fondo `#ECFDF5` | Solo tendencias/estados reales positivos |
| Atención | `#D97706` / fondo `#FFFBEB` | — |
| Peligro | `#DC2626` / fondo `#FEF2F2` | — |
| Neutral | `#64748B` | Texto secundario |

## 6. Tipografía

Titulares: **Geist**. Cuerpo, tablas y formularios: **Inter**. Cifras monetarias y KPIs en variante tabular.

## 7. Spacing

Escala base 4px: `xs=4px, sm=8px, md=16px, lg=24px, xl=32px`. Gutter de grilla 16px, margen de página 24px.

## 8. Border radius

`ROUND_EIGHT`: botones/inputs 8px, tarjetas 12-16px, badges/pills radio completo.

## 9. Sombras

Doctrina plana: sin elevaciones decorativas en tarjetas ni tablas. Sombra difusa reservada exclusivamente a `<dialog>` modales y menús flotantes.

## 10. Componentes definidos

- **KPI card**: icono + etiqueta en español natural + valor tabular + variación % real opcional.
- **Gráfico de línea** (ingresos 6 meses) y **gráfico de dona** (suscripciones por estado): datos reales de `reports.py`.
- **Tabla**: cabecera tenue, badges de estado por color semántico, acciones a la derecha.
- **Tarjeta de detalle**: acciones condicionadas por estado real.
- **Diálogo de confirmación**: `<dialog>` nativo con scrim sobre toda la pantalla (incluido el sidebar, que se ve legítimamente atenuado — no es una inconsistencia de color).
- **Formulario**: agrupado por secciones funcionales reales, un solo botón primario de envío.
- **Estado vacío**: icono + texto descriptivo concreto (aún no diseñado en ninguna pantalla — pendiente).
- **Tarjeta de entidad con formulario inline** (nuevo, confirmado en Planes): tarjeta con nombre + badges de estado + metadatos + una mini-lista interna (aquí, versiones de precio) + un formulario corto embebido al pie con su propio botón — patrón distinto de "Tabla" y de "Formulario de un paso", usado cuando el código real gestiona una colección de sub-entidades (aquí `PlanVersion`) inline en la misma página en vez de en una pantalla separada.

## 11. Sidebar — Master Shell oficial

Sidebar **sticky/fijo**, ocupa toda la altura del viewport, permanece visible durante el scroll del contenido principal, ancho fijo 240px, fondo **`#0B0F14`**. Logotipo: icono + "Budun ERP" únicamente — **nunca** "Plataforma SaaS" ni ningún subtítulo/tagline.

Navegación — 7 grupos en este orden exacto, idéntico en todas las pantallas:
**INICIO** (Dashboard) · **CLIENTES Y TENANTS** (Clientes, Tenants) · **COMERCIAL** (Venta manual, Planes, Suscripciones) · **FACTURACIÓN** (Facturas, Pagos, Transferencias, Notas de crédito, Reembolsos) · **FINANZAS** (Cuentas bancarias) · **REPORTES** (Reportes) · **INTEGRACIONES** (PayPal).

Después, un **separador visual** (línea horizontal sutil), y por último, únicamente, **Configuración** — el último elemento del sidebar. **Nunca** "Cerrar sesión"/"Salir"/"Logout"/"Perfil"/"Mi cuenta" en el sidebar (corrección respecto a la versión FASE 0.2 de este documento, que aún los incluía por error histórico) — esas acciones viven exclusivamente en el menú de perfil del topbar.

## 12. Topbar

Fijo, fondo blanco, borde inferior sutil, sin barra de búsqueda (no confirmada en el código real). A la derecha: avatar circular "CM" + "Carlos Mendizábal" (bold) + "Super Admin" (gris, pequeño). Idéntico en todas las pantallas.

## 13. Dashboard

12 KPI cards reales en el orden exacto de `get_billing_dashboard_summary()`: Ingresos recurrentes mensuales, Ingresos recurrentes anual, Suscripciones activas, Pagos atrasados, Suspendidos, Altas este mes (+%), Cancelaciones este mes (+%), Transferencias pendientes, Ingresos del mes (+%), Reembolsos del mes (+%), Notas de crédito del mes (+%), Facturas vencidas. Debajo: gráfico de línea (ingresos 6 meses) + dona (estado de suscripciones); luego "Actividad reciente"; fila final con "Últimas facturas" (5 columnas) y "Próximos vencimientos".

## 14. Tablas auditadas

- **Tenants**: 4 columnas — Nombre, Estado de facturación, Activo, Acción ("Ver"). Botón "+ Nuevo tenant" (navegación real hacia Venta manual, sin flujo nuevo). Sin buscador/filtro/paginación (no existen en `TenantsListView`).
- **Clientes SaaS**: 4 columnas — Nombre, Correo, País, acción "Ver". Sin botón de creación (los clientes solo se crean vía Venta manual), sin búsqueda/filtro/paginación (`CustomersListView.get()` no acepta parámetros).
- **Notas de crédito**: 7 columnas, SIN columna de acción. El "Estado" (Disponible/Parcialmente aplicada/Aplicada totalmente) es derivado en el template comparando saldo disponible contra monto — `CreditNote` no tiene campo `status` real, es inmutable, nunca se cancela. La emisión de notas de crédito vive en Detalle de Cliente (SAAS-06), no se duplica aquí.
- **Reembolsos**: 7 columnas — Tenant, Pago, Fecha, Monto, Motivo, Estado, acción condicional "Marcar completado". Condición doble real: `status == "pending"` **y** `not paypal_transaction_id` — solo reembolsos manuales pendientes, nunca los de PayPal. Diálogo "Marcar reembolso como completado" de solo confirmación, sin campos de formulario.
- **Cuentas bancarias**: 7 columnas — Banco, País, Moneda, Titular, Cuenta, Estado, 2 acciones ("Editar" con modal, "Activar"/"Desactivar" directo sin confirmación, azul/rojo respectivamente). El formulario de creación (9 campos, mismo `BankAccountForm` que editar) se presenta mediante **botón "+ Nueva cuenta" → modal centrado** (mismo patrón que "+ Nuevo plan" en Planes — corrección visual pedida explícitamente por el usuario tras una primera versión que lo mostraba siempre visible al pie de página, fiel al código real pero con peor UX). Incluye el párrafo explicativo real sobre por qué no existe "Eliminar" (protección por `PaymentProof.bank_account`). La columna "Cuenta" muestra el número **íntegro, sin ningún carácter de máscara** (`***`/`····`/`••••`/`...` quedaron descartados por corrección explícita del usuario: un dígito visible detrás de una máscara NO cuenta como "completo") — se logra con un presupuesto de ancho fijo por columna (`table-layout: fixed`) que reserva un mínimo intocable para la columna "Acciones" y permite truncar con ellipsis únicamente "Banco"/"Titular" si hiciera falta liberar espacio, nunca "Cuenta" ni "Acciones".
- **Reportes**: única pantalla de la plataforma sin ninguna acción, filtro, exportación ni columna de enlace por fila — de solo lectura por completo. 2 secciones independientes, cada una con línea resumen (texto simple, no KPI cards) + tabla continua de 5 columnas: "Ingresos" (Fecha/Tenant/Plan/Método/Monto) y "Antigüedad de facturas pendientes de pago" (Número/Tenant/Vencimiento/Total/Días vencido). La vista real calcula además un resumen de dashboard y un reporte de suscripciones que el template nunca renderiza — deliberadamente omitidos del diseño. La línea resumen de Antigüedad se presenta con formato moneda completo (separador de miles, 2 decimales) aunque el template real no le aplique el filtro `|monto` — decisión de fidelidad visual sobre un valor que es dinero, no una funcionalidad nueva.
- **PayPal**: vive en el namespace `billing_platform` (no `billing_admin`) — hallazgo de auditoría, distinto árbol de URLs que comparte el mismo shell visual. Tarjeta "Estado del gateway" (Ambiente/Checkout/Última prueba + 3 acciones sin confirmación: "Probar conexión", "Deshabilitar/Habilitar checkout", "Iniciar un cobro de prueba") + tabla de solo lectura "Últimas transacciones" (7 columnas: Tenant, Plan, Propósito, Monto, Estado, Creada, acción "Ver"). Sin campos de credenciales (Client ID/Secret son variables de entorno, nunca de base de datos). Corrección de "regla visual limpia" pedida explícitamente por el usuario: se eliminó el subtítulo largo real bajo el h1 y se condensó el banner de advertencia (3 frases reales) a una sola línea, conservando el contenido funcional. **Hallazgo crítico documentado en la entrada #16 del screen map**: el sidebar real agrupa distinto al Master Shell congelado (sin grupos "COMERCIAL"/"FINANZAS"/"INTEGRACIONES"; "Cuentas bancarias" y "PayPal" comparten un único grupo real "Configuración") — corrección pendiente de decisión del usuario, no aplicada aún a ninguna pantalla.
- **PayPal — Detalle de transacción** (destino real del botón "Ver" de la tabla de PayPal, `billing_platform:transaction_detail`): tarjeta de detalle (identificación, estado, montos, IDs de orden/captura/reembolso en formato código, sin truncar), banner condicional si la transacción no tiene un `SaaSPayment` real asociado, tarjeta "Reembolsar" condicional (solo si `status == "confirmed"`, sin confirmación modal, formulario de 2 campos opcionales), tabla "Eventos de webhook" (4 columnas). Auditoría encontró que el badge de estado "refunded" (Reembolsada) debe ser **azul**, no gris — mapeo real en `apps/core/templatetags/ui_extras.py`; la pantalla PayPal principal ya generada usó gris incorrectamente para ese estado, corrección pendiente en una pasada futura dedicada (no se tocó por instrucción explícita del usuario en este turno).
- **Mi perfil / Cambiar contraseña / Contraseña actualizada** (contexto SaaS, alcanzadas desde el menú del avatar del topbar, no desde el sidebar — ningún ítem del sidebar aparece activo en las 3): tras una corrección funcional real de Django (no visual) que separó estas rutas del ERP (ver entrada #16 del screen map), cada pantalla reutiliza al 100% su form real de Django — "Mi perfil" usa `ProfileForm` (3 campos: Nombre/Apellido/Correo electrónico, sin tenant/empresa), "Cambiar contraseña" usa el `PasswordChangeForm` estándar de Django (3 campos: Contraseña actual/nueva/confirmación, sin requisitos de contraseña listados porque el template real no los renderiza), "Contraseña actualizada" es solo un mensaje de confirmación + 1 botón. Todas formularios de una sola tarjeta compacta, sin acciones condicionales, sin badges de estado. "Configuración" del sidebar SaaS **no es una pantalla real** — es únicamente el título del grupo que contiene Cuentas bancarias y PayPal (plataforma), confirmado por auditoría directa del template (`<p>`, no `<a>`).
- **Transferencias — Detalle de comprobante** (distinto de la Master Screen de la cola): 2 acciones reales, no 1 — "Aprobar" (abre diálogo modal) y "Rechazar" (formulario inline de un input, SIN modal, exige motivo). El detalle expone además una descarga real del archivo del comprobante (enlace protegido, no `MEDIA_URL` estático).
- **Pagos**: 7 columnas — Tenant, Fecha, Método (PayPal/Transferencia bancaria/Otro (manual)), Referencia, Monto, Estado, acción condicional "Reembolsar total" (solo en pagos Confirmado/Parcialmente reembolsado). Diálogo "Reembolsar pago" de solo confirmación, sin campos de monto/motivo aunque el form los acepte — el template real no los renderiza.
- **Facturas**: 6 columnas — Número, Tenant, Total (con moneda), Vencimiento, Estado, acción "Ver". Tope de 100 filas por código (`[:100]`), no una paginación de UI. Sin resumen/KPIs, sin filtros, sin acciones de descargar/anular/marcar pagada.
- **Suscripciones**: 6 columnas — Tenant, Plan, Frecuencia, Estado, Fin de período, acción "Ver" (navega a Detalle de Tenant, no existe detalle de suscripción propio). Sin búsqueda/filtro/paginación/acciones. El servicio real calcula un resumen de conteos por estado que el template nunca muestra — deliberadamente omitido en el diseño para no inventar un componente inexistente en la pantalla real.
- **Planes**: NO es una tabla — es una tarjeta por plan (nombre + badge "Inactivo" condicional + slug + descripción + lista de versiones de precio, incluido histórico, con badge "Vigente" solo en la actual) + formulario inline "Nueva versión de precio" por tarjeta. La creación de un plan nuevo usa el patrón **listado → botón "+ Nuevo plan" → modal centrado** (no un formulario permanentemente visible al pie de página — corrección aplicada tras revisión del usuario). Sin búsqueda/filtro/paginación. **No existe** acción de activar/desactivar ni editar un plan ya creado — confirmado por ausencia de esas vistas en `admin_urls.py`.
- **Transferencias**: 7 columnas — Referencia, Tenant, Fecha, Cuenta bancaria, Monto declarado, Estado, acción "Revisar".
- **Facturas recientes** (Tenant detalle): hasta 20 facturas.

## 15. Formularios

**Venta manual**: exactamente 5 campos reales en 3 secciones (Cliente SaaS: nombre, correo · Tenant: nombre, plan · Propietario: correo), sin campos de pago/monto/ciclo. Copy real: "Crea un cliente SaaS, un tenant y su suscripción. El tenant queda pendiente de pago hasta que se confirme la primera factura."

## 16. Diálogos

- **Cancelar suscripción** (Tenant detalle): "Se cancelará la suscripción de [Tenant]. Esta acción detiene la facturación futura (incluido el cobro recurrente de PayPal, si está autorizado). ¿Confirmas la cancelación?" — botones Volver / Sí, cancelar.
- **Aprobar comprobante** (Transferencias): resumen del comprobante (referencia, tenant, factura, monto declarado, cuenta receptora, banco de origen, fecha, enlace al archivo) + confirmación de aplicación del pago — botones Cancelar / Sí, aprobar.

Los 4 botones de acción condicional de Tenant detalle (Activar/Reactivar/Suspender/Cancelar) respetan el mismo gating por `subscription.status` que la vista real.

## 17. Estados

Badges semánticos consistentes: verde=Activo/Aprobado, ámbar=Pendiente, rojo=Suspendido/Rechazado, gris=Cancelado, naranja=Moroso/Vencido. Ningún estado inventado.

## 18. Responsive

Breakpoints previstos en el design system: 1440/1280/1024/900/640px. Todas las pantallas generadas hasta ahora fueron verificadas únicamente en `DESKTOP` — el comportamiento responsive real **no ha sido generado ni verificado todavía**.

## 19. Decisiones visuales (no funcionales, de diseño puro)

- Sin breadcrumbs — wayfinding por ítem activo del sidebar + título + enlaces reales de "volver".
- Sin campana de notificaciones ni avatar fotográfico en el topbar (no existen en el código real).
- Sin "Sistema Operativo" / "Tenant Matriz" en el topbar.
- Etiquetas ya estaban en español natural en el código real — no hizo falta traducir ningún código técnico visible.

## 20. Elementos que NO deben inventarse (recordatorio explícito para las siguientes pantallas)

- Ninguna columna, filtro, buscador o botón de creación más allá de lo confirmado por auditoría (p. ej. Tenants y Clientes SaaS no tienen búsqueda/filtro/paginación reales).
- Ningún campo de pago/monto/ciclo en Venta manual.
- Ningún campo de contacto/RUC/límites en Tenant detalle que no esté en `tenant_detail.html`.
- Ninguna acción rápida, KPI o métrica que no provenga literalmente de un servicio real.
- Ninguna notificación, avatar fotográfico o elemento decorativo no confirmado en el código real.
- **"Cerrar sesión" nunca en el sidebar** — vive exclusivamente en el menú de perfil del topbar.

## 21. Elementos todavía pendientes

- Barra de búsqueda global en el topbar: **no confirmada** contra `layout_saas_admin.html` — decisión de chrome pendiente de validación del usuario (no se ha vuelto a incluir desde la corrección de FASE 0.3; el Master Shell actual no la tiene).
- Estado vacío (tabla sin resultados) no diseñado todavía en ninguna pantalla.
- Comportamiento responsive real no generado ni verificado.
- El resto del mapa de pantallas SaaS (Planes, Suscripciones, Facturas, Pagos, Notas de crédito, Reembolsos, Cuentas bancarias, Reportes, PayPal, Configuración, y las vistas secundarias de detalle/edición/confirmación de cada una) — pendientes, se construyen por bloques pequeños con auditoría previa a cada una (ver [STITCH-SAAS-SCREEN-MAP.md](STITCH-SAAS-SCREEN-MAP.md)).
- El bloque ERP completo (incluido POS) — no iniciado; tendrá su propia identidad visual (sidebar azul claro) en una fase separada, después de congelar el SaaS.
