# Budun Design System V1 — Hybrid (FASE 7)

## Estado y autoridad

Este documento formaliza la dirección visual **D — Hybrid**, aprobada por
el usuario tras el Design Lab (`scratch/budun-design-lab.html`, fuera del
repositorio de producto — herramienta de comparación aislada, nunca
importada por Django), como el **Design System V1 obligatorio para el
SaaS Super Admin** de Budun.

- **Stitch** deja de ser autoridad de diseño a partir de esta fase. Solo
  puede usarse como referencia funcional puntual (qué acción existe, qué
  campo pide un formulario), nunca como fuente de valores visuales.
- **`docs/design-system.md`** (FASE 5) sigue siendo la documentación
  vigente del sistema compartido ERP+SaaS actual (`static/css/base.css`,
  `static/css/design-system.css`, `templates/layout_app.html`, `/estilo/`).
  Este documento **no lo reemplaza ni lo invalida** — el ERP y las
  pantallas SaaS aún no migradas siguen funcionando con ese sistema hasta
  que cada pantalla se reconstruya explícitamente (FASE F en adelante,
  "una pantalla a la vez"). Este archivo describe el sistema **nuevo**
  que reemplazará gradualmente la capa visual del **SaaS Super Admin**
  únicamente — el ERP no está en alcance de ninguna fase de este rediseño.
- Ningún valor de este documento fue inventado de cero: cada token viene
  auditado línea por línea del bloque `[data-lab-theme="hybrid"]
  .theme-app` y de las reglas de componentes del Design Lab (ver
  referencias `[Lab:L<n>]` junto a cada valor). Donde el Lab dejaba un
  valor ad-hoc o sin token formal (spacing, radio "pill", overlay), este
  documento lo resuelve reutilizando la escala ya existente en
  `static/css/base.css` en vez de inventar una paralela — ver §3 y §9.

## Índice

1. Identidad de Hybrid
2. Design tokens — color
3. Spacing
4. Border radius
5. Shadows (elevación)
6. Tipografía
7. Layout
8. Responsive
9. Componentes obligatorios
10. Sidebar Hybrid (especificación exacta)
11. Navegación — autoridad real
12. Tablas
13. Modales
14. Regla de no-duplicación de componentes
15. Regla de no-regresión funcional
16. Regla anti-Stitch
17. Calidad visual / anti-sobrediseño
18. Inventario real de pantallas y orden de implementación
19. Procedimiento obligatorio por pantalla
20. Archivos que se crearán/modificarán (FASE E en adelante — no ejecutado todavía)

---

## 1. Identidad de Hybrid

Hybrid combina la disciplina numérica de Ledger, la calidez tipográfica
de Aperture y la densidad operativa de Console, con un sidebar oscuro
propio (nunca copiado literalmente de Console) y acentos en azul
(`#2A4CD6`) + un segundo acento teal (`#0FA3A3`) reservado para
distinguir información secundaria (nunca para botones primarios, que
siempre usan `--accent`). Tipografía única (Public Sans para todo,
incluida la marca), radios medios (6/9/12px, ni tan angulosos como
Console ni tan redondeados como Aperture), sombras discretas de dos
niveles.

## 2. Design tokens — color

Todos los valores están auditados de `[data-lab-theme="hybrid"]
.theme-app` en el Design Lab (líneas ~224-269 en la versión actual del
archivo).

### Superficie y texto

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#F7F7F6` | Fondo del área principal (detrás de cards) |
| `--surface` | `#FFFFFF` | Cards, tablas, inputs, modal |
| `--surface-2` | `#F0F0EE` | Hover de fila, fondo de badge neutral, botón secundario |
| `--border` | `#E2E2DE` | Bordes de división (topbar, panel-head, tabla) |
| `--border-strong` | `#CACAC4` | Bordes de control (input, botón ghost) |
| `--text` | `#17181A` | Texto principal |
| `--text-muted` | `#63656C` | Texto secundario (descripciones, labels) |
| `--text-faint` | `#97989E` | Texto terciario (placeholders, iconos inactivos) |

### Acento y estados semánticos

