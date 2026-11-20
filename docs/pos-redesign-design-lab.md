# FASE 7 — POS LAB PROFUNDO — ETAPA 3 — POS DESIGN LAB

Exploración controlada de direcciones visuales/UX para el POS. Cero
código productivo modificado. Fuentes leídas antes de diseñar:
`docs/pos-redesign-discovery.md`, `docs/pos-redesign-risk-map.md`,
`docs/pos-redesign-design-system.md`, `docs/erp-redesign-design-system.md`,
`docs/erp-redesign-design-lab-decision-log.md`, más inspección directa
de `apps/pos/`, `apps/sales/`, `apps/approvals/`, `apps/inventory/`,
`apps/customers/`, `templates/layout_app.html`,
`static/css/design-system-erp.css`, `static/css/base.css`,
`static/js/ui.js`.

**Corrección contra el código real**: `apps/payments/` y `apps/credit/`,
mencionados en la instrucción como directorios a inspeccionar, **no
existen** como apps independientes (verificado por `Glob`, cero
resultados). `Payment`/`PaymentAllocation`/`PaymentMethod` viven en
`apps.sales.models`; `credit_enabled`/`credit_limit` viven en
`apps.customers.models.Customer` (vía `ContactoMixin`). Este documento
usa las ubicaciones reales, no las mencionadas en la instrucción — regla
explícita de esta etapa: "no asumir que los documentos están
actualizados si el código demuestra otra cosa".

---

## 1. Objetivo del POS Lab

Se explora cómo debería verse y organizarse visualmente el POS
operativo real, comparando tres arquitecturas visuales distintas, sin
elegir ninguna todavía y sin inventar ninguna funcionalidad que el
código no soporte hoy.

**Por qué el POS necesita una exploración específica** (y no una
migración directa del patrón Atlas ya usado en las 13 pantallas
administrativas de FASE 5): el POS se opera de pie o sentado en un
mostrador, en sesiones repetitivas de alta frecuencia, a menudo con
tiempo de atención al cliente de por medio — un patrón de uso
radicalmente distinto al de un formulario de Recursos Humanos o un
reporte contable, que se completan una vez y se leen con calma.

**Qué permanece heredado de Atlas**: shell (sidebar/topbar), tipografía
(IBM Plex Sans/Mono), paleta de color completa, radios, sombras,
componentes base (`.btn`, `.tarjeta`, `.badge`, `.campo`, `.alerta`,
`.tabla`, `.estado-vacio`) — confirmado en `docs/pos-redesign-design-system.md`
§2, sin cambios en esta etapa.

**Qué puede especializarse**: densidad de tabla del carrito, tamaño de
objetivo táctil, prominencia del Total, composición espacial de la
Terminal, tratamiento responsive del grid Cliente/Descuento y de las
filas de pago.

**Qué queda fuera de este Lab**: las 10 decisiones funcionales
pendientes de `docs/pos-redesign-design-system.md` §26 (permisos,
cambio/vuelto persistido, recepción térmica, validación de
disponibilidad IMEI/stock, edición de línea de carrito, etc.) — se
consolidan de nuevo en §26 de este documento, sin resolverse.

---

## 2. Principios de diseño

Se parte literalmente de los 11 principios de
`docs/pos-redesign-design-system.md` §1, sin reemplazarlos. Traducción
visual al POS, en el mismo orden de prioridad que exige esta etapa:

1. **Velocidad de operación** → mínimo de clics/pulsaciones entre
   buscar y cobrar; controles de alta frecuencia (Agregar, Quitar,
   Cobrar) sin pasos intermedios nuevos.
2. **Lectura inmediata** → `.u-cifra` (mono + tabular) en toda cifra,
   heredado sin cambios de Atlas.
3. **Total claramente visible** → jerarquía tipográfica propia para el
   Total (ver §13), distinta de Subtotal/Descuento/Impuesto.
4. **Carrito siempre comprensible** → densidad de fila ajustada, nunca
   comprimida al punto de perder legibilidad (ver §10).
5. **Errores fáciles de detectar** → color + texto + posición
   consistente (nunca solo color), reutilizando `.alerta`/`.badge`.
6. **Operación con teclado** → orden de tabulación siguiendo el flujo
   real (§4), foco visible heredado de `base.css`.
7. **Operación táctil** → objetivo mínimo 44×44px en controles de alta
   frecuencia (criterio ya fijado en `docs/pos-redesign-design-system.md`
   §20).
8. **Pantallas pequeñas** → las tres direcciones deben resolver tablet
   y móvil, no solo escritorio (ver §19).
9. **Baja carga cognitiva** → agrupación visual clara por zona
   funcional (Producto/Carrito/Cliente/Descuento/Total/Checkout),
   nunca todo al mismo nivel visual.
10. **Consistencia con Atlas** → ninguna dirección introduce un color,
    tipografía o radio fuera de los ya aprobados.
11. **Ausencia de funcionalidad inventada** → cualquier elemento que
    implique una capacidad de backend no confirmada se marca
    explícitamente como **DECISIÓN FUNCIONAL PENDIENTE**, en las tres
    direcciones por igual.

---

## 3. Mapa real del POS

Pantallas reales confirmadas (`docs/pos-redesign-discovery.md` §1):

```
Terminal              → apps/pos/templates/pos/terminal.html
Register List         → apps/pos/templates/pos/register_list.html
Session Open          → apps/pos/templates/pos/session_open.html
Session Close          → apps/pos/templates/pos/session_close.html
Session Summary        → apps/pos/templates/pos/session_summary.html
Collections Search     → apps/pos/templates/pos/collections_search.html
Customer Collections   → apps/pos/templates/pos/customer_collections.html
Sale Receipt           → apps/sales/templates/sales/sale_receipt.html
```

**Dentro del alcance profundo del POS Lab**: Terminal, Register List,
Session Open, Session Close, Session Summary, Receipt/impresión —
coincide exactamente con el alcance que la instrucción de esta etapa
delimita.

**Relacionadas pero no rediseñadas en este Lab**: Collections Search,
Customer Collections — ya migradas a Atlas en FASE 5 (Etapa 3A), fuera
de este alcance, sin cambios propuestos aquí.

No se crea ninguna pantalla nueva — mismas 8, sin excepción.

---

## 4. Flujo real

Diagrama verificado contra `apps/pos/services.py`/`apps/pos/views.py`
(`docs/pos-redesign-discovery.md` §2.1):

