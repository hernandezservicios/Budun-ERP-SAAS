# Design System (FASE 5)

Sistema de diseño reutilizable para todo el ERP: tokens, layout (shell
autenticado) y 19 componentes. Sobrio, profesional, azul/verde +
neutrales, sin Django Admin como UI principal, sin colecciones de
tarjetas como patrón dominante del dashboard (eso se decide en FASE 7).

## Dónde vive

| Qué | Archivo |
|---|---|
| Tokens (color, tipografía, espaciado, sombras, radios, breakpoints) | `static/css/base.css` (`:root`) |
| Layout del shell + todos los componentes | `static/css/design-system.css` |
| JavaScript ligero (sidebar, dropdown, modal, tabs, toasts) | `static/js/ui.js` |
| Shell del documento (doctype, navbar público, toasts) | `templates/base.html` |
| Shell autenticado (sidebar + navbar interno) | `templates/layout_app.html` |
| Página de referencia (todos los componentes con datos de ejemplo) | `/estilo/` → `apps/core/templates/core/design_system.html` |

## Paleta y contraste (WCAG AA)

Azul y verde como identidad, con neutrales; rojo/ámbar solo para estados
semánticos (advertencia/peligro), tal como exige `docs/ui-ux.md`. Se
verificaron manualmente (fórmula de luminancia relativa WCAG 2.x) los
pares de color realmente usados como texto:

| Par | Contraste calculado | Uso |
|---|---:|---|
| `--color-azul-700` (#1d4ed8) sobre blanco | **6.71:1** | Enlaces, texto de marca, primario |
| `--color-verde-700` (#15803d) sobre blanco | **5.02:1** | Texto secundario/éxito |
| `--gris-500` (#64748b) sobre blanco | **4.76:1** | Texto tenue (ayuda, descripciones) |
| `--color-advertencia-800` sobre `--color-advertencia-100` | **6.37:1** | Badge/alerta de advertencia |

Los pares peligro-800/peligro-100 y verde-800/verde-100 siguen el mismo
patrón (tono "800" de texto sobre "100" de fondo dentro de la misma
familia), que es la combinación estándar usada en sistemas de diseño
ampliamente auditados por accesibilidad. Todos superan el mínimo AA de
4.5:1 para texto normal.

## Layout — shell autenticado

`templates/layout_app.html` (usa `templates/base.html` como shell del
documento):

- **Sidebar**: navegación principal, colapsable en tablet/móvil (≤1024px)
  como panel off-canvas con fondo semitransparente (`.sidebar__respaldo`)
  y botón `☰` en el Navbar para abrirla/cerrarla. Actualmente solo lista
  "Mi perfil" — el único destino real que existe; los módulos de negocio
  (FASE 8+) añadirán sus propios enlaces según se construyan, sin enlaces
  "fantasma" a páginas que todavía no existen.
- **Navbar**: barra superior fija con botón de sidebar (móvil), marca y
  menú de usuario (dropdown).
- **Header de página** (`.encabezado-pagina`): título + descripción +
  acciones, dentro del área de contenido — distinto del Navbar.
- Páginas públicas (home, login, registro, recuperación de contraseña,
  onboarding) usan un layout más simple (`.auth-card`, sin sidebar) desde
  `base.html` directamente: no tiene sentido mostrar navegación interna
  antes de que exista sesión o tenant.

### Responsive
Dos breakpoints reales: **≤1024px** (tablet y móvil: sidebar colapsa a
off-canvas) y **≤640px** (móvil: el panel ocupa más ancho de pantalla,
paddings reducidos). Desktop y laptop comparten el layout expandido
(>1024px) porque no hay ninguna diferencia de contenido real entre ambos
todavía que justifique un tercer breakpoint; se documenta así en vez de
simular una granularidad que no existe.

## Componentes (19)

Layout, Sidebar, Navbar, Header de página, Botones, Inputs, Selects,
Tablas, Cards, Badges, Alerts, Modales, Dropdowns, Paginación,
Breadcrumbs, Tabs, Toasts, Empty states, Loading states (spinner +
skeleton) y Error states (404/500 + patrón inline). Ver todos en vivo en
`/estilo/`.

Notas de implementación:
- **Modales**: usan el elemento nativo `<dialog>` — foco atrapado dentro
  del modal y cierre con `Escape` son gratis (accesibilidad nativa del
  navegador), `ui.js` solo conecta los botones que abren/cierran.
- **Tabs**: patrón ARIA completo (`role="tablist"`/`"tab"`/`"tabpanel"`,
  `aria-selected`, `tabindex` gestionado) con navegación por flechas de
  teclado.
- **Toasts**: los mensajes de `django.contrib.messages` ahora se
  renderizan automáticamente como toasts (antes, en FASE 4, era una lista
  inline); se autodescartan a los 6s o con el botón de cerrar. Un filtro
  de plantilla (`apps/core/templatetags/ui_extras.py`) traduce las
  etiquetas de Django (`success`, `error`, `warning`, `info`) a las
  variantes en español del componente.
- **Paginación**: componente puramente presentacional por ahora (no hay
  todavía ninguna lista real paginada); queda lista para conectarse al
  `Paginator` de Django cuando FASE 8+ lo necesite.
- **Accesibilidad transversal**: skip link (`.enlace-saltar`) en todo
  documento, foco visible (`:focus-visible`) en todos los elementos
  interactivos, `prefers-reduced-motion` respetado, `aria-label` en todos
  los botones de solo-ícono.

## Error states (404 / 500)

`templates/404.html` extiende `base.html` normalmente (Django SÍ pasa
`request` al renderizar 404, así que tiene acceso a `messages`,
`request.user`, etc.). `templates/500.html` es **deliberadamente
autocontenido** y no extiende `base.html`: Django renderiza la plantilla
500 sin `RequestContext` en producción (sin `request`, sin
`messages`), así que cualquier dependencia de esas variables rompería la
página de error justo cuando más se necesita que funcione. Verificado con
`ErrorPagesTests` en `apps/core/tests.py`.

## Bug encontrado y corregido durante esta fase

`layout_app.html` usaba `{{ request.user.get_full_name|default:request.user.email }}`
para mostrar el nombre en el menú de usuario. Con un visitante anónimo
(la página `/estilo/` es pública a propósito, para poder verificarla sin
iniciar sesión), `request.user.email` no existe en `AnonymousUser`, y a
diferencia de una variable simple, un **argumento** de filtro que falla
al resolverse por completo hace que Django lance `VariableDoesNotExist` y
rompa el render (no se sustituye silenciosamente por vacío, como sí
ocurre con la variable principal). Se corrigió con
`{% firstof request.user.get_full_name request.user.email "Invitado" %}`,
que sí tolera fallos de resolución en cada candidato. Detectado por
`DesignSystemPageTests.test_modal_usa_dialog_nativo_accesible` (fallaba
antes de la corrección) y confirmado con el resto de la suite.

## Qué NO se construyó en esta fase (deliberado)
Productos, inventario, ventas, POS, compras, gastos, reportes, API de
Inventario, PayPal, Billing — todo eso corresponde a fases posteriores.
El componente "Cards" existe en el sistema, pero, siguiendo la
instrucción explícita del usuario, no se usó como patrón dominante en
ninguna página (el dashboard real llega en FASE 7 y decidirá su propio
layout de KPIs).