| Token | Valor | Uso |
|---|---|---|
| `--accent` | `#2A4CD6` | Botón primario, enlaces, foco, ítem activo |
| `--accent-ink` | `#FFFFFF` | Texto/ícono sobre `--accent` |
| `--accent-soft` | `#E7ECFC` | Fondo de badge/alert informativo |
| `--accent-2` | `#0FA3A3` | Acento secundario — **solo** para distinguir dato/estado secundario (p. ej. un segundo indicador en un KPI), nunca en botones primarios ni en navegación |
| `--success` / `--success-soft` | `#157F3C` / `#E3F5E9` | Estado positivo (pago aplicado, activo) |
| `--warning` / `--warning-soft` | `#9A6300` / `#FBEED9` | Estado de atención (vencimiento próximo, pendiente) |
| `--danger` / `--danger-soft` | `#B42318` / `#FBE6E4` | Estado crítico, acción destructiva |
| `--info` / `--info-soft` | `#2A4CD6` / `#E7ECFC` | Igual que accent — reservado para mensajes informativos |

### Sidebar (propios, no comparten los de la superficie principal)

| Token | Valor | Uso |
|---|---|---|
| `--sidebar-bg` | `#101216` | Fondo del sidebar (oscuro, identidad propia de Hybrid) |
| `--sidebar-border` | `#22252C` | Borde derecho del sidebar, separador de marca, borde del toggle |
| `--sidebar-text` | `#AEB1BC` | Texto/ícono de enlace de navegación en reposo |
| `--sidebar-text-muted` | `#6D7078` | Etiqueta de grupo, ícono del toggle en reposo |
| `--sidebar-brand-text` | `#FFFFFF` | Nombre "Budun" junto al mark — **token dedicado**, no reutiliza `--sidebar-text` (ver nota de corrección de contraste abajo) |
| `--sidebar-active-bg` | `#1C2A66` | Fondo del enlace activo |
| `--sidebar-active-text` | `#FFFFFF` | Texto/ícono del enlace activo |

**Nota de corrección heredada (FASE 6.6.1)**: el Lab originalmente tenía
`.app-brand__name { color: #fff }` fijo en CSS compartido por los 4
temas. Como Ledger tiene sidebar claro, eso lo dejaba invisible
(blanco sobre blanco). La corrección introdujo el token
`--sidebar-brand-text`, distinto por tema. Para Hybrid vale `#FFFFFF`
(su sidebar es oscuro, ya tenía buen contraste), pero el V1 **debe**
seguir usando el token, nunca un color fijo, para que este bug no
pueda repetirse si en el futuro cambia el fondo del sidebar.

### Overlay (nuevo en V1 — no existía como token en el Lab)

El Lab usaba un valor literal en `.modal-backdrop`
(`rgba(10,10,14,.5)` + `backdrop-filter: blur(2px)` — `[Lab:L645]`),
sin tokenizar. Antes de inventar un valor nuevo se revisó el overlay
real ya usado por el SaaS actual (`static/css/design-system.css:1642-1646`,
`.shell--saas dialog.modal::backdrop { background: rgb(15 23 42 / 0.6);
backdrop-filter: blur(2px); }`) — incorporado en una fase anterior de
este mismo rediseño. V1 formaliza un token coherente con ambos:

| Token | Valor |
|---|---|
| `--overlay` | `rgb(9 10 13 / 0.6)` (mismo alpha que el SaaS actual, tono ajustado a la paleta fría de Hybrid) |
| `--overlay-blur` | `2px` (mismo blur ya validado en el sistema real) |

## 3. Spacing

El Lab, al ser un prototipo de comparación rápida, usó valores ad-hoc
por componente (`16px 14px 14px` en el sidebar, `22px 24px 30px` en el
contenido, `18px 20px` en cards, gaps de `12/14/16px` según la sección).
Esto es exactamente la inconsistencia que §16 (regla anti-Stitch) prohíbe
propagar. `static/css/base.css` **ya define** una escala real de 4px
(`--espacio-1` a `--espacio-12`, líneas 107-115) usada hoy por el ERP y
el SaaS actual — se reutiliza en vez de crear una segunda escala
paralela:

| Token existente | Valor | Uso normalizado en V1 |
|---|---|---|
| `--espacio-1` | 4px | Separación entre ítems de un mismo grupo de nav (Lab usaba 2px — se ajusta a 4px, el paso más cercano de la escala real) |
| `--espacio-2` | 8px | Gap interno de badge/alert, gap de botón+ícono |
| `--espacio-3` | 12px | Gap de `kpi-row`, padding vertical de controles pequeños |
| `--espacio-4` | 16px | Padding horizontal de página, gap del sidebar nav-scroll, padding de card (lado) |
| `--espacio-5` | 20px | Padding vertical de card, separación título/contenido |
| `--espacio-6` | 24px | Padding horizontal del área de contenido, gap entre secciones |
| `--espacio-8` | 32px | Padding inferior del área de contenido, separación entre bloques grandes |

