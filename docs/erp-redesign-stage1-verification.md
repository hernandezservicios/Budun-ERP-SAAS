# ERP REDESIGN — VERIFICACIÓN ETAPA 1 (FASE 5)

Fundación visual del ERP (tokens + shell + componentes base) —
implementada y verificada. Pantallas reales quedan para Etapa 2.

## Archivos modificados/creados

| Archivo | Tipo | Qué cambió |
|---|---|---|
| `static/css/design-system-erp.css` | **Nuevo** | Tokens Atlas exactos (color primario `#1D4E89`, success/warning/danger/neutral, superficie/texto), tipografía (IBM Plex Sans + `--fuente-mono` IBM Plex Mono), sidebar agrupado (ancho 228px/64px, acento de 3px, modo compacto), topbar (ícono de hamburguesa), fondo de `.main`. Todo bajo `.shell--erp` — radios y spacing heredados sin cambios (ya coincidían). |
| `templates/layout_app.html` | Modificado | Clase `shell--erp` añadida a `.shell`; sidebar reagrupado en 8 dominios (`.sidebar__grupo`/`.sidebar__grupo-titulo`, reutilizando las mismas clases que ya usa el sidebar del SaaS) con un ícono SVG de línea por ítem (21, reutilizados del Atlas ERP Lab ya aprobado en FASE 3); botón de colapso/expansión nuevo; bloque `extra_head` con el `<link>` de Google Fonts + el CSS nuevo; ícono de hamburguesa SVG en vez del carácter `☰`. **Cada uno de los 21 `{% url %}` y cada condición `aria-current` se preservó exactamente igual, verbatim.** |
| `static/js/ui.js` | Modificado (aditivo) | Función nueva `initSidebarAnchoToggleErp()` (mismo patrón que `initSidebarAnchoToggle` del SaaS, pero independiente: propio atributo `data-sidebar-ancho-toggle-erp`, propia clave de `localStorage` `budun-erp-sidebar-modo`), añadida a la lista de inicialización. **Ninguna función existente fue modificada.** |

No se tocó `static/css/base.css`, `static/css/design-system.css`, ningún
modelo, vista, formulario, URL, permiso, migración, ni la lógica de
Compras (la función de recepción sigue pendiente por decisión explícita
del usuario, no implementada).

## Componentes migrados (tokens, sin reescribir el componente)

Buttons, Cards, Badges, Alerts, FormFields, TableStandard, Pagination,
Breadcrumbs (`.migas`), Page Header (`.encabezado-pagina`), Dropdown —
los 9 heredan la paleta Atlas automáticamente por estar dentro de
`.shell--erp`, sin ninguna modificación a sus reglas CSS originales en
`design-system.css` (confirmado por lectura línea por línea de cada
selector antes de decidir qué custom properties sobreescribir). Tabs
(`data-tabs`) no se tocó en absoluto — ni CSS ni JS — porque su
estructura ya cumple Atlas al 100% (ARIA correcto, JS ya reutilizable
sin cambios).

Nuevo: utilidad `.u-cifra` (mono + `tabular-nums`) definida y lista
para usarse; su aplicación a cifras reales de cada pantalla es trabajo
de Etapa 2, no de esta etapa.

## Pruebas realizadas

- `python manage.py check` → sin problemas.
- `python manage.py test` (suite completa, todas las apps incluida
  `apps/billing` del SaaS) → **1446 tests, `OK`, 0 fallos, 0 errores**.
  Dos trazas visibles en la salida son artefactos preexistentes de
  pruebas que simulan errores a propósito (un `RuntimeError` mockeado y
  un `PermissionError` de bloqueo de archivo en Windows durante la
  limpieza de un adjunto temporal) — ninguna relacionada con este
  cambio; el resultado final del suite es `OK`.
- Verificación de aislamiento a nivel de código: `layout_saas_admin.html`
  confirmado con `{% extends "base.html" %}` propio y
  `class="shell shell--saas"` — nunca extiende ni incluye
  `layout_app.html`; ningún otro template sobreescribe `extra_head`
  salvo los dos layouts (confirmado por grep), por lo que el `<link>`
  de fuentes/CSS nuevo del ERP nunca se carga en una página del SaaS.
