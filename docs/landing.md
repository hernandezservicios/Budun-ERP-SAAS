# Landing + Pricing (FASE 6)

Landing pública en `/` (vista `core.views.home`, plantilla
`apps/core/templates/core/landing.html`), reemplazando la página de
verificación técnica de FASE 1. Reutiliza exclusivamente el Design System
de FASE 5 (`static/css/base.css` + `static/css/design-system.css`); no
introduce una identidad visual nueva, solo unas pocas clases adicionales
de layout específicas de landing (`.landing-*`, `.precio-*`, `.acordeon`),
construidas con los mismos tokens.

## Secciones (en el orden pedido)
Hero (qué es / propuesta de valor) → Para quién es → Problemas que
resuelve → Qué incluye (módulos) → Cómo funciona → Ventajas → Seguridad →
Integración API/IA → Precios → FAQ → CTA final. Jerarquía semántica
correcta: un único `<h1>` (hero) y un `<h2>` por sección, cada `<section>`
con `aria-labelledby` apuntando a su propio encabezado.

## Precios: configurables, una sola fuente

`apps/core/pricing.py` define `PLANS` (lista de diccionarios); la
plantilla itera sobre esa lista con `{% for plan in planes %}` — **ningún
precio está hardcodeado en ninguna plantilla**. Verificado con un test
que escanea todas las plantillas del proyecto y falla si un monto de
`PLANS` aparece fuera de `pricing.py`/`landing.html`
(`PricingSectionTests.test_precios_no_estan_hardcodeados_en_otras_plantillas`).

**Importante — precios de ejemplo**: los montos ($0 / $29 / "Personalizado")
son placeholders ilustrativos. Todavía no hay ninguna decisión de negocio
real sobre precios, y PayPal no está integrado (FASE 16/17). Antes de un
lanzamiento real, el usuario debe revisar y decidir los valores finales
en `apps/core/pricing.py` (un solo archivo, fácil de editar).

Por qué un módulo de configuración y no un modelo de base de datos: FASE
17 — Billing SaaS construirá el modelo real de planes/suscripciones
conectado a PayPal, con campos que hoy no se pueden anticipar
correctamente (IDs de producto, ciclos de facturación, períodos de
prueba). Crear un modelo `Plan` ahora se quedaría obsoleto o exigiría una
migración de reemplazo en FASE 17; un módulo de configuración evita ese
desperdicio.

## Integración API/IA: presentación, no funcionalidad

La sección "Integración con agentes CRM IA" presenta el flujo
`ERP → API de Inventario → CRM/Agentes IA` únicamente como **capacidad
futura** (badge "Próximamente", texto explícito "Todavía no está
disponible"). No se implementó ninguna API real ni PayPal funcional en
esta fase — eso corresponde a FASE 15 (Roles + Audit + Inventory API) y
FASE 16/17 (PayPal Sandbox / Billing SaaS). Verificado con
`test_landing_no_implica_api_o_paypal_funcionales`.

## SEO básico
- `<title>` específico por página (ya existía desde FASE 1/5, la landing
  define el suyo).
- `<meta name="description">` y Open Graph (`og:type`, `og:title`,
  `og:description`) — ahora definidos como bloques override-ables en
  `templates/base.html`, disponibles para cualquier página futura, no
  solo la landing.
- Sin `og:image` todavía: no existe ningún activo de marca/logo real en
  el proyecto; agregarlo es una mejora pendiente cuando exista un logo.
- Headings correctos (un `<h1>`, `<h2>` por sección) y HTML semántico
  (`<section>`, `<footer>`, `aria-labelledby`).

## Accesibilidad
- FAQ implementado con `<details>/<summary>` nativos: accesible por
  teclado y con lectores de pantalla sin necesitar JavaScript.
- El diagrama de flujo API/IA usa `role="img"` con un `aria-label` que
  describe el flujo completo en una frase, en vez de exponer 3 nodos y 2
  flechas decorativas como contenido fragmentado a un lector de pantalla.
- Iconos decorativos (emoji) marcados `aria-hidden="true"`.
- Hereda skip link, foco visible y demás bases de accesibilidad de FASE 5.

## Responsive
Las cuadrículas de contenido (`landing-grid`, `landing-pasos`,
`precios-grid`) usan `grid-template-columns: repeat(auto-fit, minmax(...))`,
por lo que se adaptan de forma continua al ancho disponible sin
necesitar puntos de quiebre explícitos por dispositivo; se añadió un
ajuste puntual en `≤640px` (tamaño de título del hero, padding de
sección). Verificado por inspección de CSS, no con captura de pantalla
(esta herramienta no tiene navegador real disponible).

## No exceso de cards
Las secciones de contenido (audiencia, problemas, módulos, ventajas,
seguridad) usan un grid simple de ícono + título + texto, **sin** bordes
ni sombra de tarjeta — se reservó el componente Card (`.tarjeta`)
exclusivamente para Precios, donde es el patrón esperado. Instrucción
explícita del usuario respetada.

## Regresión verificada
- FASE 3 (`apps/tenants`, 16 tests) y FASE 4 (`apps/accounts`, 26 tests):
  sin cambios de lógica, siguen en verde.
- FASE 5 (`apps/core` Design System, 9 tests): sin cambios de lógica,
  siguen en verde.
- 60/60 tests totales (6 nuevos de `LandingPageTests`/`PricingSectionTests`
  más específicos que el conteo neto, ya que se reemplazó `HomePageTests`
  por `LandingPageTests` con más cobertura).

## Qué NO se construyó en esta fase (deliberado)
API de Inventario funcional, PayPal funcional, modelo de Billing/Plan en
base de datos, productos/inventario/ventas/POS/compras/gastos/reportes
reales. Todo eso corresponde a fases posteriores (8, 12–17).