Mapeo explícito Lab → V1 (para que la implementación real sea
trazable, no una reinvención):

| Componente | Valor Lab | Valor V1 (escala real) |
|---|---|---|
| `.app-content` padding | `22px 24px 30px` | `var(--espacio-6) var(--espacio-6) var(--espacio-8)` → `24px 24px 32px` |
| `.card-pad` | `18px 20px` | `var(--espacio-5) var(--espacio-5)` → `20px 20px` |
| `.app-sidebar` padding | `16px 14px 14px` | `var(--espacio-4) var(--espacio-4)` → `16px 16px` (compacto usa `padding-inline: var(--espacio-3)` = 12px, más denso, igual que hoy) |
| `.app-sidebar__nav-scroll` gap | `16px` | `var(--espacio-4)` → sin cambio |
| `.app-nav-group` gap interno | `2px` | `var(--espacio-1)` → 4px |
| `.page-header` margin-bottom | `18px` | `var(--espacio-5)` → 20px |
| `.panel-head` padding | `14px 16px` | `var(--espacio-4) var(--espacio-4)` → 16px 16px |
| `.kpi-row` gap | `12px` | `var(--espacio-3)` → sin cambio |
| `.modal-box__head/body/foot` padding | `16-18px` | `var(--espacio-4)`/`var(--espacio-5)` → 16px/20px consistente |
| Tabla, padding horizontal de celda | `14px` | `var(--espacio-4)` → 16px |

## 4. Border radius

Del bloque Hybrid del Lab (`[Lab:L246]`):

| Token | Valor | Uso |
|---|---|---|
| `--radius-sm` | 6px | Controles pequeños: badge (modo denso), nav-link, botón de paginación |
| `--radius-md` | 9px | Botones, inputs, alert |
| `--radius-lg` | 12px | Card, KPI, modal, dropdown |
| `--radius-pill` | 999px | **Nuevo, formalizado en V1** — el Lab usaba `999px` como literal repetido en `.badge`, `.switch__track`, `.app-user__avatar`, `.pagination__pages button` sin nombrarlo. V1 lo nombra para que ningún componente futuro reinvente el valor. |

## 5. Shadows (elevación)

Sistema de 2 niveles + plano, ya coherente en el Lab (auditado, no
inventado):

| Token | Valor | Cuándo se usa |
|---|---|---|
| *(sin sombra)* | — | Elementos en el plano base: filas de tabla, sidebar, topbar |
| `--shadow-card` | `0 10px 24px -12px rgba(20,20,25,.16)` | Elevación de reposo: card, KPI, panel |
| `--shadow-float` | `0 18px 44px -12px rgba(15,15,20,.30)` | Elevación flotante: dropdown, modal |

Regla: una sombra solo se usa para estos dos niveles de jerarquía real
(reposo vs. flotante). Nunca se agrega una sombra a un elemento que no
necesita comunicar elevación (§17).

## 6. Tipografía

Familias (Hybrid, `[Lab:L225-227]`): `--font-display` / `--font-body` =
**Public Sans**, `--font-mono` = **JetBrains Mono** (para toda cifra de
negocio — dinero, cantidades, IDs, fechas en tabla).

Escala auditada del Lab (tamaño / peso / uso):

| Elemento | Tamaño | Peso | Otros |
|---|---|---|---|
| Título de página (`h2` de `page-header`) | 21px | 800 | `letter-spacing:-.01em`, `text-wrap:balance` recomendado |
| Descripción de página | 12.5px | 400 | `color: var(--text-muted)` |
| Título de panel/card (`h3`) | 14px | 800 | — |
| Nombre de marca (sidebar) | 14px | 800 | `letter-spacing:-.01em` |
| Enlace de navegación | 13px | 500 | — |
| Etiqueta de grupo de navegación | 10px | 700 | uppercase, `letter-spacing:.09em` |
| Botón | 13px | 700 | `line-height:1` |
| Label de campo de formulario | 11.5px | 700 | `color: var(--text-muted)` |
| Valor de KPI | 22px | 800 | **`font-family: var(--font-mono)`, `font-variant-numeric: tabular-nums`**, `letter-spacing:-.01em` |
| Etiqueta de KPI | 11px | 600 | — |
| Encabezado de tabla (`th`) | 10.5px | 700 | uppercase, `letter-spacing:.05em` |
| Celda de tabla | 12.5px | 400 | columnas numéricas: `font-family: var(--font-mono)`, `font-variant-numeric: tabular-nums`, alineadas a la derecha |
| Badge | 11px | 700 | — |
| Alert | 12.5px | 400 | `line-height:1.5` |
| Título de modal (`h4`) | 15px | 800 | — |
| Subtítulo/cuerpo de modal | 11.5-12.5px | 400 | `color: var(--text-muted)` |