```
PRODUCTO (búsqueda + resultado)
   ↓
CARRITO (agregar línea)
   ↓
CLIENTE (opcional, "Consumidor final" por defecto)
   ↓
DESCUENTO (línea y/o global, opcional)
   ↓
TOTALES (recalculados en cada paso anterior)
   ↓
CHECKOUT (formset de pago)
   ↓
PAGO (confirmar y cobrar → confirm_sale + record_payment)
   ↓
RECIBO (sales:sale_receipt)
```

Este diagrama **coincide** con el propuesto por la instrucción — no
requirió corrección. Nota de precisión: Cliente y Descuento no son
pasos secuenciales estrictos en el código (ambos son formularios
independientes que pueden enviarse en cualquier orden, o no enviarse,
mientras la venta esté en `DRAFT`) — el diagrama representa el orden
lógico/recomendado de uso, no una máquina de estados que lo fuerce.

---

## 5. Tres direcciones visuales

### Dirección A — POS Operativo Compacto

Enfocada en velocidad, densidad, teclado, lectura rápida, operador
experimentado, mínima distracción. Búsqueda prominente en la parte
superior con `autofocus`; resultados en filas compactas de una sola
línea (`--espacio-1`/`2` verticales); carrito denso ocupando la mayor
parte de la pantalla; Total en bloque fijo de gran tamaño; checkout en
una franja inferior claramente separada, siempre visible sin scroll
adicional una vez que hay líneas en el carrito. Menor uso de tarjetas
(`.tarjeta`) — más uso de separadores simples (`border-bottom`) para
reducir el "peso" visual de contenedores repetidos.

### Dirección B — POS Balanceado Atlas

Enfocada en máxima integración con Atlas, claridad, densidad moderada,
jerarquía empresarial, consistencia con el resto del ERP — debe
sentirse como "Budun ERP Atlas + especialización POS", no como una
aplicación aparte. Mantiene el uso de `.tarjeta` para agrupar Cliente/
Descuento/Checkout (igual que las 13 pantallas ya migradas), con
densidad de tabla similar a `.tabla` estándar (ligeramente más
compacta que una tabla administrativa, pero sin llegar a la densidad
de la Dirección A). El Total se destaca dentro de una tarjeta propia,
consistente visualmente con el resto de `.kpi`/`.tarjeta` del ERP.

### Dirección C — POS Táctil / Híbrido

Enfocada en pantallas táctiles, tablets, terminales de venta: botones
de mayor tamaño (objetivo táctil 48-56px, por encima del mínimo de
44px), mayor separación entre controles interactivos para prevenir
pulsaciones accidentales, menor dependencia del mouse (controles más
grandes también facilitan precisión con trackpad/mouse, sin
penalizarlo), operación híbrida teclado + touch. Resultados de
búsqueda presentados como filas más altas con mayor padding vertical;
formset de pago con filas más separadas entre sí. Sigue siendo
visualmente compatible con Atlas (misma paleta, misma tipografía) —
la diferencia es de escala/espaciado, no de identidad visual.

---

## 6. Comparación de las 3 direcciones

Sin puntuaciones, sin ganador declarado — información para una
decisión posterior del usuario.

| Criterio | Dirección A | Dirección B | Dirección C |
|---|---|---|---|
| Velocidad | Máxima — mínima fricción visual, pensada para repetición constante | Buena — algo más de contenedor visual entre pasos | Moderada — más espacio entre controles ralentiza ligeramente el escaneo visual, pero reduce errores de toque |
| Densidad | Alta | Moderada | Baja-moderada |
| Lectura del total | Muy alta, bloque fijo grande, mínima distracción alrededor | Alta, dentro de tarjeta con el mismo tratamiento que otros KPI del ERP | Alta, bloque grande con más aire alrededor |
| Teclado | Óptimo — flujo diseñado para tabulación rápida sin mouse | Bueno — mismo patrón de tabulación que el resto del ERP | Bueno, pero el mayor espaciado entre campos alarga ligeramente el recorrido de tabulación |
| Touch | Aceptable — objetivos estándar de Atlas (~36-40px), no optimizados | Aceptable — igual que Atlas | Óptimo — objetivos ampliados (48-56px), mayor separación |
| Tablet | Requiere el fix de responsive (grid/flex-wrap) para no romperse, igual que las otras dos | Igual — depende del mismo fix, sin ventaja/desventaja propia | Mejor adaptada por diseño — pensada desde el inicio para esta superficie |
| Laptop | Óptima — es su caso de uso principal | Óptima | Buena — el mayor espaciado usa más scroll vertical en pantallas de menor altura |
| Coherencia con Atlas | Menor — reduce el uso de `.tarjeta`, se aleja algo del patrón visual del resto del ERP | Máxima — es la opción explícitamente diseñada para parecerse al resto de Atlas | Alta en color/tipografía, moderada en composición (mayor escala que el resto del ERP) |
| Complejidad visual | Baja (pocos contenedores, mucha tabla/lista) | Moderada (uso normal de tarjetas, igual que hoy) | Moderada (menos contenedores que B, pero mayor escala de controles) |
| Riesgo de implementación | Bajo-moderado — reduce el uso de componentes ya existentes (`.tarjeta`), requiere más CSS nuevo bajo `.shell--pos` | Bajo — reutiliza el patrón ya probado de Atlas casi sin cambios | Moderado — requiere una escala de tamaño de botón/input nueva, más superficie de CSS nuevo que B |
| Riesgo de inventar UX | Bajo si se sigue estrictamente §28 de Etapa 2 (ninguna reduce controles, solo su presentación) | Muy bajo — es la opción más conservadora respecto a lo ya aprobado | Bajo — el escalado no implica nueva funcionalidad, pero exige más disciplina para no "rellenar" el espacio extra con controles inventados |

---

## 7. POS Shell

Las tres direcciones comparten el mismo shell base: sidebar Atlas (8
grupos, 21 rutas reales, toggle compacto/expandido ya existente),
topbar Atlas (marca, badge de tenant, menú de usuario), heredados sin
cambios de `layout_app.html`/`.shell--erp`, tal como confirma
`docs/pos-redesign-design-system.md` §3 (arquitectura de convivencia
`shell--erp` + `shell--pos`, adoptada como dirección provisional para
este Lab, **no implementada**).

