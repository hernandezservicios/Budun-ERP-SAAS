# ERP DESIGN SYSTEM SPEC — Atlas (FASE 2)

Lenguaje visual nuevo y exclusivo del ERP de Budun. No es una modernización del
sistema actual (`docs/design-system.md`, FASE 5) ni una reutilización del Design
System del Super Admin SaaS (`docs/design-system-v1-hybrid.md`, FASE 7) — es un
tercer sistema, deliberadamente aislado de ambos, diseñado desde cero a partir
del inventario funcional real del `docs/erp-redesign-map.md`.

**Estado**: solo diseño. Ningún archivo del ERP productivo (`templates/`,
`static/`, `apps/*/views.py`, `apps/*/forms.py`, modelos, URLs) fue modificado
para producir este documento ni la referencia visual que lo acompaña. La
implementación real ocurre en una fase posterior (FASE 5), pantalla por
pantalla, con la misma disciplina de "auditar → comparar contra este spec →
cambiar solo lo necesario" ya usada en el rediseño del Super Admin SaaS.

**Referencia visual**: [Atlas — ERP Design System Lab](https://claude.ai/artifact/2qw25JkKX3wgHNpuDnbSJT), un Artifact publicado con el tipo "Design System" — 17 componentes reales con vista previa en vivo, tokens completos en modo Día y Noche, y el brand book (`README.md`) con reglas de uso. No es productivo: es la herramienta de validación antes de tocar el ERP real, tal como pidió el usuario en la sección 13 de FASE 2.

## Regla de aislamiento frente al SaaS Super Admin

El SaaS Super Admin ya está aprobado y **no se toca**. `base.css`,
`design-system.css` y `ui.js` son archivos compartidos hoy por ambas
superficies — un riesgo identificado explícitamente en el Discovery
(`docs/erp-redesign-map.md`, sección 17, riesgo 1). Atlas resuelve esto
definiendo su propio juego de tokens, con nombres, valores y convenciones que
**nunca coinciden a propósito** con los de Hybrid (`--accent`/`#2A4CD6`/sidebar
oscuro/Public Sans+JetBrains Mono/radios 6-9-12). La decisión de implementación
para FASE 5 (aún no ejecutada, se documenta aquí para que se revise antes de
empezar) es: un archivo nuevo `static/css/design-system-erp.css` cargado solo
por `layout_app.html` bajo un scope `.shell--erp`, replicando exactamente el
patrón ya usado por `.shell--saas` — nunca redefinir los tokens `:root`
compartidos. Si en la implementación real surge la necesidad de tocar un
archivo compartido, se documenta primero y se verifica que el SaaS no cambie
visualmente, tal como exige la instrucción de esta fase.

---

## 1. Dirección visual

Atlas es un sistema **denso, sobrio y orientado a datos** — la antítesis de una
interfaz de marketing. Su trabajo diario real, según el Discovery, es mostrar
tablas largas, formularios financieros y estados de negocio con precisión, no
impresionar. Tres decisiones de identidad lo distinguen deliberadamente de
Hybrid (SaaS) y del ERP actual:

1. **Sidebar claro, no oscuro.** Hybrid usa un riel casi negro (`#101216`)
   como firma visual. Atlas usa un riel blanco (`sidebar-bg`) sobre un lienzo
   gris-azulado (`surface-page`) — el objeto de navegación se distingue por
   estar más claro que el contenido, no más oscuro. Decisión consciente de
   identidad, no una omisión.
2. **Una sola familia tipográfica de interfaz (IBM Plex Sans) + una familia de
   datos dedicada (IBM Plex Mono)** — distinta de Public Sans/JetBrains Mono
   del SaaS. IBM Plex fue diseñada explícitamente para software técnico y
   empresarial, coherente con el uso real del ERP (formularios largos,
   tablas financieras, POS).
3. **Radios más ajustados (4/6/10px vs. 6/9/12px de Hybrid)** y solo dos
   niveles de sombra — un sistema que se apoya en bordes y jerarquía
   tipográfica antes que en decoración, apropiado para pantallas que el
   usuario mira ocho horas al día.

No se copia el ERP actual (emoji en estados vacíos, sin fuente tabular, sidebar
plano sin agrupar) ni el SaaS (sidebar oscuro, acento azul distinto). Azul y
verde siguen siendo la identidad (mandato de `CLAUDE.md`): el azul es
`primary`, el verde es exclusivamente semántico (`success`) — nunca decorativo.

## 2. Tipografía

| Familia | Uso | Por qué |
|---|---|---|
| **IBM Plex Sans** (400/500/600/700) | Toda la interfaz: encabezados, cuerpo, etiquetas, botones | Diseñada para software técnico/empresarial; excelente legibilidad en tamaños pequeños y alta densidad — el caso de uso real del ERP |
| **IBM Plex Mono** (400/500/600) | Exclusivamente cifras que deban alinearse en columna: montos, cantidades, saldos, IDs, IMEI/serie enmascarado | Continúa la convención ya validada en el proyecto (una fuente de datos dedicada, como `.u-cifra` en el SaaS) con una familia propia, no la misma de Hybrid |

Escala (grupos y estilos, ver `tokens.json` del Lab para los valores exactos):
**Encabezados** (h1 22/28, h2 18/24, h3 16/22, h4 14/20, todos 600) ·
**Cuerpo** (body-lg 15/22, body 14/20, body-sm 13/18, todos 400; label 13/18
600; eyebrow 11/14 600 mayúscula+tracking, reservada solo a encabezados de
columna de tabla y etiquetas de grupo de navegación) · **Datos** (figure-lg
22/26 600 — valor de KPI; figure 14/20 500 — celda financiera; figure-sm 12/16
500; code 13/18 400 — SKU/documento/ID).

## 3. Color

Dos temas: **Día** (operación estándar, por defecto) y **Noche** (mostrador/POS
con poca luz — un caso de uso real del POS que hoy no tiene ninguna
adaptación, según el Discovery). Categorías pedidas por el usuario, con sus
valores en modo Día (ver el Lab para Noche):

| Categoría | Token(s) | Día |
|---|---|---|
| Background principal | `surface-page` | `#F5F6F8` |
| Surface | `surface` | `#FFFFFF` |
| Surface elevada | `surface-raised` | `#FFFFFF` + `shadow-md` |
| Border | `border` / `border-strong` | `#D7DCE3` / `#B7C0CC` |
| Text principal | `text` | `#111827` |
| Text secundario | `text-secondary` | `#3F4A5A` |
| Text muted | `text-muted` | `#5D6773` |
| Primary | `primary` / `primary-strong` / `primary-soft` | `#1D4E89` / `#123761` / `#E4ECF6` |
| Success | `success` / `success-soft` | `#0F7A5C` / `#DFF3EC` |
| Warning | `warning` / `warning-soft` | `#8F5A0B` / `#FBEFDC` |
| Danger | `danger` / `danger-soft` | `#B3311F` / `#F9E4E0` |
| Info | `info` / `info-soft` | alias funcional de `primary`/`primary-soft` |
| Neutro | `neutral` / `neutral-soft` | `#4B5563` / `#E7E9EC` |

`primary` deriva del azul `#1e3a5f` que el ERP real ya usa hoy en los
encabezados de los reportes PDF (`apps/reports/exports.py`) — no es un color
inventado desde cero, sino uno que ya existe funcionalmente en el sistema,
refinado para uso como acento interactivo. `success`/`danger` se eligieron
deliberadamente separados del eje rojo-verde puro (el success tira a
verde-azulado, el danger a rojo-terracota) para mejorar la distinción por
daltonismo sin depender solo del matiz.

## 4. Spacing

Escala de 10 pasos, base 4px: `space-1` (4) a `space-10` (64) — independiente
de la escala del SaaS aunque comparta la misma progresión base (4px es una
práctica general, no un elemento de identidad visual). Ver README del Lab para
el uso normalizado de cada paso.

## 5. Radius

`radius-sm` (4px, controles pequeños: badge, input, checkbox) ·
`radius-md` (6px, botón, select, KPI card) · `radius-lg` (10px, card, tabla,
alerta) · `radius-pill` (999px, toggle, barra de progreso, contador). Escala
deliberadamente más ajustada que la del SaaS (6/9/12) — Atlas comunica
precisión antes que suavidad.

## 6. Shadows

Solo dos niveles. `shadow-sm`: elevación de reposo de una card sobre
`surface-page` (sutil, casi imperceptible). `shadow-md`: exclusiva de lo que se
superpone temporalmente al contenido — menú desplegable, popover, encabezado
de tabla fijo al hacer scroll. Ninguna card en reposo usa `shadow-md`.

## 7. Buttons

Seis roles, los mismos que ya existen hoy en el ERP real (`.btn` +
`--primario`/`--secundario`/`--contorno`/`--fantasma`/`--peligro`) más el
botón de ícono — ninguno inventado. Un botón primario por vista como máximo.
Peligro se reserva a una acción que el ERP ya protege con `confirm()`. Tres
tamaños (`sm`/estándar/`lg`) y un estado de carga que sustituye el texto por
un spinner de 14px sin cambiar el ancho del botón. Ver componente **Buttons**
en el Lab.

## 8. Inputs

Texto, select y textarea con cuatro estados reales: reposo, foco
(`focus-ring`, 2px + 2px de separación), ayuda (`text-muted`) y error
(`danger`, borde + texto + ícono — nunca solo color). Checkbox, radio y
toggle cubren las tres necesidades reales encontradas: selección múltiple
(Cobros de cliente), elección excluyente (modo de reembolso) y booleano que se
aplica de inmediato (`Integration.is_enabled`). Ver **FormFields** y
**FormControls** en el Lab.

## 9. Forms

Layout compuesto: migas → encabezado de página → card con secciones
tituladas (`h3`) → grilla de máximo 2 columnas (1 en móvil) → barra de
acciones fija al pie ("Cancelar" fantasma a la izquierda, acción primaria a
la derecha). Nunca una grilla más densa que 2 columnas — esa densidad es
exclusiva de las tablas. Ver **FormLayout** en el Lab (ejemplo real: Nuevo
gasto).

## 10. Tables

El componente más usado del sistema — casi la mitad de las ~140 pantallas
reales son, en esencia, listas con filtros. Dos densidades únicamente:
**estándar** (`space-3` de padding vertical, uso general — Ventas, Clientes,
Productos) y **financiera/densa** (`space-2`, reservada a libros de alto
volumen — Libro Mayor, movimientos de caja, nómina). Encabezado en `eyebrow`,
columna de estado con badge, columnas numéricas en `figure`/`figure-sm`
(mono, tabular, alineadas a la derecha), fila de saldo/resumen fijada al pie
con `surface-sunken`. Paginación real con conteo total, nunca solo flechas.
Selección masiva y acciones por fila solo donde el ERP real ya las tiene —
nunca inventadas. Ver **TableStandard** y **TableFinancial** en el Lab.

## 11. Cards

Encabezado (título + máximo una acción visible) + cuerpo + pie opcional.
`radius-lg` + `shadow-sm` en reposo siempre juntos; `shadow-md` solo si la
card es interactiva y está en hover. Ver **Cards** en el Lab.

## 12. KPI

Etiqueta + valor en `figure-lg` (nunca `h1` — un KPI es un dato, no un
título) + variación opcional. La variación es `success`/`danger` solo cuando
esa dirección es objetivamente buena o mala para el negocio, nunca por
convención ciega. Un KPI sin dato real muestra "—" en `text-muted`, nunca un
cero inventado ni una etiqueta "próximamente" indefinida — corrige
directamente el hallazgo del Discovery sobre el Panel actual. Ver
**KpiCards** en el Lab.

## 13. Badges

Cinco colores semánticos únicamente — positivo, atención, crítico, neutro,
informativo — el mismo vocabulario que ya resuelve `estado_badge` hoy en todo
el ERP. El color se elige por el significado funcional real del estado, nunca
por el nombre. Ver **Badges** en el Lab.

## 14. Alerts

Cuatro variantes (info/éxito/atención/crítico), siempre con ícono + título +
cuerpo. Se usan para mensajes de página completa y prosa larga (como
`failure_reason`) — un badge es para una palabra de estado, una alerta es para
una oración completa. Ver **Alerts** en el Lab (incluye el vocabulario real
del POS: "El cambio solo puede entregarse en efectivo...").

## 15. Tabs

Patrón ya real en 8+ módulos (Clientes, Proveedores, Ventas, Gastos,
Empleados, Órdenes de compra...). Pestaña activa en `h4`/`primary-strong` con
barra inferior de 2px; el contador entre paréntesis solo aparece cuando la
pestaña resume una colección real (Documentos, Pagos), nunca en una pestaña
de datos únicos. `role="tablist"`/`aria-selected` obligatorios. Ver **Tabs**
en el Lab.

## 16. Navigation

Sidebar claro (ver §1) con los **21 módulos reales agrupados en 8 dominios de
negocio** — Principal, Inventario, Comercial, Compras, Punto de Venta,
Personas, Finanzas, Sistema — ninguno eliminado ni inventado
(`docs/erp-redesign-map.md`, sección 02). Ítem activo: barra de acento
`primary` de 3px a la izquierda + fondo `sidebar-active-bg` (tinte suave,
nunca bloque sólido). Colapso/expansión funcional con estado persistido,
mismo patrón de interacción ya validado en el SaaS pero con la identidad
visual propia de Atlas. Topbar: badge de tenant, buscador opcional, menú de
usuario con los 4 ítems reales (Panel/Mi perfil/Cambiar contraseña/Cerrar
sesión). Ver **Sidebar** y **Topbar** en el Lab.

## 17. Detail views

Patrón transversal único: **migas → encabezado (título + badge de estado +
máximo 2 acciones) → resumen en definiciones → pestañas reales → contenido**.
Se repite sin cambiar de estructura en Cliente, Proveedor, Venta, Compra,
Factura de proveedor, Producto y Empleado — solo cambian los campos del
resumen y las pestañas. Acción destructiva siempre secundaria, nunca junto a
la primaria. Ver **DetailView** en el Lab (ejemplo real: Detalle de cliente).

## 18. States

Catálogo real del Discovery (`docs/erp-redesign-map.md`, sección 06), nunca
estados inventados. Vocabulario visual consistente por categoría:

- **Positivos** → `success` (pagado, activo, aprobado, en stock)
- **Pendientes** → `warning` (pendiente, por vencer, stock bajo)
- **Negativos** → `danger` (vencido, rechazado, cancelado)
- **Neutros** → `neutral` (borrador, inactivo, sin asignar)

Estados de página completa (carga/vacío/error) sin emoji — ícono de línea
monocromo, a diferencia del ERP actual. Un estado vacío siempre dice qué
falta y, si hay una acción real disponible, la ofrece como botón. Ver
**PageStates** en el Lab.

## 19. Responsive

Sidebar colapsa a riel de solo ícono en tablet; se convierte en off-canvas
en móvil (mismo mecanismo ya validado en el ERP y el SaaS actuales, con la
identidad visual de Atlas). Formularios: 2 columnas → 1 columna bajo 480px.
Tablas: el envoltorio mantiene `overflow-x:auto` propio, nunca el body de la
página scrollea horizontalmente. KPI grid: 4 → 2 columnas en móvil. El POS
recibirá su propio tratamiento responsive en la FASE 7 dedicada
(`docs/erp-redesign-map.md`, sección 17, riesgo 9) — no se diseña aquí.

## 20. Accessibility

`focus-ring` visible (2px + 2px de separación) en todo control interactivo,
nunca suprimido sin sustituto. Campo obligatorio marcado con texto
"Obligatorio", nunca solo un asterisco de color. Ningún estado se comunica
solo por color — todo badge/alerta lleva texto, todo ícono semántico va
acompañado de texto. Contraste verificado por diseño: `text-muted` sobre
`surface`/`surface-page` se eligió con margen sobre el mínimo de 4.5:1 en
ambos temas (incluido el modo Noche, donde los acentos se aclaran en vez de
reutilizar el mismo valor que en modo Día — nunca texto blanco literal sobre
un acento claro). Tamaño táctil mínimo de 36px de alto en controles
interactivos, 44px en el modo POS de mostrador. ARIA: `role="tablist"`/
`aria-selected` en pestañas, `aria-current="page"` en navegación activa,
`aria-haspopup`/`aria-expanded` en menús desplegables — todo ya como
convención real del ERP, Atlas la conserva.

---

## Qué sigue

**FASE 3 — ERP Design Lab**: explorar las pantallas principales reales
(Dashboard, tabla de Ventas, Detalle de cliente, Formulario de gasto, POS)
aplicando Atlas, probando variaciones razonables de densidad/jerarquía antes
de fijar la dirección final — usando exclusivamente los 17 componentes ya
validados en este Lab, nunca inventando un componente nuevo sobre la marcha.
Ningún archivo del ERP productivo se toca hasta FASE 5.

Como pidió el usuario: **me detengo aquí.** No se implementa Atlas en el ERP
productivo, no se migra ninguna pantalla, no se modifica el POS, no se toca
el SaaS. A la espera de tu revisión del ERP DESIGN SYSTEM SPEC y del Atlas
Lab antes de iniciar FASE 3.