**Regla de cifras de negocio** (obligatoria, pedida explícitamente por
el usuario): todo monto, cantidad o ID numérico en KPI o tabla usa
`var(--numeric-font)` (= `--font-mono` = JetBrains Mono en Hybrid) +
`font-variant-numeric: tabular-nums`, para que las columnas de dinero
alineen verticalmente dígito por dígito — ya es el comportamiento
auditado del Lab (`.kpi__value`, `.data-table .num`), se formaliza como
regla del sistema, no una decisión aislada de un componente.

## 7. Layout

- **Ancho máximo de contenido**: el Lab no define un tope explícito
  (su mini-pantalla es de tamaño fijo de demostración). Para la
  implementación real, V1 hereda el mismo criterio ya vigente en
  `static/css/design-system.css` para `.shell--saas .main__contenido`
  (tope de 1280px, con modificadores `--estrecho`/`--ancho`/`--completo`
  ya auditados y corregidos en una fase anterior de este mismo
  rediseño) — **no se inventa un segundo sistema de anchos de página**.
- **Sidebar**: compacto `76px` / expandido `228px` — ver §10.
- **Topbar**: `56px` de alto fijo, fondo `--surface`, borde inferior
  `--border`, contenido alineado a la derecha (usuario/avatar).
- **Page header**: título + descripción a la izquierda, acción primaria
  a la derecha, `flex-wrap` para responsive.
- **Grids**: KPI row = `repeat(auto-fit, minmax(160px, 1fr))`, gap
  `--espacio-3` (12px).
- **Card**: `--surface`, `var(--card-border)`, `--radius-lg`,
  `--shadow-card`, padding `--espacio-5` (20px).
- **Tabla**: ver §12.
- **Modal**: ver §13.

## 8. Responsive

El Lab implementa el mecanismo correcto con **container queries**
(`container-type: inline-size`), no `@media` — necesario porque el
shell real puede vivir en distintos anchos de columna según el sidebar,
y una media query no puede reaccionar a eso. Dos puntos de quiebre
auditados:

| Quiebre | Contenedor ≤ | Cambia |
|---|---|---|
| Tablet | 900px | Sidebar fuerza icon-only (64/76/88/232→64px equivalente compacto) para los 4 sistemas; el toggle de expandir queda sin efecto (ver §10) |
| Mobile | 480px | KPI row pasa a 2 columnas, padding de contenido se reduce, page-header y panel-head apilan verticalmente |

Regla explícita (pedida por el usuario): un cambio de estructura
responsive debe ser deliberado (una regla de layout que reorganiza), no
una compresión accidental (achicar fuentes/paddings hasta que "quepa").

## 9. Componentes obligatorios

Cada componente listado abajo existe **una sola vez** en el sistema —
nunca una variante duplicada por pantalla (`.boton-dashboard` vs.
`.boton-clientes` es exactamente el antipatrón prohibido en §14).
Estados soportados por componente, auditados del Lab:

