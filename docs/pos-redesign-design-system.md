# FASE 7 — POS LAB PROFUNDO — ETAPA 2 — POS DESIGN SYSTEM

Especificación de diseño únicamente. Cero código modificado en esta
etapa. Fuente de verdad, en orden de autoridad: (1) código funcional
real del POS, (2) `docs/pos-redesign-discovery.md` +
`docs/pos-redesign-risk-map.md` (Etapa 1, aprobada), (3) Atlas ERP
Design System (`docs/erp-redesign-design-system.md` +
`static/css/design-system-erp.css`, FASE 5, cerrada/aprobada), (4)
necesidades UX específicas del POS, (5) propuestas visuales nuevas.
Stitch no es fuente de verdad funcional en ningún punto de este
documento. Ninguna funcionalidad nueva se infiere de un componente
visual.

---

## 1. Principios POS

El POS no es una pantalla administrativa más — es una herramienta de
operación rápida de mostrador. Todo lo definido aquí se subordina a:

1. **Velocidad** — el cajero repite el mismo flujo decenas de veces por
   turno; cada elemento visual debe reducir fricción, no añadirla.
2. **Claridad** — el producto, la cantidad y el total deben leerse sin
   ambigüedad a distancia de mostrador.
3. **Lectura inmediata** — precios y totales usan siempre tratamiento
   tabular (heredado de `.u-cifra` de Atlas), nunca una tipografía que
   dificulte comparar cifras de un vistazo.
4. **Interacción directa** — cada acción (agregar, quitar, cobrar) es
   un control de una sola pulsación/clic, sin pasos intermedios que hoy
   no existan en el código real.
5. **Baja carga cognitiva** — densidad de información alta pero
   ordenada; nunca decorativa.
6. **Prevención de errores** — el diseño visual debe dejar espacio para
   que futuras decisiones funcionales (ver §26) muestren advertencias
   antes de una acción irreversible, sin inventar esa lógica ahora.
7. **Visibilidad permanente del carrito y el total** — el cajero nunca
   debe perder de vista cuánto lleva acumulado.
8. **Acceso rápido al checkout** — el botón de cobro es siempre el
   control de mayor peso visual de la pantalla.
9. **Identificación clara del producto** — nombre, SKU, y cuando
   aplique IMEI/serie, siempre visibles en la misma línea.
10. **Feedback inmediato** — todo estado (agregado, error, aprobación
    pendiente) debe tener una representación visual reconocible al
    instante, reutilizando el lenguaje de estados ya definido por
    Atlas.
11. **Operación táctil y con teclado** — objetivos de toque de tamaño
    generoso y compatibilidad de foco de teclado en todo control
    interactivo.

Ninguno de estos principios autoriza inventar una función nueva — son
criterios para **diseñar** lo que el código real de Etapa 1 ya soporta.

---

## 2. Relación con Atlas

Atlas ERP sigue siendo la referencia visual general de Budun. El POS
**hereda por defecto** todo lo que no tenga una razón operativa
documentada para especializarse:

| Elemento | Decisión | Razón |
|---|---|---|
| Tipografía (IBM Plex Sans + IBM Plex Mono) | **Heredar sin cambios** | Ya legible, ya cargada globalmente, cambiarla solo para POS fragmentaría la identidad Budun sin beneficio operativo real. |
| Lenguaje de iconos (SVG de línea, stroke 1.5-1.75) | **Heredar sin cambios** | Mismo motivo — además corrige una inconsistencia real detectada en Etapa 1 (emoji en estados vacíos del POS, ver §21). |
| Botones (`.btn`, `.btn--primario/contorno/fantasma`) | **Heredar la base, especializar tamaño de objetivo táctil** | Ver §7.3 — Atlas no definió un tamaño mínimo de toque porque el ERP administrativo se opera con mouse/trackpad; el POS necesita uno mayor. |
| Badges (`.badge--verde/advertencia/peligro/azul/neutro`) | **Heredar sin cambios** | El vocabulario semántico de estado ya es correcto y suficiente. |
| Estados (vacío, error, éxito) | **Heredar estructura, corregir vestigio de emoji** | Ver §21. |
| Campos (`.campo`, `_campo.html`) | **Heredar, pero exigir su uso donde hoy falta** | Etapa 1 encontró filas de "Agregar producto" que no pasan por `_campo.html` (sin `<label>`) — es una corrección de conformidad con Atlas, no una especialización nueva. |
| Spacing (`--espacio-*`) | **Heredar sin cambios** | Escala ya suficiente para mayor densidad si se usan los pasos más bajos (`--espacio-1/2`) donde corresponda. |
| Bordes y radios (`--radio-sm/md/lg/completo`) | **Heredar sin cambios** | Ver §6. |
| Sombras (`--sombra-sm/md/lg`) | **Heredar, usar solo `--sombra-sm`** | Ver §6 — el POS no debe ganar peso decorativo. |
| Tablas (`.tabla`, `.tabla-envoltorio`) | **Heredar estructura, especializar densidad de fila** | Ver §7.6 — el carrito necesita filas más compactas que una tabla administrativa típica. |
| Mensajes (`django.contrib.messages`/toasts) | **Heredar el mecanismo, especializar posición/prioridad visual para checkout** | Ver §18. |
| Accesibilidad (labels, `aria-*`, foco visible) | **Heredar sin cambios, extender donde hoy falta** | Ver §20. |

**Lo que se especializa para POS** (justificación operativa, no
estética): densidad de tabla del carrito, tamaño mínimo de objetivo
táctil en controles de cantidad/agregar/quitar, prominencia del bloque
de Total, y el tratamiento de la fila de búsqueda/alta rápida de
producto. Ninguna especialización introduce un color, una tipografía o
un radio que no exista ya en Atlas o en `base.css`.

---

## 3. Namespace

**Propuesta**: `.shell--pos`, aplicado a `.shell` en el mismo punto
donde hoy `layout_app.html` aplica `.shell--erp` — pero **solo para las
pantallas operativas del terminal/caja** (`terminal.html`,
`register_list.html`, `session_open.html`, `session_close.html`,
`session_summary.html`; `customer_collections.html`/
`collections_search.html` permanecen bajo `.shell--erp`, ya migradas en
FASE 5, fuera de este alcance).

Esto es **arquitectura documentada, no implementada** en esta etapa.
Principio de aislamiento (mismo patrón ya probado por `.shell--erp` vs
`.shell--saas` en FASE 5):

- `.shell--pos` nunca redeclara `:root` — todo vive scopeado bajo el
  selector, igual que `.shell--erp`.
- `.shell--pos` puede **heredar por sustitución de token** cualquier
  variable ya definida por `.shell--erp` que el terminal use hoy
  (heredada pasivamente porque `layout_app.html` ya envuelve el POS en
  `.shell--erp` — hallazgo de Etapa 1, §9) — no se duplican valores,
  se reutilizan.