**Breadcrumb**: `terminal.html` es hoy la única pantalla del POS sin
`nav.migas` (confirmado en Etapa 1). Las tres direcciones proponen
mantenerlo así deliberadamente — un breadcrumb añade un paso de
lectura antes de la acción principal, contrario al principio de
velocidad; Register List/Session Open/Close/Summary sí lo conservan
(igual que hoy) porque son pantallas de menor frecuencia de uso.

**Título/contexto de terminal-caja**: las tres direcciones proponen un
encabezado compacto (POS Header, `docs/pos-redesign-design-system.md`
§7.2) con caja/cajero/estado de sesión siempre visible en la parte
superior del área de contenido — mismo dato real (`CashSession`
activa), solo presentado de forma más prominente que el banner actual.

**Área operativa / contenido principal**: hereda `.main` con fondo
`--color-fondo` de Atlas en las tres direcciones.

**Responsive/collapse/scroll del shell**: sin cambios — el mecanismo
off-canvas de sidebar (breakpoint 1024px) y el toggle compacto/
expandido ya funcionan igual para las tres direcciones, heredados sin
tocar.

No se agrega ningún control al shell que no exista hoy (sin buscador
global, sin notificaciones, sin acciones rápidas nuevas).

---

## 8. Terminal — exploración profunda

Interpretación explícita de esta etapa: las "Variante A/B/C" de
composición que pide la instrucción se mapean 1:1 sobre las Direcciones
A/B/C de §5 (evita explorar 9 combinaciones cuando 3 ya cubren el
espacio de diseño pedido: A = búsqueda+resultados arriba, carrito
dominante a la derecha; B = zonas claramente separadas por tarjeta; C =
composición optimizada para touch/tablet).

### Variante A (= Dirección A)
Búsqueda a todo el ancho superior. Debajo, dos columnas en escritorio:
resultados de búsqueda a la izquierda (estrechos, compactos), carrito
dominante a la derecha (más ancho, siempre visible). Cliente/Descuento
colapsan a una franja horizontal delgada entre carrito y checkout.
Checkout en la franja inferior fija.
- **Búsqueda**: campo único `q`, ancho completo, `autofocus`.
- **Resultados**: fila de una línea, precio y cantidad alineados a la
  derecha.
- **Identificación**: nombre + SKU en la misma línea, IMEI truncado
  como badge pequeño a la derecha cuando aplica.
- **Carrito**: tabla densa, columnas Producto/Cant/Precio/Desc/Imp/
  Total/Quitar.
- **Cliente**: una línea de texto + enlace "Cambiar" (abre el
  `<select>` existente, sin nuevo comportamiento).
- **Descuento**: colapsado por defecto, expandible (mismo campo real,
  solo presentación).
- **Totales**: bloque fijo a la derecha del checkout, Total en
  `--texto-3xl`.
- **Checkout**: franja inferior con formset de pago + botón de cobro
  de ancho completo.
- **Errores**: banda de alerta justo sobre el checkout, siempre en la
  misma posición.
- **Estado vacío**: mensaje breve centrado en el área de carrito, sin
  ilustración grande (coherente con "mínima distracción").

### Variante B (= Dirección B)
Layout en tarjetas separadas, apiladas verticalmente en el orden real
del flujo (§4): tarjeta Búsqueda+Resultados, tarjeta Carrito, tarjeta
Cliente, tarjeta Descuento, tarjeta Totales, tarjeta Checkout — mismo
patrón de `.tarjeta` que el resto del ERP Atlas.
- **Búsqueda**: dentro de su propia tarjeta, con resultados en tabla
  estándar (misma densidad que `.tabla` ya usa en Atlas).
- **Resultados**: fila estándar, con más aire que la Variante A.
- **Identificación**: igual que A, pero con más espacio entre nombre y
  SKU.
- **Carrito**: tabla estándar dentro de su tarjeta.
- **Cliente/Descuento**: dos tarjetas lado a lado en escritorio (grid
  2 columnas — con el fix `.u-grid-2col` ya existente, ver §19),
  apiladas en móvil.
- **Totales**: tarjeta propia con `.kpi-grid`, Total destacado dentro
  de la misma tarjeta con mayor tamaño que los otros 3 KPIs.
- **Checkout**: tarjeta final, mismo patrón visual que el resto.
- **Errores/vacío**: mismos patrones `.alerta`/`.estado-vacio` que ya
  usan las 13 pantallas Atlas, sin cambios.

### Variante C (= Dirección C)
Estructura similar a B (tarjetas por zona) pero con controles/tipografía
a mayor escala y más separación vertical entre tarjetas; en tablet, las
tarjetas Cliente/Descuento se apilan por defecto (nunca 2 columnas,
incluso en tablet, priorizando objetivos táctiles amplios sobre
densidad horizontal).
- **Búsqueda**: campo de mayor altura (objetivo táctil ampliado).
- **Resultados**: fila alta, botón "Agregar" grande y claramente
  separado del resto de la fila.
- **Identificación**: igual contenido que A/B, tipografía ligeramente
  mayor.
- **Carrito**: filas más altas que A, botón "Quitar" con área de toque
  ampliada.
- **Cliente/Descuento**: apiladas siempre (nunca 2 columnas).
- **Totales**: bloque grande, con el mismo contenido que A/B.
- **Checkout**: filas de pago con mayor separación vertical entre
  método y monto.
- **Errores/vacío**: mismo contenido, con iconografía SVG a mayor
  tamaño (consistente con la escala general de la dirección).

Ninguna variante agrega un campo, botón, columna o acción que no exista
en el código real hoy.

---

## 9. Búsqueda de productos

Las tres direcciones comparten el mismo dato real disponible: nombre,
SKU, precio, unidad (identificador truncado si es SERIALIZED),
cantidad a agregar, descuento de línea. **El stock disponible NO se
muestra en ningún template hoy** (confirmado en Etapa 1 — ausencia
real, no un olvido de este Lab) — ninguna de las tres direcciones lo
representa como si existiera; se documenta como propuesta futura
separada, no incorporada aquí (`docs/pos-redesign-design-system.md`
§18 de riesgos, coherente con §19.3 de risk-map).

Jerarquía visual propuesta (las tres direcciones): nombre del producto
como elemento principal, SKU como texto secundario tenue, precio
alineado a la derecha con `.u-cifra`, badge de identificación
(IMEI/serie) solo cuando el producto es SERIALIZED.