| Componente | Clase base | Estados auditados en el Lab |
|---|---|---|
| Sidebar | `.app-sidebar` | compacto / expandido (ver §10) |
| Sidebar group | `.app-nav-group` + `.app-nav-group__label` | — |
| Sidebar item | `.app-nav-link` | default, hover (implícito vía `:hover` heredado del navegador — **pendiente definir explícito en V1 real**, ver nota abajo), active (`.is-active`), focus-visible (heredado) |
| Sidebar toggle | `.app-sidebar__toggle` | default, hover, focus-visible |
| Topbar | `.app-topbar` | — |
| Avatar/user menu | `.app-user`, `.app-user__avatar` | — |
| Page header | `.page-header` | — |
| Breadcrumb | `.back-link` | Solo donde ya existe navegación jerárquica real (p. ej. Detalle de Tenant → volver a Tenants). No se agrega a pantallas de primer nivel. |
| Card | `.card` + `.card-pad` | — |
| Button | `.btn` | default, hover, focus-visible, disabled |
| Button primary | `.btn-primary` | ídem |
| Button secondary | `.btn-secondary` | ídem |
| Button ghost | `.btn-ghost` | ídem |
| Button danger (destructivo) | `.btn-destructive` | ídem — **falta variante "danger soft"** pedida por el usuario, no existía en el Lab; V1 la agrega como `.btn-destructive-soft` (`background: var(--danger-soft); color: var(--danger)`), mismo patrón que `.badge-danger`, para acciones destructivas secundarias (p. ej. "Cancelar" dentro de un modal de confirmación, junto al botón `.btn-destructive` real) |
| Input / Select / Textarea | `.field input`, `.field select`, `.field textarea` | default, focus, disabled (pendiente formalizar explícitamente — el Lab no lo demuestra) |
| Checkbox | `.check-row input[type=checkbox]` | default, checked (nativo) |
| Radio | — | **No existe en el Lab.** Se construye en V1 reutilizando exactamente el patrón visual de `.check-row` (mismo tamaño, gap, tipografía), solo cambia `type=radio` |
| Form field | `.field` | default, con error (**pendiente** — el Lab no demuestra estado de error de formulario; V1 lo define como borde `--danger` + texto de ayuda `--danger` bajo el campo, mismo patrón que `.alert-danger`) |
| Badge | `.badge` + `.badge-{success,warning,danger,info,neutral}` | — |
| Status badge | mismo componente `.badge`, mapeado semánticamente por estado real del dato (no una clase nueva) | — |
| Alert | `.alert` + `.alert-{info,success,warning,danger}` | — |
| Tabs | `.tabs` | default, active |
| Dropdown | `.dropdown-menu` | abierto/cerrado |
| Table | `table.data-table` | hover de fila |
| Table actions | `.data-table a.row-link` | default, hover |
| Empty state | `.state-block` | — |
| Loading state | `.skeleton-line` | animación shimmer |
| Modal | `.modal-box` | — |
| Confirmation modal | `.modal-box` + `.modal-box__icon` neutro/informativo | — |
| Destructive confirmation modal | `.modal-box` + `.modal-box__icon` con `--danger-soft`/`--danger` | — |
| Pagination | `.pagination` | página activa |
| Toast/feedback | **No está en el Lab** — el sistema real (`static/js/ui.js` `.toast`) ya existe y se reutiliza tal cual, solo re-tokenizado a los valores Hybrid |
| KPI/stat card | `.kpi` | delta up/down |
| Currency/amount display | `.data-table .num`, `.kpi__value` (mono + tabular-nums) | — |

**Nota pendiente real** (no inventar ahora): el Lab no define
explícitamente `:hover`/`:focus-visible`/`:disabled` para `.app-nav-link`
ni estado de error de `.field`. Antes de implementar el Master Shell
real, estos dos casos deben resolverse consultando primero si
`static/css/design-system.css` ya tiene un patrón (`:focus-visible` con
`outline: 2px solid` es el patrón ya usado en botones/inputs actuales,
según `docs/design-system.md`) y reutilizándolo con los tokens Hybrid,
en vez de inventar un tratamiter nuevo — exactamente la regla del punto
7 del audit.

## 10. Sidebar Hybrid (especificación exacta)

| Propiedad | Valor |
|---|---|
| Ancho compacto | **76px** |
| Ancho expandido | **228px** |
| Fondo | `--sidebar-bg` (`#101216`) |
| Modo inicial | Compacto (`data-sidebar-expanded="false"`) |
| Control de expandir/contraer | Botón `.app-sidebar__toggle`, ícono de flecha que rota 180°, **fuera** de la región con scroll (nunca se desplaza fuera de vista) |
| Scroll interno | `.app-sidebar__nav-scroll { overflow-y:auto }` + clase utilitaria `.scrollbar-hidden` (barra oculta, scroll funcional — nunca `overflow:hidden`) |
| Reset al cambiar de tema (solo aplica a este Lab de comparación, no al producto real que no tiene "temas") | — |
| Compacto | Solo ícono, centrado, texto con `display:none` (nunca truncado con ellipsis) |
| Expandido | Ícono + texto completo, ninguna etiqueta se corta — verificado por ancho de texto contra 228px para las etiquetas más largas reales: "Clientes y tenants", "Configuración / cuenta", "Cambiar contraseña", "Cuentas bancarias" |
| Reajuste del contenido principal | CSS Grid `grid-template-columns: var(--sidebar-width) 1fr` — el área principal (`1fr`) se recalcula automáticamente, nunca posición absoluta |
| Overflow horizontal | Ninguno — `.app-sidebar { overflow:hidden }` + `min-width:0` en cada hijo flex, salvaguarda contra el "grid blowout" de `min-width:auto` |