- `.shell--pos` nunca modifica `base.css` ni `design-system.css` (la
  librería de componentes compartida, sin scope, que hoy define
  `.btn`/`.tarjeta`/`.tabla`/`.badge`/`.campo`/`.kpi*`).
- `.shell--pos` nunca modifica ni depende de `.shell--saas`.
- Un archivo nuevo, `static/css/design-system-pos.css` (nombre
  propuesto, mismo patrón que `design-system-erp.css`), sería el único
  lugar donde vivan tokens/especializaciones POS — **no creado en esta
  etapa**.

**Pregunta abierta para Etapa 3 (Design Lab), no resuelta aquí**: si
`.shell--pos` convive con `.shell--erp` en la misma página (ej.
`<div class="shell shell--erp shell--pos">`, aplicando ambos) o si lo
reemplaza por completo en las pantallas del terminal. Dado que hoy el
POS ya hereda pasivamente `.shell--erp` (sidebar/topbar Atlas, que
Etapa 1 confirmó que debe conservarse — no es una pantalla de pantalla
completa aislada como un punto de venta dedicado), la opción que
menos rompe la arquitectura actual es **convivencia** (`shell--erp
shell--pos` juntos, el segundo solo añade/sobrescribe tokens de
densidad y tamaño táctil dentro del área de contenido). Se documenta
como recomendación, a confirmar explícitamente al iniciar Etapa 3.

---

## 4. Tokens — Color

Ningún color nuevo. Todos los siguientes son **alias de tokens Atlas ya
existentes**, renombrados solo donde el propósito POS lo justifica para
legibilidad del propio CSS (nunca un valor distinto):

| Token POS propuesto | Alias de | Valor heredado | Propósito |
|---|---|---|---|
| `--pos-color-primario` | `--color-primario` (Atlas) | `#1D4E89` | Botón de cobro, foco, elementos de acción principal |
| `--pos-color-primario-hover` | `--color-primario-hover` (Atlas) | `#123761` | Hover/active del botón de cobro |
| `--pos-color-exito` | `--color-secundario`/verde Atlas | `#0F7A5C` | Línea agregada con éxito, pago confirmado |
| `--pos-color-advertencia` | ámbar Atlas | `#8F5A0B` / fondo `#FBEFDC` | Requiere IMEI/serie, descuento pendiente de autorización |
| `--pos-color-peligro` | rojo-terracota Atlas | `#B3311F` / fondo `#F9E4E0` | Error de validación, stock/unidad no disponible, rechazo de checkout |
| `--pos-color-info` | azul Atlas | `#1D4E89` / fondo `#E4ECF6` | Mensaje informativo neutro (ej. "Consumidor final") |
| `--pos-color-neutral` | gris Atlas | `--gris-400`/`--gris-700` | Elementos secundarios, texto de ayuda |
| `--pos-color-superficie` | `--color-superficie` (Atlas) | `#FFFFFF` | Tarjetas, filas de carrito |
| `--pos-color-fondo` | `--color-fondo` (Atlas) | `#F5F6F8` | Fondo de página |
| `--pos-color-texto` | `--color-texto` (Atlas) | `#111827` | Texto principal |
| `--pos-color-texto-tenue` | `--color-texto-tenue` (Atlas) | `#5D6773` | Texto secundario (SKU, ayuda) |
| `--pos-color-borde` | `--color-borde` (Atlas) | `#D7DCE3` | Bordes de fila/campo |

**Estados de checkout** (mapeo visual, no un color nuevo — reutiliza
exactamente el vocabulario semántico de badge/alerta ya definido por
Atlas):
- Pago suficiente / venta lista para confirmar → `--pos-color-exito`.
- Pago insuficiente sin crédito habilitado (`InsufficientPaymentError`
  real) → `--pos-color-peligro`.
- Autorización de descuento/crédito pendiente (`ApprovalRequest`
  `PENDING` real) → `--pos-color-advertencia`.
- Autorización ya aprobada, lista para consumir → `--pos-color-exito`.

**Estados de pago** (mapeo sobre `Payment.Status`/`PaymentMethod`
reales — nunca un estado inventado):
- `confirmed` → `--pos-color-exito`.
- `voided` → `--pos-color-neutral` (texto tachado/atenuado, mismo
  patrón que "Revertido" en `sale_detail.html`).

No se introduce ningún color fuera de la paleta Atlas ya aprobada —
verificado explícitamente contra `docs/erp-redesign-design-system.md`
y `static/css/design-system-erp.css`.

---

## 5. Tipografía

**Se mantiene la tipografía Atlas sin especialización**: IBM Plex Sans
para texto de interfaz, IBM Plex Mono (`--fuente-mono`) para cifras. No
existe una razón operativa documentada en Etapa 1 que justifique una
familia tipográfica distinta para el POS — introducir una segunda
familia solo para POS fragmentaría la identidad visual sin beneficio
medible.

**Tratamiento numérico obligatorio** (extensión directa de la utilidad
`.u-cifra` ya existente, sin crear una segunda):
- Precio unitario, subtotal de línea, descuento, impuesto, total de
  línea, Subtotal/Descuento/Impuesto/Total del carrito, monto de cada
  fila de pago, efectivo esperado/contado/diferencia de caja: **todos**
  llevan `.u-cifra` (mono + `tabular-nums`), igual que ya se aplicó a
  las 13 pantallas Atlas en FASE 5.
- El **Total** de la venta usa una escala de tamaño mayor que el resto
  de las cifras (ver §11 — prominencia), pero la misma familia
  monoespaciada, nunca una fuente distinta.

**Escala de tamaño**: se reutiliza `--texto-xs/sm/base/lg/xl/2xl/3xl`
de `base.css` sin ampliarla — el Total del checkout puede usar
`--texto-3xl` (mayor que el `--texto-2xl` que usan hoy los KPI de
Atlas), justificado únicamente para ese elemento por el principio de
prominencia de §11, no una escala nueva.

---

## 6. Espaciado, bordes y sombras

**Espaciado**: se reutiliza la escala `--espacio-1` a `--espacio-12` de
`base.css` sin crear una escala paralela. La especialización POS es de
**uso**, no de valores nuevos: el carrito y la fila de búsqueda/alta
favorecen los pasos más bajos (`--espacio-1`/`--espacio-2`) para
aumentar densidad sin reducir legibilidad, mientras que el bloque de
Total y el botón de cobro favorecen los pasos más altos
(`--espacio-6`/`--espacio-8`) para separarlos visualmente del resto.

