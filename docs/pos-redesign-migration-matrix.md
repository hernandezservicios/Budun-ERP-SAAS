# FASE 7 — POS LAB PROFUNDO — ETAPA 6 — MIGRATION MATRIX

Mapa archivo por archivo. Complementa
`docs/pos-redesign-implementation-plan.md`. Ningún archivo fue
modificado en esta etapa — es exclusivamente el mapa que una futura
implementación deberá seguir.

---

## Pantallas/componentes

| Pantalla/Componente | Archivo | Estado actual | Objetivo visual | Tipo de cambio | Funcionalidad afectada | Riesgo | Tests |
|---|---|---|---|---|---|---|---|
| Terminal — Búsqueda | `apps/pos/templates/pos/terminal.html` | Campo único `q`, sin `autofocus`, sin densidad Atlas | Ancho completo, `autofocus`, densidad compacta | VISUAL | Ninguna | Bajo | `test_terminal.py` |
| Terminal — Resultados | `apps/pos/templates/pos/terminal.html` | Fila inline sin `_campo.html`, sin `<label>` | Fila compacta, `_campo.html` real | VISUAL + UX (accesibilidad) | Ninguna | Bajo | `test_terminal.py` |
| Terminal — Carrito | `apps/pos/templates/pos/terminal.html` | Tabla estándar, sin `.u-cifra`/`.u-num` | Densidad compacta, `.u-cifra`/`.u-num`, objetivo táctil en "Quitar" | VISUAL | Ninguna | Bajo | `test_terminal.py` |
| Terminal — Cliente/Descuento | `apps/pos/templates/pos/terminal.html` | Grid inline `1fr 1fr`, no responsive | `.u-grid-2col` (o equivalente `.shell--pos`), apilado en tablet | VISUAL + RESPONSIVE | Ninguna | Bajo | `test_terminal.py` |
| Terminal — Totales | `apps/pos/templates/pos/terminal.html` | 4 KPIs visualmente iguales | Total destacado, `--texto-3xl` | VISUAL | Ninguna | Bajo | `test_terminal.py` |
| Terminal — Checkout | `apps/pos/templates/pos/terminal.html` | `flex` sin `flex-wrap` | `flex-wrap: wrap`, franja de cierre, objetivo táctil en botón de cobro | VISUAL + RESPONSIVE | Ninguna | Bajo | `test_terminal.py` |
| Terminal — Estados vacíos | `apps/pos/templates/pos/terminal.html` | Emoji (🛒) | Ícono SVG (mismo patrón ya aprobado en FASE 5) | VISUAL | Ninguna | Ninguno | N/A |
| Register List | `apps/pos/templates/pos/register_list.html` | Sin migrar a Atlas | Tarjetas/tabla Atlas | VISUAL | Ninguna | Bajo | `test_cash_sessions.py` |
| Session Open | `apps/pos/templates/pos/session_open.html` | Sin migrar | Tarjeta de formulario Atlas | VISUAL | Ninguna | Bajo | `test_cash_sessions.py` |
| Session Close | `apps/pos/templates/pos/session_close.html` | Sin migrar | Tarjeta + tabla de movimientos Atlas | VISUAL | Ninguna | Bajo | `test_cash_sessions.py` |
| Session Summary | `apps/pos/templates/pos/session_summary.html` | Sin migrar | KPIs + tabla Atlas | VISUAL | Ninguna | Bajo | `test_cash_sessions.py` |
| Cash Movement (entrada UI) | — (sin template) | Inexistente | **No incluido en Bloques 0-7** | FUNCIONAL (decisión #5) | Exposición de capacidad ya construida | Bajo-medio | `test_cash_sessions.py` (si se autoriza) |
| Receipt | `apps/sales/templates/sales/sale_receipt.html` | Extiende `base.html`, azul `#1d4ed8` | Rediseño visual dentro de la realidad HTML/print | VISUAL | Ninguna (cambio/vuelto excluido) | Bajo | `test_sales.py::test_recibo_via_http` |
| Collections Search | `apps/pos/templates/pos/collections_search.html` | Sin migrar | **No tocar — fuera de alcance** | — | — | — | — |
| Customer Collections | `apps/pos/templates/pos/customer_collections.html` | Ya migrado (FASE 5) | **No tocar — ya cerrado** | — | — | — | — |

---

## Infraestructura (CSS/JS/Shell)

| Archivo | Estado actual | Cambio propuesto | Tipo de cambio | Riesgo | Tests |
|---|---|---|---|---|---|
| `static/css/design-system-pos.css` | No existe | **Crear** (Bloque 0), namespace `.shell--pos` | INFRAESTRUCTURA | Muy bajo | Ninguno (sin lógica) |
| `templates/layout_app.html` | Carga `design-system-erp.css` para todo `.shell--erp` | Carga condicional de `design-system-pos.css` solo en pantallas POS; posible atributo/clase `.shell--pos` añadido | INFRAESTRUCTURA | Bajo | Suite completa (verificar que las 13 pantallas Atlas no-POS no se ven afectadas) |
| `static/js/ui.js` | Completo, sin funciones POS | **NO TOCAR** | — | — | — |
| `static/js/pos.js` | No existe | **No crear en Bloques 0-7** — candidato solo si Bloque 9 autoriza cálculo en vivo | — | — | — |
| `static/css/base.css` | Tokens raíz compartidos | **NO TOCAR** | — | — | — |
| `static/css/design-system.css` | Librería de componentes global | **NO TOCAR** | — | — | — |
| `static/css/design-system-erp.css` | Cerrado en FASE 5 | **NO TOCAR** | — | — | — |

---

## Backend (views/forms/services/urls) — todos "NO TOCAR" en Bloques 0-7

| Archivo | Estado | Nota |
|---|---|---|
| `apps/pos/views.py` | **NO TOCAR** (Bloques 0-7); Bloque 8 únicamente agrega `require_permission`, si se autoriza | Ninguna vista se reescribe, solo se añade una línea de verificación por vista en el Bloque 8 |
| `apps/pos/forms.py` | **NO TOCAR** | Ningún campo nuevo, ningún form nuevo en los Bloques 0-7 |
| `apps/pos/services.py` | **NO TOCAR** | La lógica de negocio no cambia por un rediseño visual |
| `apps/pos/urls.py` | **NO TOCAR** | Ninguna ruta nueva en los Bloques 0-7 |
| `apps/pos/models.py` | **NO TOCAR** | Ninguna migración en los Bloques 0-7 |
| `apps/sales/views.py` | **NO TOCAR** (Bloques 0-7); Bloque 8 únicamente | Igual criterio que `apps/pos/views.py` |
| `apps/sales/services.py` | **NO TOCAR** | Incluye `confirm_sale`, `checkout_sale`-adyacente — ningún bloque visual lo toca |
| `apps/sales/models.py` | **NO TOCAR** (Bloques 0-8); decisión #7 (cambio/vuelto) en Bloque 9 únicamente, si se autoriza | Migración de `Payment.amount_received`/`change_amount` es la única razón para tocar este archivo, y solo con autorización específica |
| `apps/approvals/services.py`, `apps/approvals/models.py` | **NO TOCAR** | Mecanismo ya completo (Etapa 5 §14) |
| `apps/permissions/services.py`, `apps/permissions/catalog.py` | **NO TOCAR** (Bloques 0-7); consultado, no modificado, en Bloque 8 | El catálogo ya tiene todos los códigos necesarios — Bloque 8 los usa, no los crea |
| `apps/inventory/services.py`, `apps/inventory/models.py` | **NO TOCAR** | Incluye `ensure_unit_available_for_sale` — decisión #3, fuera de Bloques 0-7 |
| `apps/customers/models.py`, `apps/customers/services.py` | **NO TOCAR** | Ninguna decisión pendiente los involucra directamente |

---

## Tests — ninguno se modifica salvo por aserción de texto literal

| Archivo | Estado | Nota |
|---|---|---|
| `apps/pos/tests/test_terminal.py` | **NO TOCAR** salvo aserciones de texto/clase HTML que cambien por el rediseño visual (mismo patrón ya usado y aprobado en FASE 5 — actualizar solo la aserción necesaria) | Nunca eliminar cobertura funcional |
| `apps/pos/tests/test_cash_sessions.py` | Igual criterio | — |
| `apps/pos/tests/test_collections.py` | **NO TOCAR** — fuera de alcance (Collections/Customer Collections no se rediseñan esta fase) | — |
| `apps/pos/tests/test_isolation.py`, `test_concurrency.py`, `test_performance.py` | **NO TOCAR** | Sin relación con cambios visuales |
| `apps/pos/tests/test_discount_authorization.py`, `test_credit_overage.py` | **NO TOCAR** | Mecanismo de `apps.approvals` no se modifica |
| `apps/sales/tests/*` | **NO TOCAR** salvo aserción de texto/clase en `test_sales.py::test_recibo_via_http` si el rediseño del recibo cambia HTML cubierto por esa aserción | — |
| `apps/permissions/tests/test_services.py`, `test_views.py` | **NO TOCAR** en Bloques 0-7; consultados como baseline antes del Bloque 8 | — |

---

## Resumen por tipo de cambio (Bloques 0-7, alcance de esta etapa)

- **VISUAL**: 8 pantallas + infraestructura CSS — la inmensa mayoría
  del trabajo real de implementación.
- **UX**: 1 corrección (labels reales en fila de alta rápida de
  producto).
- **RESPONSIVE**: 2 correcciones puntuales (grid Cliente/Descuento,
  filas de pago) — CSS puro, sin JS, sin cambio de comportamiento.
- **INFRAESTRUCTURA**: 1 archivo nuevo (`design-system-pos.css`) + 1
  cambio mínimo (`layout_app.html`).
- **FUNCIONAL, SEGURIDAD, IMPRESIÓN**: 0 en los Bloques 0-7 — reservados
  íntegramente a los Bloques 8-9, condicionados a autorización
  explícita e independiente por decisión.

**Archivos explícitamente "NO TOCAR" en toda la implementación de los
Bloques 0-7**: `apps/pos/views.py`, `apps/pos/forms.py`,
`apps/pos/services.py`, `apps/pos/urls.py`, `apps/pos/models.py`,
`apps/sales/views.py`, `apps/sales/services.py`, `apps/sales/models.py`,
`apps/approvals/*`, `apps/permissions/services.py`,
`apps/permissions/catalog.py`, `apps/inventory/services.py`,
`apps/inventory/models.py`, `apps/customers/*`, `static/css/base.css`,
`static/css/design-system.css`, `static/css/design-system-erp.css`,
`static/js/ui.js`, `apps/pos/templates/pos/collections_search.html`,
`apps/pos/templates/pos/customer_collections.html`.