## 11. Navegación — autoridad real

Única fuente: 7 grupos / 14 ítems, verificados contra
`apps/billing/admin_urls.py` (URLs reales existentes hoy):

| Grupo | Ítem | `name` real de la URL |
|---|---|---|
| Inicio | Dashboard | `billing_admin:dashboard` |
| Clientes y tenants | Tenants | `billing_admin:tenants_list` |
| | Clientes | `billing_admin:customers_list` |
| Comercial | Venta manual | `billing_admin:manual_sale` |
| | Planes | `billing_admin:plans_list` |
| | Suscripciones | `billing_admin:subscriptions_list` |
| Facturación | Facturas | `billing_admin:invoices_list` |
| Finanzas | Pagos | `billing_admin:payments_list` |
| | Transferencias | `billing_admin:transfers_queue` |
| | Reembolsos | `billing_admin:refunds_list` |
| | Cuentas bancarias | `billing_admin:bank_accounts_list` |
| Reportes | Reportes | `billing_admin:reports` |
| Configuración / cuenta | Mi perfil | `billing_admin:profile` |
| | Cambiar contraseña | `billing_admin:password_change` |

**No existe** "Configuración general" ni "Notas de crédito" como URL
real — confirmado, no se agregan (§14 de la instrucción del usuario,
FASE previa de este mismo rediseño ya las retiró del Super Admin real).

## 12. Tablas

Patrón único `table.data-table`, auditado del Lab:

- Encabezado: `--table-head-bg` (transparente en Hybrid), texto 10.5px/700
  uppercase, `--text-muted`, borde inferior `--table-head-border`.
- Altura de fila: `--row-h` = **40px** en Hybrid (Console usa 36px,
  Aperture 50px — cada sistema define su propia densidad, Hybrid queda
  a medio camino, consistente con su identidad).
- Padding horizontal de celda: `--espacio-4` (16px, normalizado desde
  14px — ver §3).
- Alineación: texto a la izquierda, números/moneda a la derecha
  (`.num`, mono + tabular-nums).
- Hover de fila: `background: var(--surface-2)`.
- Borde: 1px `--border` bajo cada fila, sin borde en la última.
- Acciones: enlace `--accent` con `font-weight:700`, subrayado solo en
  hover.
- Responsive: ninguna tabla se comprime con `font-size` reducido; el
  patrón real a definir por pantalla (scroll horizontal contenido vs.
  colapso a tarjetas) se decide en FASE F por pantalla, según densidad
  real de columnas — no se resuelve en este documento de forma genérica
  para no imponer una solución que no se haya visto contra datos reales.
- Empty state: `.state-block` dentro del `tbody`/debajo de la tabla,
  nunca una fila con "sin resultados" como único texto plano.

## 13. Modales

Patrón único `.modal-box` (usa `<dialog>` nativo en la implementación
real, igual que el sistema actual — foco atrapado y `Escape` nativos):

- Ancho: `min(420px, 100%)`.
- Radio: `--radius-lg` (12px).
- Sombra: `--shadow-float`.
- Overlay: `--overlay` + `backdrop-filter: blur(--overlay-blur)` (ver §2).
- Estructura fija: `__head` (ícono + título + subtítulo) → `__body`
  (texto + `.callout` opcional) → `__foot` (acciones alineadas a la
  derecha, `.btn-ghost`/`.btn-secondary` primero, acción principal al
  final).
- **Modal destructivo**: mismo componente, `__icon` con
  `background:var(--danger-soft); color:var(--danger)` en vez del
  neutro. Un único patrón para Suspender/Cancelar/Reembolsar/Eliminar —
  nunca estilos distintos entre acciones críticas (regla explícita del
  usuario). El botón de confirmación usa `.btn-destructive`; si el modal
  ofrece una acción secundaria destructiva "suave" (p. ej. deshacer
  parcial), usa `.btn-destructive-soft` (§9).

## 14. Regla de no-duplicación de componentes