- Verificación funcional: los 1446 tests incluyen numerosas
  aserciones de navegación/permisos/formularios/POST/redirects sobre
  páginas reales que extienden `layout_app.html` — todas siguen en
  verde, confirmando que el comportamiento no cambió.

**Pendiente explícito**: validación visual en navegador real — no
existe herramienta de captura de pantalla en este entorno (mismo
criterio ya declarado en todas las fases anteriores de este proyecto).
Esta verificación es de código/comportamiento, no visual.

## Responsive

- **Desktop** (>1024px): grid de 2 columnas sin cambios estructurales;
  sidebar en 228px expandido / 64px compacto (nuevo, toggle persistido
  en `localStorage`).
- **Off-canvas / navegación móvil** (≤1024px): mecanismo existente sin
  modificar (`.shell.sidebar-abierto`, `data-sidebar-toggle`/
  `data-sidebar-backdrop`) — confirmado que sigue funcionando porque no
  se tocó ninguna de sus reglas ni su JS; se agregó una regla para que,
  en este rango, el modo compacto se ignore visualmente (el panel
  off-canvas siempre muestra texto completo al abrirse, nunca solo
  íconos — el botón de ancho se oculta en este rango).
- **≤640px**: ajuste de `inset`/padding existente sin modificar.
- No se creó un breakpoint de "tablet" propio — el código real solo
  tiene un salto (1024px), consistente con lo ya documentado en
  `docs/erp-redesign-implementation-plan.md` §7; no se inventó uno.

## Regresiones

Ninguna encontrada. El SaaS (`.shell--saas`) no fue tocado ni directa
ni indirectamente — verificado por aislamiento de clase/archivo a nivel
de código y por los tests de `apps/billing` (incluidos en la corrida
completa) en verde.

## Problemas encontrados y corregidos durante la implementación

- Al usar `{% static %}` dentro del nuevo bloque `extra_head` de
  `layout_app.html`, faltaba `{% load static %}` en ese archivo (el
  `{% load %}` de `base.html` no se hereda entre archivos de plantilla
  distintos en Django) — corregido agregando el `{% load %}` al inicio
  de `layout_app.html`. Detectado y corregido antes de correr los
  tests, no llegó a producir un fallo real.

## Comparación con Stitch (composición, no valores exactos)

Sidebar claro agrupado en 8 dominios con barra de acento de 3px en el
ítem activo — coincide con la composición de las 13 pantallas maestras
de Stitch. Colores reales usados: los valores EXACTOS de
`docs/erp-redesign-design-system.md` (`#1D4E89` primario), nunca los
aproximados que Stitch renderizó (`#325f9b`/`#4d78b6`), tal como exigía
esta etapa. Tipografía real: IBM Plex Sans + IBM Plex Mono cargadas vía
Google Fonts (mismo mecanismo que Stitch usó, dependencia de red
documentada, con pila de reserva de sistema si no carga) — nunca la
sustitución que hizo la propia herramienta Stitch (Google Sans Mono/
Public Sans) al no tener IBM Plex Mono en su selector.

## Pendientes

- Modo Noche del ERP — no autorizado en esta etapa, preparado
  conceptualmente (mismo patrón de atributo+`localStorage` ya probado
  con el ancho del sidebar) pero no implementado.
- Función de servicio de recepción de Compras
  (`get_purchase_order_received_percent`) — registrada como pendiente,
  decisión funcional separada, no creada.
- Aplicación de `.u-cifra` a cifras reales — Etapa 2, pantalla por
  pantalla.
- Íconos de módulo — se incluyeron en el sidebar (necesarios para que
  el modo compacto sea legible); no se extendieron a ningún otro
  componente (KPI, badges, etc.) en esta etapa.
- Validación visual en navegador real — pendiente, sin herramienta
  disponible en este entorno.