Selección: el flujo real (campo `unit_identifier` cuando la búsqueda no
resuelve una unidad exacta) se mantiene idéntico en las tres
direcciones — solo cambia la presentación del campo (ver §16).

---

## 10. Carrito

Explorado en las tres direcciones (detalle completo en §8). Resumen
común: Producto (+ SKU + IMEI/serie truncado si aplica) → Cantidad →
Precio → Descuento → Impuesto → Total de línea → Quitar. Ninguna
dirección agrega edición de cantidad/precio en línea — el único control
por línea sigue siendo "Quitar", igual que el código real.

> **FUTURA DECISIÓN UX/FUNCIONAL** — un control de edición de línea
> (`Quantity Control`, clasificado **B** en
> `docs/pos-redesign-design-system.md` §7.8) puede mencionarse como
> dirección conceptual futura en cualquiera de las tres propuestas,
> pero **no se diseña como si ya existiera** — no aparece en ninguna
> maqueta de este Lab como control funcional.

**Densidad por dirección**: A = muy compacta (`--espacio-1`/`2`); B =
estándar Atlas (`--espacio-3`); C = ampliada (`--espacio-3`/`4`, filas
más altas).

**Estado vacío**: mismo mensaje real, ícono SVG en las tres (corrige el
emoji actual, ya definido como corrección de conformidad en
`docs/pos-redesign-design-system.md` §7.17, no una especialización por
dirección).

---

## 11. Cliente

Mismo contenido real en las tres direcciones: cliente actual
(`display_name` o "Consumidor final"), `<select>` para cambiarlo. El
campo "Buscar cliente" (hoy vestigial, sin efecto —
`docs/pos-redesign-discovery.md` §15) **no se presenta como
funcional** en ninguna dirección — permanece marcado como
`docs/pos-redesign-design-system.md` §7.9, decisión **D**.

No se agregan: creación inline de cliente, historial de compras,
límite de crédito visible en el terminal (`credit_enabled`/
`credit_limit` sí existen en `Customer`, pero el terminal no los
muestra hoy — solo se usan internamente para decidir si una venta a
crédito es válida; mostrarlos sería una superficie de información
nueva, no solo un rediseño, y no se incluye).

---

## 12. Descuento

Mismo mecanismo real en las tres direcciones (línea y global, vía
`apps.approvals`). Se distingue explícitamente:

- **UI de descuento**: campos `discount_percent`/`discount_amount`,
  presentados con distinto nivel de prominencia según la dirección (A:
  colapsado por defecto para no competir visualmente con el checkout;
  B: tarjeta propia igual que hoy; C: campos de mayor tamaño dentro de
  su tarjeta).
- **Mecanismo funcional de autorización** (`apps.approvals`,
  `ApprovalRequest`): **sin cambios en ninguna dirección** — el bloque
  de "autorizaciones aprobadas pendientes de consumir" se presenta
  igual en las tres (reutilizando `.alerta--advertencia`/`.alerta--exito`
  ya definidos en `docs/pos-redesign-design-system.md` §21), sin tocar
  la lógica que lo genera.

---

## 13. Totales

El área más importante del Lab, junto con el Carrito y el Checkout.

Contenido real, sin cambios: Subtotal, Descuento, Impuesto, **TOTAL**,
Moneda (`sale.currency`, sin selector — la doctrina de multi-moneda no
está implementada).

**Jerarquía por dirección** (las tres elevan el Total por encima de
Subtotal/Descuento/Impuesto, coherente con `docs/pos-redesign-design-system.md`
§12, difieren en el tratamiento):
- **A**: Total en bloque fijo aparte, `--texto-3xl`, color
  `--pos-color-primario`, sin tarjeta contenedora (borde superior
  simple que lo separa del resto).
- **B**: Total dentro de la misma tarjeta `.kpi-grid` que los otros 3,
  pero con `--texto-3xl` vs. `--texto-lg` del resto — mismo contenedor,
  jerarquía tipográfica distinta.
- **C**: Total en bloque propio como A, pero con aún más espacio
  vertical alrededor y color `--pos-color-exito` cuando el pago
  ingresado ya cubre el total (dato ya calculable server-side en el
  render inicial del checkout, sin JS).

Ningún total nuevo se introduce en ninguna dirección.

---

## 14. Checkout