**Bordes y radios** — jerarquía propuesta, todos alias de
`--radio-sm/md/lg/completo` ya existentes (`4px`/`6px`/`10px`/`999px`):

| Elemento | Radio | Justificación |
|---|---|---|
| Inputs (cantidad, descuento, IMEI, montos de pago) | `--radio-sm` (4px) | Igual que cualquier `.campo` de Atlas — sin especialización. |
| Tarjetas (Cliente, Descuento, Cobro) | `--radio-lg` (10px) | Igual que `.tarjeta` de Atlas. |
| Fila de carrito | `--radio-sm` (4px) o sin radio (borde inferior simple) | Una tabla no necesita el mismo radio que una tarjeta — a decidir en Design Lab según legibilidad real. |
| Bloque de Total | `--radio-lg` (10px) | Consistente con tarjetas, refuerza que es un bloque de cierre. |
| Alertas (autorización pendiente, error de checkout) | `--radio-md` (6px) | Igual que `.alerta` de Atlas. |
| Botones | `--radio-md` (6px) | Igual que `.btn` de Atlas — el botón de cobro no necesita un radio especial para destacar, su tamaño/color ya lo logran (ver §11). |
| Modales | No aplica — **el POS no tiene modales hoy** (Etapa 1 confirmó cero JS/modales propios); si una futura decisión funcional introduce uno, usaría `--radio-lg`, igual que cualquier modal Atlas ya existente en el proyecto. |

**Sombras**: deliberadamente discretas, coherente con la instrucción
de no convertir el POS en una interfaz decorativa. Uso exclusivo de
`--sombra-sm` para tarjetas/filas elevadas; `--sombra-md`/`--sombra-lg`
quedan reservados (como en Atlas) para elementos genuinamente
flotantes — hoy el POS no tiene ninguno (sin dropdowns/modales
propios).

---

## 7. Componentes POS

Para cada componente: si existe hoy, si se reutiliza de Atlas, si
requiere especialización POS, si es nuevo (solo visual) o si necesita
una decisión funcional antes de poder implementarse. Clasificación
A/B/C/D según §27.

### 7.1 POS Shell
**Existe** (es `layout_app.html` + `.shell--erp`, heredado). **Reutiliza
Atlas** (sidebar/topbar) **+ especialización POS** propuesta (§3,
`.shell--pos` para densidad/tamaño táctil del área de contenido).
Clasificación: **A**.

### 7.2 POS Header
**No existe como componente propio** — `terminal.html` no tiene
`nav.migas` (única pantalla del POS sin breadcrumb, confirmado en
Etapa 1) ni un encabezado de página dedicado más allá del banner de
estado de caja. Especialización POS propuesta: un encabezado compacto
con nombre de caja/cajero/estado de sesión, siempre visible. Es
**visual únicamente** — la información (caja, usuario, sesión) ya
existe en el contexto de la vista. Clasificación: **A**.

### 7.3 Product Search
**Existe** (`PosSearchForm`, campo único `q`). Reutiliza `.campo` de
Atlas. Especialización POS propuesta: mayor tamaño de campo/objetivo
táctil, `autofocus` visual (el propio HTML ya podría llevar el
atributo `autofocus` sin ningún cambio de lógica — es un atributo
HTML declarativo, no JS; se documenta aquí como candidato de Design
Lab, no se agrega en esta etapa). Clasificación: **A**.

### 7.4 Product Result
**Existe** (fila de resultado con Producto/SKU/Precio/Unidad/Cantidad/
Descuento). Reutiliza `.tabla`. Especialización POS: la fila de alta
rápida (`quantity`/`discount_percent`/`discount_amount`/
`unit_identifier`) debe pasar a usar `_campo.html` con `<label>` real
(hoy no lo hace — hallazgo de Etapa 1) — esto es una corrección de
conformidad con Atlas/accesibilidad, no una función nueva.
Clasificación: **A**.

### 7.5 Product Identification (nombre/SKU/IMEI visible)
**Existe** parcialmente — el carrito muestra el identificador
truncado (`···últimos 4 dígitos`), el recibo el identificador completo.
Reutiliza patrón de `.badge`/texto secundario de Atlas. Clasificación:
**A**.

### 7.6 Cart (Carrito)
**Existe** (tabla del carrito en `terminal.html`). Reutiliza `.tabla`
de Atlas, **con especialización de densidad** (filas más compactas,
`--espacio-2` en vez de `--espacio-3`/`4` de una tabla administrativa
típica) — justificado por el principio de visibilidad permanente del
carrito completo sin scroll excesivo. Ver §9 para el detalle completo
de jerarquía de columnas. Clasificación: **A**.

### 7.7 Cart Line (línea de carrito)
**Existe**. Reutiliza fila `.tabla` + botón "Quitar" (`.btn--sm`).
Clasificación: **A**.