Cuando dos pantallas necesiten "un botón que guarda", "una tarjeta que
resume", "una tabla que lista": es el **mismo** componente (`.btn-primary`,
`.card`, `.data-table`), nunca una clase nueva con el nombre de la
pantalla. Antes de crear una clase nueva, verificar en este documento
si el componente ya existe; si existe pero con un caso no cubierto,
se extiende el componente (nuevo modificador, ej. `.btn-destructive-soft`
en §9), nunca se clona.

## 15. Regla de no-regresión funcional

El Design System es autoridad **visual**. La funcionalidad real de
Django (modelos, URLs, permisos, nombres de campo, POST, validaciones,
consultas) es autoridad **funcional** y no se toca para conseguir una
apariencia. Ningún archivo de este documento ni de las fases siguientes
modifica `models.py`, `views.py`, `forms.py`, `urls.py` a menos que el
usuario lo pida explícitamente y por separado de una tarea de diseño.

## 16. Regla anti-Stitch

Cuando una pantalla real (al llegar la FASE F) muestre una
inconsistencia heredada de Stitch (dos botones visualmente distintos
para la misma acción, spacing distinto entre pantallas para el mismo
componente), **no se copia la inconsistencia**. Se resuelve aplicando
el componente único de este documento y luego adaptando la composición
específica de esa pantalla a los datos reales que muestra.

## 17. Calidad visual / anti-sobrediseño

Prohibido agregar, sin que exista ya en este documento o sin necesidad
funcional real: gradientes decorativos, animaciones sin propósito,
sombras extra, glassmorphism, colores fuera de la paleta tokenizada,
iconos decorativos sin función, tarjetas anidadas sin necesidad. La
única animación ya auditada y aceptada es el shimmer de `.skeleton-line`
(estado de carga, tiene función) y la transición de 0.16s en
hover/toggle (micro-interacción de feedback, no decorativa).

## 18. Inventario real de pantallas y orden de implementación

Verificado contra `apps/billing/admin_urls.py`, `apps/billing/urls.py`
(PayPal plataforma) y `apps/billing/portal_urls.py` (portal del tenant,
**fuera de alcance** de este Design System — usa `layout_app.html`,
shell del ERP, no del Super Admin).

Orden de implementación (FASE F, no iniciada):

1. Master Shell (`templates/layout_saas_admin.html`)
2. Dashboard — `billing_admin:dashboard`
3. Clientes — `billing_admin:customers_list`
4. Customer Detail — `billing_admin:customer_detail`
5. Tenants — `billing_admin:tenants_list`
6. Tenant Detail — `billing_admin:tenant_detail`
7. Venta manual — `billing_admin:manual_sale`
8. Planes — `billing_admin:plans_list` (+ modal `plan_version_create`)
9. Suscripciones — `billing_admin:subscriptions_list`
10. Facturas — `billing_admin:invoices_list`
11. Invoice Detail — `billing_admin:invoice_detail`
12. Pagos — `billing_admin:payments_list` (+ modal `request_refund`)
13. Transferencias — `billing_admin:transfers_queue`
14. Proof Detail — `billing_admin:proof_detail` (+ `proof_download`, sin UI propia)
15. Reembolsos — `billing_admin:refunds_list` (+ `complete_refund`)
16. Cuentas bancarias — `billing_admin:bank_accounts_list` (+ `bank_account_update`, `bank_account_toggle_active`)
17. Reportes — `billing_admin:reports`
18. Perfil — `billing_admin:profile`
19. Cambiar contraseña — `billing_admin:password_change`
20. Contraseña actualizada — `billing_admin:password_change_done`
21. PayPal Status — `billing:status` (Super Admin de plataforma, `is_superuser`, ver `docs/paypal.md`)
22. PayPal Checkout — `billing:checkout_create`
23. PayPal Resultado — `billing:checkout_return` / `billing:checkout_cancel`
24. PayPal Transacción — `billing:transaction_detail`
25+. Modales asociados a cada pantalla anterior (confirmaciones, destructivos) — se implementan junto con la pantalla que los dispara, no por separado.

## 19. Procedimiento obligatorio por pantalla (FASE F, recordatorio — no ejecutado en esta fase)

