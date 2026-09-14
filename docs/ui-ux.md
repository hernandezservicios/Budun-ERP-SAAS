# UX/UI Design System

## Dirección visual
Elegir un estilo SaaS empresarial moderno: limpio, sobrio, profesional, legible y orientado a productividad. La estética debe provenir de jerarquía, spacing, tipografía y consistencia, no de colores excesivos.

## Colores
- Azul: primary/action/navigation — identidad única de TODO el proyecto (ERP y SaaS).
- Verde: **exclusivamente** success/estado positivo — nunca color estructural/secundario en ninguna vista nueva.
- Neutrales: fondos, superficies y texto.
- Rojo/ámbar: exclusivamente para estados semánticos.

Evitar neón, arcoíris, fondos multicolor, gradientes dominantes y tarjetas excesivas.

### Dos identidades, un mismo sistema (FASE DE REDISEÑO VISUAL SaaS)
El ERP tenant (`templates/layout_app.html`) conserva azul+verde tal como se
documentó en FASE 5 — `--color-secundario` (verde) sigue siendo un botón
secundario legítimo ahí (Ventas, Compras), y no se retiró ni se rediseñó.
La **plataforma SaaS** (Super Admin — `templates/layout_saas_admin.html`,
namespaces `billing_admin`/`billing_platform`) adoptó una identidad
deliberadamente distinta: azul + neutrales, con un sidebar azul profundo
propio (`--color-saas-sidebar-*`, ver `docs/design-system.md`) y **sin
verde estructural** — verde queda reservado ahí exclusivamente para
estados de éxito (`badge--verde`, `kpi--exito`). Ningún token existente se
eliminó; ambos shells comparten `base.css`/`design-system.css`.

### Refinamiento visual de la plataforma SaaS (FASE — REDISEÑO VISUAL INTEGRAL SaaS 2.0)
Sobre la separación de shells de la fase anterior, la plataforma SaaS
(`.shell--saas`) recibió: tamaños de encabezado explícitos de la
escala tipográfica (`h1`=`--texto-2xl`, `h2`=`--texto-lg`,
`h3`=`--texto-base`, acotados al modificador — el ERP conserva el
tamaño por defecto del navegador, sin cambios); iconos con emoji en
cada enlace del sidebar y cada KPI (mismo mecanismo ya usado en
`estado-vacio__icono`, nunca una librería de iconos nueva); espaciado
más generoso en `.main`. Scrollbar fina (`scrollbar-width: thin` +
`::-webkit-scrollbar`) y `overflow-x: hidden` en `body` se dejaron
GLOBALES (todo el proyecto, ERP incluido) — son mejoras neutras de
plataforma/navegador, no cambios de identidad visual. (Nota: los
iconos con emoji mencionados aquí se reemplazaron por completo en la
fase siguiente — ver más abajo.)

### Rediseño Visual Maestro (basado en imagen de referencia)
A partir de una imagen de referencia visual maestra (nunca copiada
literalmente — solo su lenguaje visual), la plataforma SaaS ganó: un
sistema de iconos SVG inline propio (`{% icono %}`,
`apps/core/templatetags/ui_icons.py`) que reemplaza TODO el emoji de
interfaz anterior; una KPI card v2 (`.saas-kpi-card`, icono circular +
tendencia — componente nuevo, nunca una modificación de `.kpi`/
`.kpi-grid`, que el ERP sigue usando sin cambios); gráficas de línea y
dona dibujadas con SVG inline (sin librería de gráficas,
`apps/core/templatetags/ui_charts.py`) con datos 100% reales (ingresos
últimos 6 meses, distribución de suscripciones por estado, actividad
reciente); un buscador de navbar deliberadamente inerte (sin backend
real todavía) y un avatar con iniciales. Ver "SaaS Master Visual
Language Patterns" en `docs/project-status/SAAS_PLATFORM_KNOWLEDGE_KIT.md`
para el detalle completo de cada patrón, y `docs/design-system.md`
para dónde vive cada pieza.

## UX
Prioridades: experiencia de usuario > legibilidad > claridad > jerarquía > consistencia > estética.

## Componentes
Botones, tablas, formularios, modales, alerts, toast, pagination, cards, KPI cards, empty/loading/error states.

## Responsive
Desktop, tablet y mobile reales. POS especialmente táctil y rápido.

## Accesibilidad
Contraste, foco, keyboard navigation, labels, semantic HTML.