### 7.8 Quantity Control
**No existe como control dedicado hoy** — la cantidad se captura solo
en el formulario de alta (antes de agregar), y no es editable una vez
en el carrito (hallazgo de Etapa 1, §19.3 de risk-map: "sin edición de
línea"). Un control visual de +/- en el carrito **implicaría poder
editar una línea ya agregada**, que hoy no existe como capacidad de
backend. Clasificación: **B — EXISTENTE PERO REQUIERE CAMBIO UX,
condicionado a una decisión funcional separada** (edición de línea del
carrito, no incluida en las 8 decisiones pendientes de Etapa 1 porque
no fue detectada como ausencia crítica, pero comparte la misma
naturaleza). Se documenta el control visual (par de botones +/- con
input central) como propuesta, **no autorizada para Design Lab** hasta
que se decida si el backend soporta editar cantidad de una línea
`DRAFT` ya agregada.

### 7.9 Customer Selector
**Existe** (`CustomerSelectForm`, `<select>`). Reutiliza `.campo`.
Especialización POS: el campo "Buscar cliente" hoy vestigial (Etapa 1)
no debe rediseñarse visualmente como si funcionara — se documenta como
**D — decisión funcional pendiente** (conectar la búsqueda real ya
existente en `apps.customers.services.list_customers`, usada en
Cobros pero no aquí) antes de que el Design Lab le dé tratamiento
visual de "buscador funcional". Clasificación: **A** para el `<select>`
en sí; **D** para el campo de búsqueda.

### 7.10 Discount Section
**Existe** (línea y global, con autorización real vía
`apps.approvals`). Reutiliza `.campo`/`.alerta`. Clasificación: **A**.

### 7.11 Totals
**Existe** (`.kpi-grid` de 4 KPIs iguales: Subtotal/Descuento/
Impuesto/Total). Reutiliza `.kpi` de Atlas, **con especialización de
prominencia para el Total** (ver §11) — hoy los 4 KPIs son visualmente
idénticos, lo cual Etapa 1 marcó como problema de jerarquía.
Clasificación: **A**.

### 7.12 Payment Form
**Existe** (`CheckoutPaymentFormSet`, 2 filas). Reutiliza `.campo`.
Clasificación: **A**.

### 7.13 Payment Row
**Existe** (método + monto por fila). Reutiliza `.campo` en fila
flex — **especialización POS: `flex-wrap` real** (hoy carece de él,
hallazgo de Etapa 1 §16 — es una corrección responsive, no una función
nueva). Clasificación: **A**.

### 7.14 Checkout Summary
**No existe como bloque dedicado** — hoy el resumen antes de cobrar es
implícito (el cajero ve los KPIs de arriba y el formset de pago). Un
bloque visual que agrupe "Total a pagar / Total ingresado / Diferencia"
antes de confirmar es **visual únicamente si los tres valores ya se
calculan** — `sale.total` y la suma de `amount` del formset sí están
disponibles en el momento de renderizar; la diferencia/cambio se
calcula hoy solo en el POST del servidor (`CheckoutView.post`), no
antes. Mostrar una diferencia en vivo mientras el cajero escribe
montos requeriría JavaScript nuevo (hoy inexistente). Clasificación:
**A** para un resumen estático de Total a pagar; **C — nueva
funcionalidad (cálculo en vivo con JS)** para cualquier actualización
dinámica antes del submit — no incluida en Design Lab sin autorización
separada.

### 7.15 Cash Status (estado de caja abierta/cerrada)
**Existe** (banner en `terminal.html`). Reutiliza `.badge`/`.alerta`.
Clasificación: **A**.

### 7.16 Approval Notice
**Existe** (bloque de `ApprovalRequest` aprobadas pendientes de
consumir, y mensaje flash cuando se solicita una nueva). Reutiliza
`.alerta--advertencia`/`.alerta--exito`. Clasificación: **A**.

### 7.17 Empty State
**Existe** (carrito vacío, sin resultados, sin sesiones). Reutiliza
`.estado-vacio` de Atlas — **requiere corrección**: hoy usa emoji
(🛒/🗂️/🏪/🔍) en vez del ícono SVG de línea que Atlas ya define
(`.estado-vacio__icono svg`, ya usado en `customer_collections.html`).
Es una corrección de conformidad con una regla Atlas ya aprobada, no
una especialización nueva. Clasificación: **A**.

### 7.18 Error State
**Existe** (mensajes flash de Django vía `ui.js`/toasts, errores de
formulario vía `_campo.html`). Reutiliza el mecanismo existente.
Especialización POS: prioridad visual mayor para errores de checkout
(ver §13). Clasificación: **A**.

### 7.19 Success Feedback
**Existe** (mensaje flash de éxito al cobrar/abrir/cerrar caja).
Reutiliza `.alerta--exito`/toast. Clasificación: **A**.

### 7.20 Serial/IMEI input
**Existe** (campo `unit_identifier`, badge "Requiere IMEI/serie"). Ver
§14 para el detalle visual completo. Reutiliza `.campo`/`.badge`.
Clasificación: **A** para la presentación visual; **D** para la
validación de disponibilidad al momento de escribir el IMEI (Etapa 1
§19.3 — `ensure_unit_available_for_sale` desconectada), que sigue
siendo una decisión funcional pendiente, no resuelta por ningún
tratamiento visual.

### 7.21 Cash Session UI
**Existe** (`session_open.html`). Reutiliza `.tarjeta`/`.campo`.
Clasificación: **A**.

### 7.22 Cash Movement UI
**Existe en backend, sin UI accesible** (Etapa 1 §19.5 — hallazgo
crítico: `CashMovementCreateView` no tiene ningún botón/enlace en
ningún template). Diseñar visualmente un punto de entrada (botón/
enlace desde `terminal.html` o `session_close.html` hacia el formulario
ya existente) es **A — solo rediseño/exposición visual de una
capacidad de backend ya construida y probada**, pero se marca como
condicionado: no debe implementarse en Design Lab sin que el usuario
confirme explícitamente que quiere exponer esta funcionalidad hoy
oculta (aunque el riesgo técnico es bajo, es un cambio de superficie de
uso real del sistema). Clasificación: **A, con confirmación previa
requerida**.

### 7.23 Closing Summary
**Existe** (`session_summary.html` — esperado/contado/diferencia).
Reutiliza `.tabla`/`.kpi`. Clasificación: **A**.

### 7.24 Receipt / Print Layout
**Existe** (`sale_receipt.html`, fuera de `apps.pos`). Ver §16-17 para
el detalle. Clasificación: **A** para el rediseño visual dentro de la
realidad HTML/`window.print()` actual; **D** para mostrar el
cambio/vuelto (campo no persistido hoy, Etapa 1 §19.7); **D** para
optimización de impresora térmica (ver §18).

---

## 8. Terminal — estructura conceptual

La secuencia visual propuesta:

```
PRODUCTOS / BÚSQUEDA
        ↓
CARRITO
        ↓
CLIENTE
        ↓
DESCUENTO
        ↓
TOTALES
        ↓
CHECKOUT
```

Esta secuencia **coincide exactamente** con el flujo real documentado
en `docs/pos-redesign-discovery.md` §2.1 (búsqueda → agregar → carrito
→ cliente → descuento global → cobrar) — no se agrega, reordena ni
omite ningún paso funcional. La única diferencia con el HTML actual de
`terminal.html` es de **presentación**: hoy Cliente y Descuento
comparten una fila de grid 2 columnas (con el defecto responsive ya
documentado, ver §19) situada después del carrito; el orden lógico
arriba es el mismo que el orden real en el DOM actual, confirmado
contra el archivo.

---

## 9. Carrito

**Jerarquía de columnas** (mismas columnas reales, sin agregar ni
quitar ninguna): Producto (con SKU secundario e IMEI/serie truncado
cuando aplica) → Cantidad → Precio unitario → Descuento → Impuesto →
Total de línea → Quitar.

**Densidad**: filas compactas (`--espacio-2` vertical, no
`--espacio-3`/`4`) para que el carrito completo sea visible sin
scroll excesivo en la mayoría de las ventas de mostrador — el mismo
principio de "visibilidad permanente del carrito" de §1.

**Precio/descuento/impuesto/total**: `.u-cifra` (mono + tabular),
alineados a la derecha (`.u-num`), igual que ya hacen las 13 pantallas
Atlas.

**Eliminación**: botón "Quitar" por fila, `.btn--contorno`/`.btn--sm`
con objetivo táctil ampliado (ver §7.8 — no se agrega edición de
cantidad, solo eliminar, que es lo único que el backend soporta hoy).

**Identificación serial/IMEI**: cuando la línea tiene `inventory_unit`,
mostrar el identificador truncado como badge secundario bajo el nombre
del producto (mismo patrón ya usado hoy, solo restilizado).

**Estado vacío**: `.estado-vacio` con ícono SVG (corrección de emoji,
ver §7.17), mensaje "El carrito está vacío" (texto ya real, sin
cambiar).

**No se agrega**: edición de cantidad/precio en línea (§7.8, pendiente
de decisión), override de precio unitario (no existe en ningún punto
del código real, no se diseña).

---

## 10. Cliente

Bloque visual con: cliente actual (`display_name` o "Consumidor
final"), `<select>` de cambio de cliente. El campo "Buscar cliente"
**no recibe tratamiento de buscador funcional** hasta que la decisión
funcional D de §7.9 se resuelva — en esta etapa se documenta
visualmente como lo que es hoy (un campo sin efecto), no se rediseña
para aparentar funcionalidad que no existe.

---

## 11. Descuentos

Bloque visual con: descuento global (%, monto), mensaje de ayuda,
bloque de autorizaciones aprobadas pendientes de consumir (reutiliza
`.alerta--exito`). Mismo mecanismo real de `apps.approvals`, sin
cambios.

---

## 12. Totales — prominencia

**Cambio de tratamiento respecto a hoy** (visual, no funcional): los 4
KPIs (Subtotal/Descuento/Impuesto/Total) dejan de ser visualmente
idénticos. Propuesta:
- Subtotal/Descuento/Impuesto: tamaño `--texto-lg`, `--pos-color-texto`,
  fila secundaria.
- **Total**: tamaño `--texto-3xl`, `--pos-color-primario` o
  `--pos-color-exito` (a definir en Design Lab según cuál transmite
  mejor "listo para cobrar"), en un bloque propio con mayor peso
  visual — mismo dato real (`sale.total`), sin ningún cálculo nuevo.

Moneda: se muestra igual que hoy (`sale.currency`), sin agregar
selector ni conversión — la doctrina de multi-moneda no está
implementada (confirmado en Etapa 1) y esta etapa no la anticipa.

---

## 13. Checkout

**Métodos de pago**: los 4 reales (`cash`/`card`/`transfer`/`other`),
sin agregar ninguno.

**Filas de pago**: método + monto, con `flex-wrap` real (corrección
responsive, §7.13).

**Total pagado**: suma visual de los montos capturados en el formset —
dato calculable en el render, sin JS.

**Diferencia/cambio**: la auditoría de Etapa 1 confirmó que el cambio
se calcula en `CheckoutView.post` mediante variables locales
(`total_recibido`/`exceso`/`cambio`), se comunica **solo** por mensaje
flash tras el submit, y nunca se persiste ni se muestra en el recibo.

> **DECISIÓN FUNCIONAL / UX PENDIENTE** — no se corrige en esta etapa.
> El Design System documenta un espacio visual reservado para mostrar
> el cambio calculado (ej. debajo del formset de pago, o en un bloque
> "Cambio a entregar" tras confirmar), pero su implementación real
> depende de si se decide (a) mantenerlo como mensaje flash únicamente,
> (b) persistirlo en `Payment` y reflejarlo en el recibo — ver
> `docs/pos-redesign-risk-map.md` §7. Clasificación: **D**.

**Mensajes de validación**: reutilizan `.alerta--peligro`/toast, mismo
mecanismo que hoy (`InsufficientPaymentError`, "el cambio solo puede
entregarse en efectivo", etc.) — sin agregar validaciones nuevas.

---

## 14. IMEI / Serial

**Búsqueda**: mismo campo único `q` del terminal — no se agrega un
buscador dedicado de IMEI.

**Selección**: cuando la búsqueda resuelve una unidad exacta, mostrarla
con un badge distintivo (ícono de identificación + últimos dígitos) en
la fila de resultado; cuando requiere selección manual, mostrar el
campo `unit_identifier` con la etiqueta real "IMEI o número de serie" y
`_campo.html` (corrección de accesibilidad, §7.4).

**Identificación**: mismo patrón truncado en carrito, completo en
recibo — sin cambios de qué se muestra, solo de cómo.

**Asociación con línea**: visual — un ícono/badge en la línea del
carrito que indica "unidad serializada asociada", reutilizando el
badge ya propuesto en §9.

**Validación y errores**: el mensaje "No se encontró ninguna unidad con
ese IMEI/serie" ya existe y se reutiliza sin cambios. La ausencia de
validación de disponibilidad **al agregar** (unidad ya vendida/
reservada/dañada) sigue siendo la decisión funcional pendiente más
severa de Etapa 1 (`docs/pos-redesign-risk-map.md` §3) — el Design
System no la resuelve ni la oculta visualmente; como mucho, reserva un
lugar para un futuro mensaje de advertencia inmediato si esa función se
autoriza más adelante. Clasificación: **D**.

---

## 15. Caja

**Lenguaje visual**:
- Caja abierta → `.badge--verde` "Abierta", con nombre de caja/cajero/
  hora de apertura.
- Caja cerrada / sin sesión → `.badge--neutro` o `.alerta--advertencia`
  "Sin caja abierta", con enlace a abrir.
- Movimientos → tabla reutilizando `.tabla`, columnas Tipo/Monto/Motivo/
  Usuario/Fecha (mismas columnas reales de `session_close.html`/
  `session_summary.html`, hoy duplicadas — se documenta como candidato
  de `{% include %}` compartido en Design Lab, sin cambiar su
  contenido).
- Efectivo esperado / contado / diferencia → 3 KPIs con `.u-cifra`,
  diferencia con color condicional (positivo → `--pos-color-exito`,
  negativo → `--pos-color-peligro`, cero → neutro) — mismo dato real
  (`expected_cash`/`counted_cash`/`difference`), sin ningún cálculo
  nuevo.

**No se agrega**: ninguna acción nueva, ningún campo de denominaciones
(la doctrina de moneda no está implementada — ver
`docs/pos-redesign-risk-map.md` §4, **D**, fuera de alcance de esta
etapa por completo).

---

## 16. Recibo

Tratamiento visual futuro, respetando la realidad técnica confirmada en
Etapa 1 (HTML + `window.print()`, sin PDF backend, sin nueva
dependencia):

- **Encabezado**: nombre del tenant (`request.tenant.name`), sin logo
  (no existe hoy un campo de logo de tenant en el modelo — no se
  inventa uno).
- **Número, cliente, vendedor, fecha, estado**: mismos datos reales,
  con jerarquía tipográfica clara (número de venta destacado, resto
  secundario).
- **Líneas**: mismas columnas reales (descripción, SKU, IMEI/serie,
  cantidad, precio, descuento, impuesto, total), con `.u-cifra` en
  columnas numéricas.
- **Totales**: mismo bloque de Subtotal/Descuento/Impuesto/Total, con
  el Total visualmente más prominente (mismo criterio de §12).
- **Pagos**: tabla de método + monto, ya real.
- **Notas**: si existen, sin cambios.
- **Cambio/vuelto**: ver §13 — **D**, no se agrega hasta resolver la
  decisión funcional.
- **Impresión**: se mantiene `window.print()` + `@media print`, sin
  PDF backend, sin nueva dependencia — **explícitamente descartado**
  cualquier `reportlab`/`weasyprint`/`xhtml2pdf`, coherente con la
  decisión ya documentada en el propio código (`apps/sales/models.py`
  docstring).
- **Shell**: Etapa 1 confirmó que `sale_receipt.html` extiende
  `base.html` directamente, no `layout_app.html` — sin sidebar/topbar
  Atlas, con el azul compartido (`#1d4ed8`) en vez del azul Atlas
  (`#1D4E89`). Se documenta como **pregunta de diseño para Design Lab,
  no resuelta aquí**: mantener el aislamiento deliberado (documento
  imprimible limpio, sin chrome de navegación) es una opción legítima
  y común en documentos imprimibles — la alternativa (envolver en
  `layout_app.html`) tiene la desventaja de imprimir también el
  sidebar/topbar salvo que se oculten con `@media print`, ya un patrón
  usado (`.no-imprimir`). Clasificación: **A** de cualquier forma —
  ninguna opción implica lógica nueva, solo una decisión de qué
  plantilla padre usar.

---

## 17. Impresión

Reafirmado: **no se implementa PDF en esta etapa ni se propone como
parte del Design System**. La impresión sigue siendo responsabilidad
del navegador (`window.print()` + diálogo "Guardar como PDF" del
sistema operativo del usuario). El Design System solo define el
tratamiento visual `@media print` (tipografía, tamaño de tabla, ocultar
controles vía `.no-imprimir`), reutilizando el patrón ya existente en
`sale_receipt.html`/`proforma_print.html`/`quotation_print.html`.

---

## 18. Impresión térmica (58/80mm)

Etapa 1 detectó que el recibo actual está pensado para hoja carta/A4
(`max-width:800px`), no para impresoras térmicas de recibo angosto.

**Qué requeriría visualmente** (si se autoriza en el futuro): una hoja
de estilo `@media print` alternativa con ancho fijo de 58mm/80mm,
tipografía monoespaciada de mayor tamaño relativo, columnas reducidas
(posiblemente sin columna de impuesto separada, solo total con
impuesto incluido), y renuncia a cualquier elemento decorativo — un
diseño de recibo térmico es intrínsecamente distinto de uno de hoja
completa, no una simple compresión del mismo layout.

**Qué requeriría técnicamente**: decidir si se detecta el tipo de
impresora vía CSS (`@media print and (width: ...)` no es fiable para
detectar hardware térmico real) o si se ofrece una vista/URL alternativa
explícita ("Recibo térmico") que el cajero elige manualmente — esto sí
sería una decisión funcional (una nueva vista/ruta), no solo visual.

> **DECISIÓN FUNCIONAL / TÉCNICA PENDIENTE — no implementada.**
> Clasificación: **D**. Documentado como especialización futura
> posible, no autorizada para Design Lab en esta etapa.

---

## 19. Responsive

Comportamiento conceptual, sin implementar:

| Viewport | Comportamiento propuesto |
|---|---|
| Escritorio (≥1024px) | Layout actual, con el fix de grid Cliente/Descuento y flex-wrap de pago ya aplicados (ver abajo). Sidebar Atlas expandido o compacto según el toggle ya existente. |
| Laptop (768-1023px) | Igual que escritorio; sidebar puede colapsar a compacto automáticamente si el usuario ya lo configuró (mecanismo ya existente, sin cambios). |
| Tablet (640-767px) | Grid Cliente/Descuento colapsa a 1 columna (aplicando `.u-grid-2col`, ya existente en Atlas, nunca aplicado hoy al terminal). Filas de pago con `flex-wrap: wrap` real. Carrito mantiene scroll horizontal contenido (`.tabla-envoltorio`, ya funciona). |
| Móvil (<640px) | Mismo colapso de grid + flex-wrap. Los inputs de la fila de alta rápida (cantidad/descuento/IMEI) pasan de ancho fijo en `rem` a ancho fluido/porcentual dentro de su contenedor. Botón de cobro ocupa el ancho completo disponible para maximizar el objetivo táctil. |

**Grid Cliente/Descuento** (`terminal.html:125`, `grid-template-columns:
1fr 1fr` inline): la corrección propuesta es aplicar la clase
`.u-grid-2col` ya existente en `design-system-erp.css` (el mismo fix ya
usado en `customer_collections.html`) — no se inventa un mecanismo
nuevo, se aplica uno ya aprobado y probado en FASE 5. **No se
implementa en esta etapa** (Etapa 2 es solo especificación).

**Filas de pago sin `flex-wrap`**: mismo criterio — agregar
`flex-wrap: wrap` (y idealmente migrar a una clase reutilizable en vez
de `style=""` inline, seguiendo el mismo principio que motivó
`.u-grid-2col`). No implementado en esta etapa.

**Scroll y teclado táctil**: el teclado virtual en móvil/tablet no debe
tapar el campo de búsqueda activo ni el botón de cobro — esto es un
criterio de diseño para el Design Lab (evitar campos fijos en la parte
inferior de la pantalla sin espacio de reserva), no requiere ningún
cambio de código en esta etapa.

---

## 20. Accesibilidad

Reglas, extendiendo los patrones Atlas ya existentes sin inventar un
sistema nuevo:

- **Labels**: todo campo debe pasar por `_campo.html` (o su equivalente
  con `<label for>` explícito) — corrige la ausencia real detectada en
  la fila de alta rápida de producto (§7.4).
- **Foco**: `:focus-visible` ya definido globalmente en `base.css`, se
  hereda sin cambios; el campo de búsqueda del terminal es candidato a
  `autofocus` (atributo HTML declarativo, no JS) en Design Lab.
- **Contraste**: los tokens Atlas ya declarados (`--color-texto:
  #111827` sobre `--color-fondo: #F5F6F8`/`--color-superficie:
  #FFFFFF`) ya cumplen un contraste alto — se heredan sin cambios.
- **Botones**: objetivo táctil mínimo recomendado 44×44px CSS
  (criterio WCAG 2.5.5, nivel AAA, pero razonable para un POS de
  mostrador) para los controles de mayor uso (Agregar, Quitar,
  Confirmar y cobrar) — hoy `.btn`/`.btn--sm` de Atlas no garantiza ese
  mínimo en todos los casos; ajustar el padding en el contexto
  `.shell--pos` sin cambiar `.btn` globalmente (evita afectar el resto
  del ERP).
- **Estados**: todo estado visual (badge, alerta) debe llevar también
  texto legible por lector de pantalla, nunca solo color — ya es el
  patrón Atlas, se reafirma para POS.
- **`aria-*`**: reutilizar `aria-label`/`aria-current`/`aria-hidden` ya
  usados en el resto del proyecto; ninguna pantalla del POS usa tabs
  hoy, por lo que `role="tab"` no aplica.
- **Mensajes de error**: siempre junto al campo que falló (patrón
  `_campo.html`) además del toast global — hoy los errores de negocio
  del checkout (descuento no autorizado, IMEI no encontrado) solo
  llegan por mensaje flash tras recarga completa; el Design System
  reserva espacio visual para un mensaje en contexto, pero mostrarlo
  antes del submit requeriría JS nuevo (fuera de alcance, ver §24).
- **Navegación por teclado**: orden de tabulación debe seguir la
  secuencia visual de §8 (Producto → Carrito → Cliente → Descuento →
  Pago → Cobrar) — verificable sin JS, es una cuestión de orden en el
  DOM/HTML.
- **Targets táctiles**: ver "Botones" arriba.

---

## 21. Estados — tratamiento visual, nunca de negocio

Se diferencia explícitamente **estado visual** (cómo se ve) de
**estado de negocio** (qué significa, definido por el modelo/servicio
real, nunca modificado aquí):

| Estado de negocio real | Tratamiento visual propuesto |
|---|---|
| Carrito/resultados vacíos | `.estado-vacio` + ícono SVG (nunca emoji — corrige el hallazgo de Etapa 1) |
| Error de validación | `.alerta--peligro` / borde de campo `--pos-color-peligro` |
| Éxito (venta cobrada, caja abierta/cerrada) | `.alerta--exito` / toast |
| `ApprovalRequest.PENDING` | `.alerta--advertencia`, "Autorización solicitada" |
| `ApprovalRequest.APPROVED` (no consumida) | `.alerta--exito`, "Autorización disponible" |
| `CashSession.OPEN` | `.badge--verde` |
| `CashSession.CLOSED` / sin sesión | `.badge--neutro` / `.alerta--advertencia` |
| `Payment.CONFIRMED` | `.badge--verde` |
| `Payment.VOIDED` | `.badge--neutro`, texto atenuado |
| `Sale.DRAFT` | Sin badge (es el carrito activo, no un documento cerrado) |
| `Sale.CONFIRMED` | `.badge--verde` (en el recibo/detalle, no en el terminal) |
| `Sale.CANCELED` | `.badge--peligro` |
| `Sale.RETURNED`/`PARTIALLY_RETURNED` | `.badge--advertencia` — visible solo en `apps.sales`, el POS no produce estos estados (Etapa 1 confirmado) |
| `InventoryUnit.EN_STOCK` | Sin badge especial (estado normal) |
| `InventoryUnit.VENDIDO`/`RESERVADO`/`DANADO`/etc. (si se muestra en una futura validación de disponibilidad) | `.badge--peligro`/`.badge--advertencia` — **el mostrar esto al agregar al carrito depende de la decisión funcional D de §14**, aquí solo se define cómo se vería si se autoriza |

Ningún estado de esta tabla es inventado — todos provienen de los
enums reales documentados en `docs/pos-redesign-discovery.md` §11.

---

## 22. Permisos — consideración visual únicamente

Etapa 1 encontró que `pos.use`, `cash.view`, y todos los permisos de
`apps/sales/views.py` están definidos en el catálogo pero no aplicados
por ninguna vista (`docs/pos-redesign-risk-map.md` §1). **Esta etapa no
corrige esa brecha.** El Design System define únicamente cómo se vería
la representación visual de un estado de autorización, **para cuando
esa brecha se resuelva como decisión funcional separada** (ver §26):

- **Acción disponible** (el usuario tiene el permiso): botón/control en
  su estado normal, sin tratamiento especial.
- **Acción no disponible** (el usuario no tiene el permiso, una vez que
  la verificación exista): el control se oculta o se deshabilita con
  `disabled` + un `title`/tooltip explicando por qué — mismo patrón que
  Atlas ya usa en otros módulos para acciones restringidas por rol
  (ej. edición de campos sensibles de RRHH, FASE 13).
- **Aprobación pendiente**: ya cubierto en §21 (`ApprovalRequest`).
- **Acceso restringido** (intento de acceder a una vista sin permiso,
  una vez enforced): página de error estándar del proyecto, reutilizada
  sin cambios — el POS no necesita una pantalla de error propia.

Ninguno de estos tratamientos se implementa en esta etapa — son
especificación para el día en que la decisión funcional de §26.1 se
apruebe e implemente.

---

## 23. Arquitectura CSS

Estrategia propuesta (documentada, no implementada):

- Nuevo archivo `static/css/design-system-pos.css` (nombre propuesto),
  scopeado bajo `.shell--pos` — mismo patrón exacto que
  `design-system-erp.css` bajo `.shell--erp` en FASE 5.
- **Reutiliza de `design-system-erp.css`**: todos los tokens de color/
  tipografía ya heredados pasivamente (el POS ya vive dentro de
  `.shell--erp` hoy, confirmado en Etapa 1) — `.shell--pos` no
  redeclara `--color-primario` ni ningún otro token ya resuelto por
  `.shell--erp`, solo añade lo que Atlas no cubre (densidad de tabla,
  tamaño de objetivo táctil, prominencia de Total).
- **Reutiliza de `base.css`/`design-system.css`**: `.btn`, `.tarjeta`,
  `.badge`, `.campo`, `.alerta`, `.tabla`, `.estado-vacio`,
  `.kpi-grid`/`.kpi` — sin reescribir ninguno, solo por sustitución de
  token donde `.shell--pos` defina algo adicional (mismo mecanismo que
  ya usa `.shell--erp`).
- **Nunca toca `base.css`**: cero cambios a la librería de tokens raíz
  compartida.
- **Nunca toca `.shell--saas`**: cero reglas nuevas bajo ese selector.
- **Nunca toca `.shell--erp` fuera de lo ya existente**: `.shell--pos`
  es aditivo, no reemplaza ninguna regla ya escrita en
  `design-system-erp.css`.
- Namespace de clases nuevas propuesto: prefijo `.pos-` (ej.
  `.pos-carrito`, `.pos-total`, `.pos-fila-pago`) para evitar toda
  colisión con las ~3300 líneas combinadas de `design-system.css` +
  `design-system-erp.css` — mismo riesgo de colisión ya documentado en
  Etapa 1 §17, resuelto aquí con un namespace explícito en vez de
  reutilizar nombres genéricos.

**No se crea ningún archivo CSS en esta etapa.**

---

## 24. Arquitectura JS

El discovery confirmó que el POS no tiene JavaScript propio hoy (cero
AJAX, cero atajos de teclado, cero cálculo en vivo). Esta etapa **no
introduce JavaScript nuevo**. Se documenta únicamente, para referencia
de una futura etapa, qué interacciones visuales *implicarían* JS y si
la función subyacente ya existe:

| Interacción visual candidata | ¿Requiere JS? | ¿La función ya existe en backend? |
|---|---|---|
| `autofocus` en campo de búsqueda | No (atributo HTML) | N/A |
| Cálculo de cambio en vivo antes de submit | Sí | Sí (la fórmula ya existe en `CheckoutView.post`, solo no se ejecuta en el cliente) |
| Edición de cantidad de línea sin recargar | Sí (o al menos un submit adicional) | No — requiere decisión funcional (§7.8) |
| Confirmación antes de "Confirmar y cobrar" | Sí (`confirm()`, ya usado en "Cancelar carrito") | Sí — mismo patrón ya existente, trivial de replicar si se autoriza |
| Validación de disponibilidad de IMEI en vivo | Sí (o server round-trip) | Parcial — la función existe (`ensure_unit_available_for_sale`) pero está desconectada (§14, decisión D) |

Ninguna de estas se implementa. Se documentan para que Design Lab (o
una etapa posterior de implementación) sepa cuáles son puramente
visuales/declarativas y cuáles requieren JS nuevo + posible decisión
funcional.

---

## 25. Riesgos

1. **Colisión de nombres CSS** si el namespace `.pos-` (§23) no se
   respeta estrictamente en Design Lab.
2. **Confundir "componente visual nuevo" con "funcionalidad nueva"** —
   mitigado por la clasificación A/B/C/D obligatoria de §27, aplicada a
   los 24 componentes de §7.
3. **Diseñar el Quantity Control (§7.8) o el Checkout Summary dinámico
   (§7.14) como si ya fueran funcionales** en Design Lab, adelantándose
   a una decisión funcional no tomada — deben quedar explícitamente
   fuera de alcance hasta nueva autorización.
4. **Aplicar el fix de responsive (`.u-grid-2col`, flex-wrap) como
   parte de un rediseño visual más amplio sin separar el commit** —
   Etapa 3 deberá decidir si ese fix puntual se adelanta como cambio
   aislado o se incluye en el rediseño completo del terminal.
5. **Recibo**: cualquier decisión de reintegrar `sale_receipt.html` al
   shell Atlas debe verificar que `.no-imprimir`/`@media print` sigan
   ocultando correctamente el sidebar/topbar — riesgo bajo pero real de
   imprimir contenido no deseado si se hace descuidadamente.

---

## 26. Decisiones pendientes (consolidado, clasificación D)

Mismas 8 decisiones de `docs/pos-redesign-risk-map.md`, más 2 nuevas
identificadas durante esta etapa de diseño:

1. Brecha de autorización real en `apps.pos`/`apps.sales` (§22).
2. `cash.view` no aplicado en `CashSessionSummaryView` (§22).
3. Validación de disponibilidad de stock/unidad al agregar al carrito
   (§14).
4. Cierre de caja por denominaciones (§15, fuera de alcance completo).
5. Movimiento manual de caja — exposición de UI condicionada a
   confirmación explícita (§7.22).
6. Devolución de mercancía accesible desde el flujo del POS (no
   detallada visualmente en esta etapa — sigue en `apps.sales`).
7. Persistencia de `amount_received`/`change_amount` y su reflejo en
   el recibo (§13, §16).
8. Integración de `TaxCode`/`SaleItemTax` al POS (no rediseñada
   visualmente en esta etapa — el POS sigue mostrando solo el impuesto
   plano).
9. **(Nueva)** Edición de cantidad de una línea ya agregada al carrito
   (§7.8, Quantity Control).
10. **(Nueva)** Impresión térmica 58/80mm — especialización futura,
    requiere decisión técnica además de funcional (§18).

---

## 27. Propuestas vs. funcionalidad — clasificación obligatoria

Aplicada explícitamente en §7 a los 24 componentes. Resumen por
categoría:

- **A — Existente, solo rediseño visual**: POS Shell, POS Header
  (visual sobre datos ya disponibles), Product Search, Product Result,
  Product Identification, Cart, Cart Line, Customer Selector (el
  `<select>`), Discount Section, Totals, Payment Form, Payment Row,
  Cash Status, Approval Notice, Empty State, Error State, Success
  Feedback, Serial/IMEI input (presentación), Cash Session UI,
  Cash Movement UI (exposición, con confirmación previa), Closing
  Summary, Receipt/Print Layout (dentro de la realidad HTML actual).
- **B — Existente pero requiere cambio UX (no implementar todavía)**:
  Quantity Control (edición de línea).
- **C — Nueva funcionalidad (no implementar)**: Checkout Summary con
  cálculo en vivo (JS).
- **D — Decisión funcional (requiere aprobación independiente)**:
  permisos (§22), cambio/vuelto persistido (§13/§16), recibo térmico
  (§18), validación de disponibilidad IMEI/stock al agregar (§14),
  búsqueda real de cliente en checkout (§7.9), devolución accesible
  desde POS, integración `TaxCode`, edición de línea si se decide que
  sí requiere cambio de backend.

---

## 28. Reglas estrictas contra funcionalidad inventada

Reafirmadas para Etapa 3 (Design Lab), que deberá seguir este
documento como fuente de verdad de diseño:

- Ningún componente clasificado B, C o D se implementa visualmente como
  si ya fuera funcional — puede mostrarse como maqueta/estado
  deshabilitado explícitamente marcado, nunca como si funcionara.
- Ningún dato mostrado puede ser inventado — todo campo/cifra/estado
  visual debe corresponder a un campo/cálculo/enum real ya confirmado
  en `docs/pos-redesign-discovery.md`.
- Ningún color/tipografía/radio/sombra fuera de los tokens Atlas ya
  aprobados (§4-6).
- Ninguna función de backend (permisos, validación de stock, cambio
  persistido, impresión térmica, devoluciones desde POS, edición de
  línea, integración de `TaxCode`) se implementa en Design Lab sin una
  aprobación explícita separada, específica para esa decisión.
- El namespace `.shell--pos`/`.pos-*` (§23) es obligatorio para
  cualquier CSS nuevo de Design Lab — nunca reutilizar un nombre de
  clase ya usado por `design-system.css`/`design-system-erp.css` sin
  el prefijo.
- El POS sigue sin JavaScript propio salvo que una decisión funcional
  específica lo autorice explícitamente (§24).