Mismo flujo real en las tres direcciones: total a pagar
(`sale.total`), métodos de pago reales (`cash`/`card`/`transfer`/
`other`), formset de 2 filas, total ingresado (suma de los montos del
formset, calculable en el render), validaciones reales
(`InsufficientPaymentError`, mensaje "el cambio solo puede entregarse
en efectivo"), estado de pago (`Sale.PaymentStatus`).

> **DECISIÓN FUNCIONAL PENDIENTE** — el cambio/vuelto se calcula hoy en
> `CheckoutView.post` (variables locales `total_recibido`/`exceso`/
> `cambio`) y solo se comunica por mensaje flash tras confirmar; no se
> persiste en `Payment` ni aparece en el recibo. **No se resuelve en
> este Lab.** Las tres direcciones reservan un espacio visual (un
> bloque "Cambio a entregar" bajo el formset de pago) que hoy
> permanecería vacío hasta el submit, mostrando el valor solo después
> de la confirmación real (mismo comportamiento actual, solo mejor
> ubicado visualmente) — ninguna dirección simula un cálculo en vivo
> antes del submit, porque eso requeriría JavaScript nuevo no
> autorizado (`docs/pos-redesign-design-system.md` §24).

**Pagos múltiples**: sí existen realmente (2 filas por defecto,
`extra=2` en el formset) — las tres direcciones lo representan tal
cual, sin agregar un botón de "agregar fila" (no existe en el código
hoy; agregarlo sería una decisión funcional/JS nueva, marcada aparte si
se propusiera, no incluida en ninguna de las tres direcciones de este
Lab).

---

## 15. Pago

Los 4 métodos reales, sin ninguno inventado:

| Método | Cómo se presenta (A/B/C) |
|---|---|
| `cash` (Efectivo) | Mismo `<select>`, ícono de billete opcional (SVG ya del set Atlas) |
| `card` (Tarjeta) | Mismo `<select>`, ícono de tarjeta opcional |
| `transfer` (Transferencia) | Mismo `<select>`, ícono de transferencia opcional |
| `other` (Otro) | Mismo `<select>`, sin ícono especial (placeholder genérico, confirmado en Etapa 1 como acoplamiento futuro a FASE 16/PayPal, fuera de alcance) |

**Payment Row**: método + importe en la misma fila, `flex-wrap: wrap`
en las tres direcciones (corrige el defecto real de Etapa 1, ver §19).
**Total pagado**: suma visual de los montos capturados. **Diferencia**:
ver §14 (decisión pendiente). **Errores**: mismos mensajes reales,
`.alerta--peligro`. **Confirmación**: botón "Confirmar y cobrar", sin
`confirm()` nativo en ninguna dirección (igual que hoy — solo
"Cancelar carrito" lo tiene; agregar uno a Confirmar sería un cambio
menor de UX, no incluido a menos que se decida explícitamente en una
etapa posterior).

---

## 16. IMEI / Serial

Mismo flujo real en las tres direcciones — sin escaneo automático
inventado, sin lector físico inventado, sin nuevos estados de
`InventoryUnit`.

- **Identificación**: badge "Requiere IMEI/serie" cuando el producto es
  SERIALIZED y la búsqueda no resolvió una unidad exacta.
- **Entrada**: campo de texto `unit_identifier`, con `<label>` real
  "IMEI o número de serie" (corrección de accesibilidad ya definida en
  Etapa 2, aplicada en las tres direcciones).
- **Selección**: cuando la búsqueda por IMEI/serie exacto ya resolvió
  la unidad, se muestra directamente (identificador truncado) sin pedir
  entrada manual — igual que hoy.
- **Asociación con línea**: badge secundario en la fila del carrito.
- **Validación/error**: mismo mensaje real "No se encontró ninguna
  unidad con ese IMEI/serie."
- **Confirmación**: la unidad pasa a `VENDIDO` solo al confirmar la
  venta (`confirm_sale`) — sin cambios, sin validación anticipada al
  agregar (esa validación sigue siendo la decisión funcional pendiente
  de mayor severidad, `docs/pos-redesign-risk-map.md` §3, **no
  resuelta aquí**).

Diferencia entre direcciones: solo tamaño/densidad del campo (A:
compacto e inline; B: campo estándar dentro de la fila de resultado; C:
campo de mayor altura, con el botón "Agregar" claramente separado para
evitar toques accidentales antes de verificar el IMEI).

---

## 17. Caja

Mismas 5 superficies reales (`Register List`, `Session Open`, `Session
Close`, `Session Summary`, `Cash Movement` — este último sin punto de
entrada en la UI hoy, ver `docs/pos-redesign-risk-map.md` §5).

**Caja activa/inactiva**: badge `--pos-color-exito`/neutro sobre
`CashRegister.status` real, igual en las tres direcciones (solo cambia
tamaño/densidad de la tarjeta contenedora).

**Sesión abierta/cerrada**: banner en el header POS (§7), reutilizando
el mismo patrón en las tres direcciones.

**Movimientos**: tabla real (Tipo/Monto/Motivo/Usuario/Fecha) — A la
presenta compacta, B estándar, C con filas más altas.

**Esperado/contado/diferencia**: 3 valores reales
(`expected_cash`/`counted_cash`/`difference`) con `.u-cifra`, diferencia
con color condicional (positivo `--pos-color-exito`, negativo
`--pos-color-peligro`) — mismo tratamiento en las tres direcciones,
coherente con `docs/pos-redesign-design-system.md` §15.

**Cash Movement UI**: las tres direcciones incluyen un punto de entrada
visual hacia el formulario ya existente (botón/enlace desde
`terminal.html` o `session_close.html`) — clasificado **A, con
confirmación previa requerida** en Etapa 2 (§7.22); este Lab lo maqueta
pero no lo implementa, y reitera que requiere esa confirmación explícita
antes de construirse.

Ningún cálculo de caja se modifica; ninguna acción nueva se agrega
(sin conteo por denominaciones — fuera de alcance completo, decisión
**D** de `docs/pos-redesign-risk-map.md` §4).

---

## 18. Receipt

Mismos datos reales en las tres direcciones (tenant, número, cliente,
fecha, vendedor, líneas con SKU/IMEI-serie, cantidad, precio,
descuento, impuesto, total, pagos, notas) — ver
`docs/pos-redesign-design-system.md` §16 para el detalle completo, sin
repetirlo aquí.

Confirmado de nuevo: `HTML` + `window.print()`, **sin backend PDF**,
**sin PDF implementado en este Lab**, **sin nueva dependencia**.

La impresión térmica 58/80mm aparece en las tres direcciones únicamente
como nota de posible especialización futura junto al botón de imprimir
("Optimizado para impresión térmica — próximamente", si acaso, como
texto de marcador de posición) — nunca como una opción funcional real.

> **PROPUESTA FUTURA / DECISIÓN FUNCIONAL** — impresión térmica,
> clasificación **D** (`docs/pos-redesign-design-system.md` §18 y
> §26.10). No implementada, no maquetada como funcional.

Diferencia entre direcciones: solo densidad tipográfica del documento
(A/C más compactas y con mayor tamaño de fuente respectivamente para
lectura rápida de mostrador; B mantiene el tratamiento actual de hoja
carta/A4 sin cambios de escala).

---

## 19. Responsive Lab

Las tres direcciones deben resolver los mismos dos riesgos reales ya
descubiertos en Etapa 1 y reafirmados en Etapa 2:

```css
/* terminal.html:125 — no colapsa hoy */
display:grid;
grid-template-columns: 1fr 1fr;
```
y filas de pago con `display:flex` sin `flex-wrap`.

**No se corrigen en este Lab** (el fix — aplicar `.u-grid-2col`, ya
existente en `design-system-erp.css`, y agregar `flex-wrap: wrap` — ya
está documentado y probado desde FASE 5; implementarlo pertenece a una
etapa de implementación posterior, no a este Lab de exploración).

Cómo resuelve cada dirección estos dos puntos **conceptualmente**:

| Superficie | Dirección A | Dirección B | Dirección C |
|---|---|---|---|
| Grid Cliente/Descuento | Franja horizontal que ya no es un grid de 2 columnas fijo — se apila naturalmente por ser una franja delgada, sin depender de `.u-grid-2col` | Usa `.u-grid-2col` tal cual (2 columnas en escritorio, 1 en móvil) — mismo patrón que `customer_collections.html` | Apilado siempre, incluso en tablet — nunca 2 columnas, prioriza objetivo táctil sobre densidad horizontal |
| Filas de pago | `flex-wrap: wrap`, campos de ancho mínimo definido para no comprimirse en exceso | `flex-wrap: wrap`, mismo ancho que Atlas estándar | `flex-wrap: wrap` + mayor `gap`, cada fila prácticamente ocupa su propia línea en móvil |
| Carrito | Scroll vertical dentro de un contenedor de altura fija (mantiene checkout visible sin scroll) | Scroll de página normal (igual que hoy) | Scroll de página normal, con filas más altas — mayor scroll total pero cada fila más legible al tacto |
| Total | Fijo/sticky en la parte inferior en móvil (siempre visible) | Sigue el flujo normal de la página (como hoy) | Fijo/sticky en la parte inferior en móvil, igual que A |
| Checkout | Franja fija inferior en escritorio y móvil | Tarjeta al final del flujo, igual que hoy | Tarjeta al final, con botón de cobro de ancho completo en cualquier viewport |
| Botones | Tamaño estándar Atlas | Tamaño estándar Atlas | Tamaño ampliado en todo viewport, no solo en móvil |
| Scroll | Minimizado por diseño (contenedores de altura fija) | Igual que hoy (scroll de página completo) | Mayor que A, menor que si no se optimizara — balance entre legibilidad y longitud de página |
| Touch targets | Estándar Atlas (~36-40px) | Estándar Atlas | Ampliados (48-56px) en todo viewport |

**Desktop/Laptop/Tablet/Mobile**: las tres direcciones se probarían
conceptualmente en los 4 anchos de referencia ya usados por el proyecto
(`--punto-movil: 640px`, `--punto-tablet: 768px`, `--punto-laptop:
1024px`, `--punto-escritorio: 1280px`, de `base.css`) — ningún
breakpoint nuevo se introduce, se reutilizan los ya definidos.

---

## 20. Teclado y touch

**Teclado** (las tres direcciones comparten el mismo criterio, difieren
solo en densidad de campos por pantalla, lo que afecta cuántos
`Tab` se requieren):
- Foco visible heredado de `base.css` (`:focus-visible`), sin cambios.
- Orden de tabulación sigue el flujo real de §4.
- `autofocus` en el campo de búsqueda (atributo HTML declarativo, sin
  JS) — candidato en las tres direcciones.
- Confirmación de checkout vía `Enter` en el último campo de pago
  (comportamiento nativo de un `<form>` HTML, sin JS nuevo) — ya
  disponible hoy por defecto del navegador, no requiere ninguna
  implementación.

**Touch**:
- Separación mínima entre controles de alta frecuencia para prevenir
  pulsaciones accidentales — más generosa en C, estándar en A/B.
- Botones "Quitar"/"Agregar" nunca adyacentes sin espacio entre ellos
  en ninguna dirección.

**Shortcuts**: ninguna dirección propone un atajo de teclado nuevo (ej.
`F2` para buscar, `F9` para cobrar) porque no existe hoy en el código.

> Si una futura etapa quisiera introducir shortcuts, quedaría marcado
> como **DECISIÓN FUNCIONAL PENDIENTE** — no incluido en ninguna de las
> tres direcciones de este Lab.

---

## 21. Accesibilidad

Comparación de las tres direcciones respecto a los criterios ya fijados
en `docs/pos-redesign-design-system.md` §20 (sin modificarlos, solo
comparar cómo los cumple cada dirección):

| Criterio | Dirección A | Dirección B | Dirección C |
|---|---|---|---|
| Contraste | Igual (mismos tokens Atlas en las tres) | Igual | Igual |
| Focus visible | Heredado, sin cambios | Heredado, sin cambios | Heredado, sin cambios |
| Labels | `_campo.html` en las tres (corrige la fila de alta rápida sin label, hoy real) | Igual | Igual |
| Mensajes de error | Mismo mecanismo, presentación algo más compacta | Mismo mecanismo, igual que hoy | Mismo mecanismo, con mayor espacio de lectura |
| ARIA | Heredado sin cambios (breadcrumb sigue ausente en Terminal en las tres) | Heredado sin cambios | Heredado sin cambios |
| Navegación por teclado | Más rápida por menor cantidad de contenedores intermedios | Estándar | Ligeramente más larga por mayor espaciado, sin afectar el orden lógico |
| Touch targets | Estándar Atlas (no ampliado) | Estándar Atlas | Ampliado — mejor cumplimiento del criterio WCAG 2.5.5 |
| Estados | Color + texto (nunca solo color), igual en las tres | Igual | Igual |
| Lectura de números | `.u-cifra` en las tres | Igual | Igual |
| Iconos SVG | Reemplaza emoji en las tres (corrección ya definida, no una diferencia entre direcciones) | Igual | Igual — a mayor tamaño, consistente con la escala general |
| Ausencia de emoji como iconografía principal | Cumplida en las tres | Cumplida | Cumplida |

No se modifica nada en esta etapa — es una comparación de cómo se
comportaría cada dirección si se implementara.

---

## 22. Estados

Únicamente estados reales de Etapa 1
(`docs/pos-redesign-discovery.md` §11), sin inventar ninguno. Las tres
direcciones comparten el mismo mapeo visual definido en
`docs/pos-redesign-design-system.md` §21 (estado de negocio → badge/
alerta), solo difiere el tamaño/densidad del contenedor:

- **Empty** (carrito/resultados vacíos) → `.estado-vacio` + ícono SVG.
- **Loading**: **no existe hoy** (confirmado — el POS no tiene
  indicador de carga, todo es recarga completa de página); ninguna
  dirección lo inventa. Se documenta como ausencia real, no como un
  estado a diseñar.
- **Error** → `.alerta--peligro`.
- **Success** → `.alerta--exito`/toast.
- **Warning** → `.alerta--advertencia`.
- **Pending approval** (`ApprovalRequest.PENDING`) → `.alerta--advertencia`.
- **Restricted/not available**: ver §23 — presentación visual
  únicamente, condicionada a que la verificación real exista.

---

## 23. Permisos

**No se resuelve la brecha real aquí** (`pos.use`, `cash.view`,
`sales.*`, `payments.*`, `credit.*` definidos pero no aplicados —
`docs/pos-redesign-risk-map.md` §1-2). Las tres direcciones exploran
únicamente cómo **se vería** cada estado, condicionado a que la
verificación exista en el futuro:

- **Disponible**: control en su estado normal.
- **Restringido/no disponible**: control oculto o `disabled` +
  tooltip — mismo patrón ya usado en otros módulos del ERP para
  restricciones por rol (ej. campos sensibles de RRHH).
- **Pendiente de aprobación**: bloque `.alerta--advertencia`, igual
  que §12/§22.

**Se distingue explícitamente**: presentación visual (lo que este Lab
explora) vs. autorización real (lo que sigue sin existir en el código
para la mayoría de estas acciones). Ningún decorator, mixin,
middleware o `require_permission` se agrega, modifica o simula en este
documento ni en ningún archivo del repositorio.

---

## 24. Arquitectura CSS/JS

No implementada — solo explorada conceptualmente, extendiendo
`docs/pos-redesign-design-system.md` §23-24:

```
.shell--erp                  (Atlas, ya existente — heredado sin cambios)
    ↓ (convivencia, no reemplazo)
.shell--pos                  (nuevo, aditivo — tokens de densidad/escala táctil, NO redeclara :root)
    ↓
.pos-*                       (namespace de clases nuevas: .pos-carrito, .pos-total, .pos-fila-pago, etc.)
```

**Qué reutilizaría `design-system-erp.css`**: todo lo ya resuelto
pasivamente hoy (color primario, tipografía, radios, sombras, spacing)
— `.shell--pos` no redeclara ningún token ya definido por `.shell--erp`.

**Qué sería POS-específico**: densidad de fila de carrito, escala de
objetivo táctil (variable por dirección — A/B usan la escala estándar
de Atlas, C define una escala ampliada propia bajo `.shell--pos`),
prominencia tipográfica del Total, `flex-wrap`/`.u-grid-2col` aplicados
al terminal.

**Qué nunca debe tocar `base.css`**: ningún token raíz compartido —
confirmado como regla dura, igual que en FASE 5.

**Qué nunca debe tocar `.shell--saas`**: cero reglas nuevas bajo ese
selector, en ninguna de las tres direcciones.

**Qué debe evitar colisión con `.shell--erp`**: todo nombre de clase
nuevo lleva el prefijo `.pos-`, nunca reutiliza un nombre ya existente
en `design-system.css`/`design-system-erp.css` sin ese prefijo — mismo
criterio de Etapa 2 §23, reafirmado.

**No se crea ningún archivo CSS ni JS en esta etapa.**

---

## 25. Matriz de componentes

Los 24 componentes de Etapa 2, con las tres propuestas de este Lab.
"Atlas" = qué reutiliza; "POS especialización" = qué cambia respecto a
Atlas puro (de `docs/pos-redesign-design-system.md` §7); "Funcionalidad
nueva" = **Ninguna** salvo donde se indique explícitamente (y en ese
caso, siempre marcada como decisión pendiente, nunca implementada).