Para cada pantalla, en este orden: (a) leer el template Django completo,
(b) identificar datos reales/formularios/botones/acciones/URLs/permisos/
modales/tablas/estados/condiciones, (c) mapear cada elemento a un
componente de este documento, (d) implementar, (e) revisar el HTML/CSS
generado, (f) ejecutar `manage.py check`, (g) ejecutar los tests
correspondientes, (h) si hay navegador disponible abrir la ruta real; si
no lo hay, declarar explícitamente **"VALIDACIÓN DE CÓDIGO COMPLETADA —
VALIDACIÓN VISUAL DE NAVEGADOR PENDIENTE"**, nunca afirmar validación
visual sin haberla hecho.

## 20. FASE E — Master Shell (implementado)

Primer bloque real ejecutado. Archivos modificados:

- `templates/layout_saas_admin.html` — sidebar reestructurado: nuevo
  wrapper `.sidebar__nav-scroll` (marca + los grupos, único elemento
  con scroll interno), botón `.sidebar__toggle-ancho`
  (`data-sidebar-ancho-toggle`, distinto del toggle móvil existente)
  como hermano fuera de esa región, texto de cada enlace envuelto en
  `.sidebar__enlace-texto` (necesario para poder ocultarlo en modo
  compacto sin truncarlo). Regrupado: "Facturación" ahora solo tiene
  Facturas; "Finanzas" tiene Pagos/Transferencias/Reembolsos/Cuentas
  bancarias (antes repartidos de otra forma). Grupo nuevo
  "Configuración / cuenta" (Mi perfil, Cambiar contraseña) agregado al
  sidebar — antes esas dos rutas solo vivían en el dropdown del topbar,
  que se conserva sin cambios. Grupo "Integraciones" (PayPal) mantenido
  como 8º grupo por decisión explícita del usuario: el Design System V1
  define 7 grupos, pero una funcionalidad real existente nunca se
  elimina solo para igualar el número de grupos de la galería de
  referencia — regla explícita: funcionalidad real > restricción de la
  demo. Fuentes cambiadas de Geist/Inter a Public Sans en `extra_head`.
- `static/css/design-system.css` — dentro de `.shell--saas` únicamente:
  tokens `--color-primario`/`--color-primario-hover` actualizados de
  Stitch (#2563EB) a Hybrid (#2A4CD6/#2140B8); nuevas variables
  `--ancho-sidebar-saas-compacto`(76px)/`--ancho-sidebar-saas-expandido`(228px)/
  `--ancho-sidebar-saas`, deliberadamente separadas de `--ancho-sidebar`
  (ERP, base.css, nunca tocada); atributo `data-sidebar-modo` en
  `.shell--saas` controla cuál se usa. Colores de sidebar/marca/avatar
  actualizados de los hex de Stitch a los de Hybrid (`#101216`
  fondo, `#22252C` borde, `#AEB1BC` texto, `#1C2A66` activo). Nueva
  región `.sidebar__nav-scroll` con scroll funcional y barra oculta
  (`scrollbar-width:none` + `::-webkit-scrollbar{width:0}`, nunca
  `overflow:hidden`). Nuevo componente `.sidebar__toggle-ancho`. Reglas
  de modo compacto/expandido acotadas a `@media (min-width:1025px)` —
  en tablet/móvil el sidebar sigue siendo el panel off-canvas existente
  a ancho completo, sin cambios de comportamiento. Se retiraron 2 reglas
  de scrollbar visible ya sin efecto (documentado inline, no borrado
  silencioso).
- `static/js/ui.js` — nueva función `initSidebarAnchoToggle()`,
  independiente de `initSidebar()` (móvil, sin tocar). Persiste el modo
  compacto/expandido en `localStorage` para que no se reinicie en cada
  navegación real (recarga completa de página, no SPA).
- `apps/core/templatetags/ui_icons.py` — 2 iconos nuevos ("perfil",
  "candado") para los 2 ítems nuevos del sidebar; ningún icono
  existente encajaba sin reutilizar uno ya asignado a otro significado.
- `apps/billing/tests/test_ui_saas_shell.py` — test de grupos
  actualizado a los 8 grupos reales; 3 tests nuevos (reagrupación
  Facturación/Finanzas, grupo Configuración/cuenta, presencia del
  toggle de ancho).
- Este documento (§20).

**NO modificado**: ERP, modelos, vistas, URLs, permisos, formularios de
negocio, ninguna plantilla de pantalla SaaS individual, `base.css`
(ver nota transparente en `.shell--saas` sobre `--color-saas-sidebar-*`,
dejados intactos por estar fuera del alcance de archivos de esta fase).