| Componente | Atlas | POS especialización | Propuesta A | Propuesta B | Propuesta C | Funcionalidad nueva |
|---|---|---|---|---|---|---|
| POS Shell | Sidebar/topbar completos | Ninguna (heredado 100%) | Igual | Igual | Igual | Ninguna |
| POS Header | — (no existe hoy) | Nuevo bloque visual sobre datos ya reales | Compacto, integrado en la franja superior | Tarjeta separada, estilo Atlas | Bloque grande, alta visibilidad | Ninguna |
| Product Search | `.campo` | Tamaño de campo | Ancho completo, `autofocus` | Estándar dentro de tarjeta | Campo alto, táctil | Ninguna |
| Product Result | `.tabla` | Densidad de fila | Muy compacta | Estándar | Alta, botón separado | Ninguna |
| Product Identification | Badge/texto secundario | Ninguna | Igual | Igual | Igual, mayor tamaño | Ninguna |
| Cart | `.tabla` | Densidad | Muy densa | Estándar | Amplia | Ninguna |
| Cart Line | Fila + `.btn--sm` | Objetivo táctil del botón "Quitar" | Estándar | Estándar | Ampliado | Ninguna |
| Quantity Control | — (no existe) | N/A | No incluido como funcional | No incluido como funcional | No incluido como funcional | **Marcada — decisión B, no implementada** |
| Customer Selector | `.campo` | Ninguna en el `<select>`; buscador vestigial sin tratamiento funcional | Línea + enlace "Cambiar" | Tarjeta estándar | Tarjeta amplia | Ninguna |
| Discount Section | `.campo`/`.alerta` | Prominencia | Colapsado por defecto | Tarjeta estándar | Tarjeta amplia | Ninguna |
| Totals | `.kpi-grid` | Jerarquía del Total | Bloque fijo aparte | Dentro de la misma tarjeta, tamaño mayor | Bloque grande con más aire | Ninguna |
| Payment Form | `.campo` en formset | `flex-wrap` | Compacto | Estándar | Amplio | Ninguna |
| Payment Row | Fila flex | `flex-wrap`, ancho mínimo | Compacta | Estándar | Amplia | Ninguna |
| Checkout Summary | — (no existe como bloque) | Resumen estático de Total a pagar | Incluido, estático | Incluido, estático | Incluido, estático | **Cálculo en vivo marcado — decisión C, no incluido** |
| Cash Status | `.badge`/`.alerta` | Ninguna | Igual | Igual | Igual | Ninguna |
| Approval Notice | `.alerta` | Ninguna | Igual | Igual | Igual | Ninguna |
| Empty State | `.estado-vacio` | Corrección emoji→SVG | Igual | Igual | Igual, ícono mayor | Ninguna |
| Error State | `.alerta--peligro`/toast | Posición junto a checkout | Igual | Igual | Igual | Ninguna |
| Success Feedback | `.alerta--exito`/toast | Ninguna | Igual | Igual | Igual | Ninguna |
| Serial/IMEI input | `.campo`/`.badge` | Label real, tamaño | Compacto inline | Estándar en fila | Alto, separado | Ninguna |
| Cash Session UI | `.tarjeta`/`.campo` | Ninguna | Igual | Igual | Igual | Ninguna |
| Cash Movement UI | — (backend sin UI) | Punto de entrada visual nuevo | Enlace discreto | Botón en tarjeta | Botón grande | **Exposición marcada — A con confirmación previa requerida** |
| Closing Summary | `.tabla`/`.kpi` | Ninguna | Igual | Igual | Igual | Ninguna |
| Receipt/Print Layout | Documento HTML propio | Densidad tipográfica | Compacta | Sin cambios (actual) | Amplia | Térmica marcada — **decisión D, no incluida** |

---

## 26. Decisiones funcionales pendientes

Consolidado de `docs/pos-redesign-risk-map.md` y
`docs/pos-redesign-design-system.md` §26, separado por categoría, sin
resolver ninguna.

### UX pendiente
- **Edición de línea del carrito** (Quantity Control) — problema: solo
  se puede quitar una línea, no editarla; realidad actual: confirmado
  ausente en `add_item_to_cart`/`add_sale_item`; impacto: el cajero
  debe quitar y re-agregar ante cualquier corrección; por qué no se
  decide aquí: requeriría confirmar si el backend soporta editar una
  línea `DRAFT` ya agregada, cambio de servicio, no solo de vista.
- **Checkout Summary con cálculo en vivo** — problema: el cajero no ve
  el cambio antes de confirmar; realidad actual: el cálculo vive
  server-side, sin JS; impacto: menor velocidad de verificación antes
  de cobrar; por qué no se decide aquí: requiere JavaScript nuevo, hoy
  inexistente en el POS.

### Funcional pendiente
- **Validación de disponibilidad de stock/unidad al agregar** —
  problema: el error solo aparece al cobrar; realidad actual:
  `ensure_unit_available_for_sale` existe pero desconectada; impacto:
  riesgo de doble venta de unidad serializada, carritos armados en
  vano; por qué no se decide aquí: cambia el momento de un error de
  negocio real, requiere decisión de producto.
- **Devolución de mercancía accesible desde el POS** — problema: hoy
  solo existe en `apps.sales`, sin enlace desde el terminal; realidad
  actual: `pos:cancel_cart` solo cancela `DRAFT`; impacto: navegación
  fragmentada para el cajero; por qué no se decide aquí: podría
  resolverse con solo un enlace (bajo riesgo) o con lógica nueva (alto
  riesgo) — la elección requiere decisión de producto.
- **Integración de `TaxCode`/`SaleItemTax` al POS** — problema: el POS
  solo usa el impuesto plano del producto; realidad actual: el sistema
  multi-código ya existe en `apps.accounting` pero desconectado;
  impacto: tenants con impuestos múltiples no pueden usarlos desde el
  POS; por qué no se decide aquí: conecta dos sistemas de impuestos,
  requiere definir la regla de interacción entre ambos.
- **Persistencia de `amount_received`/`change_amount`** — ver §14;
  impacto: el comprobante no documenta cuánto entregó/recibió el
  cliente; por qué no se decide aquí: requiere migración de `Payment`,
  modelo compartido con Cobros/CxC.

### Seguridad/permisos pendiente
- **Brecha de autorización real** (`pos.use`, `cash.view`, todo
  `apps/sales/views.py`) — problema: catálogo definido, no aplicado;
  realidad actual: solo `cash.open`/`close`/`move` verificados; impacto:
  cualquier usuario con membresía activa puede operar el POS/anular
  ventas sin importar su rol; por qué no se decide aquí: es la decisión
  de mayor severidad de todo el discovery, requiere confirmación
  explícita antes de tocar `apps/pos/views.py`/`apps/sales/views.py`.
- **`cash.view` no aplicado en `CashSessionSummaryView`** — problema:
  exposición de datos de sesión de caja de otros cajeros; realidad
  actual: sin `require_permission`; impacto: bajo-medio, dato interno
  del tenant, no cruza tenants; por qué no se decide aquí: cambio
  acotado pero agrupado con la decisión anterior por coherencia.

### Impresión pendiente
- **Impresión térmica 58/80mm** — problema: el recibo actual está
  pensado para hoja carta/A4; realidad actual: sin ningún CSS/vista
  alternativa; impacto: bajo hasta que un tenant use impresora
  térmica real; por qué no se decide aquí: requiere decidir si se
  detecta por CSS o por una vista/ruta alternativa explícita (esto
  último ya sería funcional, no solo visual).

### Arquitectura pendiente
- **Convivencia `.shell--erp` + `.shell--pos` vs. reemplazo** —
  problema: no confirmado si ambas clases coexisten en la misma página
  o si `.shell--pos` reemplaza el tratamiento de `.shell--erp` dentro
  del área de contenido del terminal; realidad actual: el POS ya
  hereda `.shell--erp` pasivamente hoy; impacto: determina cómo se
  estructura el primer CSS productivo de una futura etapa de
  implementación; por qué no se decide aquí: es una pregunta de
  arquitectura que Etapa 2 ya dejó abierta explícitamente para
  resolverse al iniciar una etapa de implementación, no de exploración.

---

## 27. Recomendación para la siguiente fase

Este Lab no elige una dirección final — corresponde al usuario decidir,
con la información de §6 y §25 como base. Se requiere aprobación
humana explícita para:

1. **Dirección visual** — A (Operativo Compacto), B (Balanceado Atlas)
   o C (Táctil/Híbrido), o una combinación específica entre ellas.
2. **Composición de Terminal** — cuál de las tres variantes de §8 (o
   una síntesis) se lleva a una futura etapa de implementación.
3. **Nivel de densidad** — el rango entre "muy compacto" (A) y
   "amplio/táctil" (C) que mejor corresponde al contexto real de uso
   del negocio (mostrador con mouse/teclado vs. tablet táctil).
4. **Nivel de especialización POS** — cuánto debe diferenciarse
   `.shell--pos` de `.shell--erp` (mínimo, como en B, o notable, como
   en A/C).
5. **Tratamiento responsive** — confirmar el enfoque de §19 antes de
   que una etapa de implementación aplique el fix real de
   `.u-grid-2col`/`flex-wrap`.
6. **Decisiones funcionales pendientes** — cuáles de las 10 de §26 se
   autorizan a resolverse antes, durante o después de la
   implementación visual del POS — empezando, si se decide avanzar, por
   la brecha de autorización de seguridad (mayor severidad de todo el
   discovery).

La siguiente etapa **no debe comenzar automáticamente**.

---

## Confirmación de reglas absolutas respetadas

Durante esta etapa: cero modificaciones a modelos, views, forms,
services, URLs, migraciones, permisos, lógica de negocio, CSS
productivo, JS productivo o templates productivos. Ningún prototipo
aislado fue necesario — toda la exploración de este Lab es documental
(este archivo), sin artifacts ni archivos de código adicionales.
