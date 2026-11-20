# FASE 7 — POS LAB PROFUNDO — ETAPA 6 — PLAN DE IMPLEMENTACIÓN

Mapa de implementación, no autorización para programar. Cero código
modificado en esta etapa. Construido sobre las 5 etapas previas
(aprobadas) y verificación directa de código real esta etapa.

---

## 1. Objetivo

Definir cómo pasar del POS actual (funcional, sin rediseño Atlas) al
POS final aprobado (`docs/pos-redesign-final-direction.md`), de forma
incremental, aislada, reversible y verificable — sin regresión
funcional en ningún momento del proceso.

## 2. Alcance

Cubre exclusivamente las 8 pantallas/documentos reales del POS ya
inventariados (`docs/pos-redesign-discovery.md` §1): `terminal.html`,
`register_list.html`, `session_open.html`, `session_close.html`,
`session_summary.html`, `collections_search.html`,
`customer_collections.html` (ya migrado en FASE 5 — solo verificación
de no regresión, sin rediseño nuevo), `sale_receipt.html`. Ninguna
decisión funcional de las 10 de Etapa 5 se ejecuta en los Bloques 0-7
— solo entran en juego en los Bloques 8-9, y únicamente si el
propietario las autoriza explícitamente antes de empezar.

## 3. Arquitectura

```
.shell--erp                 → shell/base Atlas ERP (heredado, sin cambios)
    └── .shell--pos          → contexto POS (convivencia, nunca reemplazo)
            └── .pos-*        → componentes específicos POS (namespace obligatorio)
```

`.shell--erp` sigue siendo responsable de: shell general, sidebar,
topbar, navegación ERP, tokens Atlas (color/tipografía/radios/
sombras/spacing), iconografía, componentes compartidos (`.btn`,
`.tarjeta`, `.badge`, `.campo`, `.alerta`, `.tabla`, `.estado-vacio`,
`.kpi-grid`). `.shell--pos` es responsable exclusivamente de: densidad
POS (carrito/búsqueda compacta), composición de Terminal, objetivo
táctil ampliado en controles de alta frecuencia, responsive específico
del grid Cliente/Descuento y filas de pago. Ninguna regla de
`.shell--pos` duplica un token ya resuelto por `.shell--erp` — mismo
principio de sustitución de token ya usado por `design-system-erp.css`
sobre `design-system.css` en FASE 5.

## 4. Arquitectura CSS

**Recomendación**: nuevo archivo `static/css/design-system-pos.css`,
cargado en `layout_app.html` **solo** cuando la página pertenece al
contexto POS (mismo mecanismo condicional que hoy carga
`design-system-erp.css` vía `{% block extra_head %}`, nunca en todas
las páginas del ERP). Orden de imports en `<head>`: `base.css` →
`design-system.css` → `design-system-erp.css` → `design-system-pos.css`
(el más específico al final, gana por orden de cascada + especificidad
de selector `.shell--pos` sobre `.shell--erp`). Ninguna regla de
`design-system-pos.css` usa un selector menos específico que
`.shell--pos` — evita que una regla POS se filtre a las 13 pantallas
Atlas ya cerradas o al Super Admin SaaS.

**Prohibido modificar `base.css`** salvo que una necesidad
verdaderamente transversal (aplicable también a pantallas no-POS) se
demuestre y se apruebe por separado — ninguna de las especializaciones
identificadas en Etapa 2-4 (densidad de carrito, prominencia del
Total, touch targets de controles de alta frecuencia) es transversal;
todas son exclusivas del contexto POS.

**No contaminación verificada**: `.shell--saas` no comparte ningún
selector con `.shell--pos` (mismo principio de aislamiento ya probado
entre `.shell--erp`/`.shell--saas` en FASE 5); `design-system-pos.css`
nunca declara nada bajo `:root` ni bajo `.shell--erp` fuera de
`.shell--pos`.

## 5. Arquitectura JS

**Comportamiento POS que requeriría JS real** (de
`docs/pos-redesign-design-system.md` §24, reconfirmado): `autofocus`
en búsqueda no requiere JS (atributo HTML declarativo); cálculo de
cambio en vivo, edición de línea sin recarga, y validación de IMEI en
vivo **sí requerirían JS**, pero los tres están ligados a decisiones
funcionales no autorizadas en esta etapa (#7, #9, #3 de Etapa 5) — por
tanto **ningún JS nuevo se crea en los Bloques 0-7**.

**JS existente que debe preservarse sin cambios**: `static/js/ui.js`
completo (`initSidebar`, `initSidebarAnchoToggleErp`, `initDropdowns`,
`initToasts`, `initModals`, `initTabs`) — el POS ya lo consume
pasivamente vía `layout_app.html` y debe seguir haciéndolo sin
modificación.

**`static/js/pos.js`**: no se crea en esta etapa. Solo sería necesario
si el Bloque 9 autoriza explícitamente cálculo de cambio en vivo u
otra interacción de las marcadas como categoría C en Etapa 5 — se
documenta como candidato, nunca como parte del plan de los Bloques
0-7.

## 6. Templates reales — inventario y clasificación

| Template | Clasificación | Razón |
|---|---|---|
| `apps/pos/templates/pos/terminal.html` | **Modificar** | Pantalla principal del rediseño (Bloques 2-4) |
| `apps/pos/templates/pos/register_list.html` | **Modificar** | Rediseño visual (Bloque 5) |
| `apps/pos/templates/pos/session_open.html` | **Modificar** | Rediseño visual (Bloque 5) |
| `apps/pos/templates/pos/session_close.html` | **Modificar** | Rediseño visual (Bloque 5) |
| `apps/pos/templates/pos/session_summary.html` | **Modificar** | Rediseño visual (Bloque 5) |
| `apps/pos/templates/pos/collections_search.html` | **No tocar** | Fuera de alcance — parte de Cobros/CxC, no del terminal POS |
| `apps/pos/templates/pos/customer_collections.html` | **No tocar** | Ya migrado a Atlas en FASE 5 (Etapa 3A) — solo verificación de no regresión, nunca rediseño nuevo |
| `apps/sales/templates/sales/sale_receipt.html` | **Modificar** | Rediseño visual (Bloque 6), fuera de `apps.pos` pero parte del flujo POS |
| `templates/layout_app.html` | **Dependencia indirecta** | Solo si el Bloque 1 confirma que `.shell--pos` necesita un atributo/clase condicional nuevo en el `<div class="shell">` — cambio mínimo, nunca reescritura |
| `static/css/base.css` | **No tocar** | Ver §4 |
| `static/css/design-system.css` | **No tocar** | Librería compartida global — cualquier cambio aquí afecta las 13 pantallas Atlas y el Super Admin SaaS |
| `static/css/design-system-erp.css` | **No tocar** | Ya cerrado en FASE 5 — el POS solo lo consume, no lo modifica |
| `static/js/ui.js` | **No tocar** | Ver §5 |

---

## 7. Migration Matrix

Ver `docs/pos-redesign-migration-matrix.md` (documento separado,
completo).

## 8. Mapa de la Terminal

| Zona | HTML actual | CSS actual | JS actual | Backend relacionado | Cambio visual propuesto | Riesgo | Prueba |
|---|---|---|---|---|---|---|---|
| Búsqueda | `PosSearchForm`, campo único `q` | Compartido (`.campo`) | Ninguno | `services.search`→`inventory.search_catalog` | Ancho completo, `autofocus`, densidad Atlas | Bajo | `test_terminal.py` (búsqueda delega en inventory) |
| Resultados | Tabla + mini-formulario inline por fila | Compartido (`.tabla`), estilos inline en filas | Ninguno | `AddItemView`/`services.add_item_to_cart` | Fila compacta, `_campo.html` real (corrige ausencia de `<label>`) | Bajo — solo estructura HTML de presentación | `test_terminal.py` (agregar producto por cantidad/serializado) |
| Identificación (IMEI/serie) | Badge "Requiere IMEI/serie" + campo `unit_identifier` | Compartido (`.badge`) | Ninguno | `AddItemView`, búsqueda por `serial`/`imei_1`/`imei_2` | Badge + label real, sin cambio de lógica | Bajo | `test_terminal.py` (unidad serializada) |
| Carrito | Tabla de líneas + botón Quitar | Compartido (`.tabla`) | Ninguno | `RemoveItemView`/`services.remove_cart_item` | Densidad compacta, objetivo táctil ampliado en "Quitar" | Bajo | `test_terminal.py` (quitar línea recalcula totales) |
| Cliente | `<select>` + campo de búsqueda vestigial | Compartido (`.campo`), grid inline `1fr 1fr` | Ninguno | `SetCustomerView`/`services.set_cart_customer` | Tarjeta Atlas, buscador vestigial presentado tal cual (sin fingir funcionalidad) | Bajo | `test_terminal.py` (set cliente) |
| Descuento | Campos % / monto + bloque de autorizaciones | Compartido (`.campo`/`.alerta`), mismo grid inline | Ninguno | `SetGlobalDiscountView`/`apps.approvals` | Tarjeta Atlas, sin cambio de mecanismo | Bajo | `test_discount_authorization.py` |
| Totales | `.kpi-grid` de 4 KPIs iguales | Compartido (`.kpi`) | Ninguno | `sale.subtotal/discount_total/tax_total/total` (ya calculados) | Total en bloque separado, `--texto-3xl` | Bajo — solo CSS/estructura | `test_terminal.py` (totales recalculados) |
| Checkout | Formset de 2 filas de pago + botón | Compartido (`.campo`), `display:flex` sin `flex-wrap` | Ninguno | `CheckoutView`/`services.checkout_sale` | `flex-wrap: wrap` real, franja de cierre, objetivo táctil ampliado en botón de cobro | Bajo — CSS puro | `test_terminal.py` (checkout multipago) |
| Mensajes/errores | `django.contrib.messages` (toasts) | Compartido | `ui.js` (`initToasts`) | Excepciones reales (`InsufficientPaymentError`, etc.) | Sin cambios — mismo mecanismo | Ninguno | Cobertura ya existente |
| Estados vacíos | `.estado-vacio` con emoji | Compartido | Ninguno | N/A | Reemplazar emoji por ícono SVG (mismo patrón ya aplicado en `customer_collections.html`) | Ninguno — corrección de conformidad ya aprobada en FASE 5 | Ninguna prueba nueva necesaria (no es lógica) |

## 9. Carrito — qué se preserva

Cálculo de líneas (`_recalculate_item`), cantidades, descuentos,
impuestos, totales, IMEI/serie, eliminación — **sin ningún cambio de
lógica**. El rediseño toca únicamente densidad de fila y objetivo
táctil del botón "Quitar". La edición de línea (decisión #9 de Etapa
5) queda fuera de los Bloques 0-7 por completo — solo entraría en el
Bloque 9 si se autoriza explícitamente.

## 10. Checkout / Pagos

**Cambio visual seguro**: `flex-wrap: wrap` en filas de pago,
reorganización de la franja de checkout, objetivo táctil del botón
"Confirmar y cobrar". **Cambio funcional pendiente, no se toca en
Bloques 0-7**: persistencia de cambio/vuelto (decisión #7) — el
mensaje flash actual se conserva exactamente como está; el rediseño
visual solo reserva el espacio donde ese dato aparecería *si* se
autoriza en el Bloque 9.

## 11. Caja

| Superficie | Views | Forms | Services | Templates | Permisos | Tests |
|---|---|---|---|---|---|---|
| Register List | `CashRegisterListView` | — | — | `register_list.html` | `require_role(OWNER)` (sin cambios) | `test_cash_sessions.py` |
| Session Open | `CashSessionOpenView` | `OpenSessionForm` | `open_cash_session` | `session_open.html` | `cash.open` (ya verificado) | `test_cash_sessions.py` |
| Session Close | `CashSessionCloseView` | `CloseSessionForm` | `close_cash_session`/`get_expected_cash` | `session_close.html` | `cash.close` (ya verificado) | `test_cash_sessions.py` |
| Session Summary | `CashSessionSummaryView` | — | — | `session_summary.html` | **`cash.view` no verificado** (decisión #2, Bloque 8 únicamente) | `test_cash_sessions.py` |
| Cash Movement | `CashMovementCreateView` | `CashMovementForm` | `record_cash_movement` | **sin template** | `cash.move` (ya verificado) | `test_cash_sessions.py` |

**No se agrega ningún punto de entrada visual a Cash Movement en los
Bloques 0-7** (decisión #5, pendiente de autorización). **`ADJUSTMENT`
no se habilita** bajo ninguna circunstancia sin resolver primero la
decisión #1 (Bloque 8).

## 12. Receipt

`SaleReceiptView`/`sale_receipt.html` — se preservan datos (tenant,
número, cliente, fecha, vendedor, líneas, SKU, IMEI/serie, cantidad,
precio, descuento, impuesto, total, pagos, notas), cálculos,
impresión actual (`window.print()` + `@media print`). Cuatro
categorías explícitamente separadas, nunca mezcladas en un mismo
cambio: (a) rediseño visual — Bloque 6; (b) cambio/vuelto — decisión
#7, Bloque 9 si se autoriza; (c) impresión térmica — decisión #10,
fuera de los Bloques 0-9 salvo autorización y confirmación de
hardware; (d) PDF — fuera de alcance permanente, ya decidido y
cerrado.

## 13. Permisos

| Ruta/acción | Permiso catalogado | Enforcement actual | Cambio propuesto | Tipo | Riesgo | Tests |
|---|---|---|---|---|---|---|
| Terminal (agregar/quitar/cliente/descuento/cancelar/checkout) | `pos.use` | No verificado | Bloque 8 únicamente, si se autoriza | Seguridad | Ver Etapa 5 §4 (riesgo de regresión verificado como bajo) | `apps/pos/tests/` completo + `apps/permissions/tests/test_services.py`/`test_views.py` |
| `apps.sales` (crear/confirmar/cancelar venta, línea, pago, devolución) | `sales.*`/`payments.*`/`credit.*`/`credit_note.*` | No verificado | Bloque 8 únicamente, si se autoriza | Seguridad | Ver Etapa 5 §4 | `apps/sales/tests/` completo |
| `CashSessionSummaryView` | `cash.view` | No verificado | Bloque 8 únicamente, si se autoriza | Seguridad | Bajo (cambio de una vista) | `apps/pos/tests/test_cash_sessions.py` |
| Abrir/Cerrar/Mover caja | `cash.open`/`cash.close`/`cash.move` | **Ya verificado** | Ninguno | — | — | Cobertura ya existente |

**No se asume que porque `require_permission` existe debe aplicarse
automáticamente** — los Bloques 0-7 no tocan ningún permiso; el Bloque
8 es una implementación separada, explícitamente condicionada a
autorización expresa e independiente de todo lo visual.

## 14. Approvals

`apps.approvals` (descuento, crédito excedido) ya está completo y
probado (`docs/pos-redesign-functional-decisions.md` §14) — **no
requiere rediseño funcional en ningún bloque**. El único trabajo de
implementación relacionado es visual: que la tarjeta de Descuento y el
bloque de autorizaciones pendientes representen correctamente
`ApprovalRequest.Status` real (Bloque 3), sin tocar
`apps/approvals/services.py`/`models.py`.

## 15. IMEI / Serial

`apps/pos/views.py` (`AddItemView`), `apps/pos/forms.py`
(`PosAddItemForm.unit_identifier`), `apps/inventory/services.py`
(`search_catalog`), `apps/inventory/models.py` (`InventoryUnit`,
constraints de serial/IMEI1/IMEI2) — el rediseño visual (Bloque 2-3)
envuelve esta funcionalidad exactamente como existe hoy, sin tocar
ninguna validación, sin conectar `ensure_unit_available_for_sale`
(decisión #3, fuera de los Bloques 0-7). Cobertura: `test_terminal.py`
(unidad serializada), tests de `apps/inventory/tests/`.

## 16. Responsive

- **Grid Cliente/Descuento** (`terminal.html:125`,
  `grid-template-columns: 1fr 1fr` inline): **CSS puro + cambio mínimo
  de template** — sustituir el `style=""` inline por la clase
  `.u-grid-2col` ya existente en `design-system-erp.css` (o su
  equivalente bajo `.shell--pos` si el Bloque 1 decide namespacing
  propio). Sin JS, sin cambio de comportamiento funcional.
- **Filas de pago sin `flex-wrap`**: **CSS puro** — agregar
  `flex-wrap: wrap` a la regla ya existente. Sin JS, sin cambio
  funcional.

Ambos se ejecutan en el Bloque 2/4 respectivamente (parte del
rediseño visual de esas zonas), no como bloque separado — son
correcciones de presentación, no una categoría propia de riesgo.

## 17. Touch

| Control | Ubicación | Desktop | Tablet | Mobile |
|---|---|---|---|---|
| Botón "Agregar" (resultado de búsqueda) | Fila de resultado | Estándar Atlas | Ampliado (~44px) | Ampliado |
| Botón "Quitar" (línea de carrito) | Fila de carrito | Estándar Atlas | Ampliado | Ampliado |
| Botón "Confirmar y cobrar" | Franja de checkout | Estándar Atlas, ancho contenido | Ampliado, ancho completo | Ampliado, ancho completo |

Ningún otro control recibe objetivo ampliado — coherente con
`docs/pos-redesign-final-direction.md` §18 (evita "todo son botones
gigantes"). No se crean controles nuevos.

## 18. Test strategy

- **`apps/pos/tests/`** (71 tests, confirmados `OK` en Etapa 1): base
  de regresión obligatoria antes/después de cada bloque.
- **`apps/sales/tests/`**: base de regresión para checkout/confirm_sale
  (usado indirectamente por el POS).
- **`apps/permissions/tests/`** (`test_services.py`, `test_views.py`):
  relevante únicamente para el Bloque 8 — confirmar que
  `require_permission`/`PermissionRequiredMixin` siguen comportándose
  igual antes de aplicarlos a nuevas vistas.
- **Verificación visual**: sin herramienta de navegador/captura en este
  entorno (confirmado repetidamente en todas las fases de este
  proyecto) — la comparación contra las 7 pantallas de Stitch
  (`docs/pos-redesign-final-direction.md` §25) será por revisión de
  código/clases CSS aplicadas, nunca por captura de pantalla real.

## 19. Pruebas mínimas por bloque

Para cada bloque: **Antes** — `manage.py test apps.pos apps.sales` en
verde como baseline; **Durante** — ningún test nuevo hasta que el
bloque termine (evita falsos positivos a mitad de cambio); **Después**
— misma suite, mismo conteo de tests, sin ningún test modificado
(salvo que el bloque cambie un literal de HTML ya cubierto por una
aserción de texto, mismo patrón ya usado y aprobado en FASE 5 —
actualizar solo la aserción necesaria, nunca eliminar el test);
**Visual** — revisión manual de clases CSS aplicadas contra la
pantalla Stitch correspondiente; **Regresión** — suite completa
(`manage.py test`) antes de dar el bloque por cerrado.

## 20. Orden de implementación

- **Bloque 0 — Infraestructura POS aislada**: crear
  `static/css/design-system-pos.css` (vacío o con solo namespace base
  `.shell--pos {}`), decidir mecanismo de carga condicional en
  `layout_app.html`. Sin tocar ningún template de contenido.
- **Bloque 1 — Shell/contexto POS**: aplicar `.shell--pos` a las 8
  pantallas del alcance (§2), agregar el encabezado compacto de
  contexto (caja/cajero/sesión) si se decide (Etapa 3 §7.2).
- **Bloque 2 — Terminal visual**: búsqueda, resultados, identificación
  IMEI/serie, corrección de `_campo.html` en la fila de alta rápida,
  fix de responsive de la fila de búsqueda.
- **Bloque 3 — Cart + Customer + Discount + Totals**: densidad de
  carrito, tarjetas Cliente/Descuento con `.u-grid-2col`, bloque de
  Totales con Total destacado.
- **Bloque 4 — Checkout/Payment visual**: `flex-wrap` de filas de
  pago, franja de cierre, objetivo táctil del botón de cobro.
- **Bloque 5 — Cash screens**: Register List, Session Open/Close/
  Summary — rediseño visual, sin exponer Cash Movement.
- **Bloque 6 — Receipt**: rediseño visual dentro de la realidad
  HTML/`window.print()`, sin cambio/vuelto ni térmica.
- **Bloque 7 — Responsive/touch refinements**: verificación final de
  tablet/mobile en las 8 pantallas, ajustes finos si el análisis de
  código revela algo no cubierto por los Bloques 2-4.
- **Bloque 8 — Permisos funcionales**: **únicamente si fue autorizado
  explícitamente** — activar `require_permission` según §13.
- **Bloque 9 — Decisiones funcionales adicionales**: **únicamente las
  que el propietario autorice** de las 10 de Etapa 5 (#3, #4, #5b, #6,
  #7, #8, #9, #10) — cada una como su propio sub-bloque aislado, nunca
  agrupadas.

**Ningún bloque comienza con esta etapa.**

## 21. Criterios de rollback

| Bloque | Archivos modificados | Riesgo | Cómo detectar regresión | Cómo revertir | Qué no debe revertirse |
|---|---|---|---|---|---|
| 0 | `static/css/design-system-pos.css` (nuevo), `layout_app.html` (mínimo) | Muy bajo | `manage.py check`, carga visual de cualquier página POS | `git checkout` del archivo nuevo (nunca creado = nada que revertir) o revertir el diff mínimo de `layout_app.html` | Nada — bloque sin lógica |
| 1 | `layout_app.html`, 8 templates (clase `.shell--pos` añadida) | Bajo | Suite `apps.pos`/`apps.sales` en verde, sidebar/topbar siguen funcionando | Revertir el commit del bloque (cambio puramente aditivo de clase) | El resto de pantallas Atlas (`.shell--erp` sin `.shell--pos`) — no deben verse afectadas, verificar explícitamente |
| 2-6 | Templates + CSS POS específicos de cada bloque | Bajo-medio | Suite de tests del bloque + revisión visual de clases | Revertir el commit del bloque | Los bloques anteriores ya aceptados |
| 7 | CSS de responsive (dentro de `design-system-pos.css`) | Bajo | Revisión de clases en los 3 breakpoints | Revertir el commit | Bloques 0-6 |
| 8 | `apps/pos/views.py`, `apps/sales/views.py` (líneas `require_permission`) | Medio — puede bloquear un flujo de producción real no cubierto por tests | Suite completa + monitoreo de errores 403 en producción tras desplegar | Revertir el commit del bloque (elimina las líneas `require_permission` agregadas) | Ningún otro bloque — es completamente independiente de lo visual |
| 9 | Variable por decisión — ver §16 de `docs/pos-redesign-functional-decisions.md` | Variable, evaluado por decisión individual | Suite + tests nuevos específicos de la decisión | Revertir el commit de esa decisión específica, nunca un rollback agrupado de varias decisiones | Las demás decisiones del Bloque 9 ya aceptadas |

No se ejecuta ningún rollback automático — cada reversión es una
decisión humana explícita ante una regresión detectada.

## 22. Criterios de aceptación

Por bloque, los 6 criterios exigidos: **Funcional** (mismo
comportamiento observable, suite en verde, mismo conteo de tests);
**Visual** (coincide con la pantalla Stitch correspondiente, sin los
elementos inventados catalogados en `docs/pos-redesign-final-direction.md`
§25); **Responsive** (sin overflow horizontal conocido en los 4
breakpoints de `base.css`); **Seguridad** (ningún acceso se amplía
accidentalmente — especialmente crítico en el Bloque 8, donde el
criterio se invierte: el objetivo es *restringir*, verificar que no se
restrinja de más ni de menos que lo documentado en Etapa 5); **Tenant
isolation** (sin cambios — todo el POS ya usa `all_objects` filtrado
por tenant, ningún bloque visual lo toca); **Performance** (sin
consultas N+1 nuevas — el POS ya tiene `test_performance.py`
cubriendo esto, debe seguir en verde).

## 23. Riesgos

Se reafirman, sin eliminar ninguno, los riesgos ya documentados en
`docs/pos-redesign-design-lab.md` §6 y `docs/pos-redesign-risk-map.md`
— el hecho de que el diseño ya los haya abordado visualmente (ej. el
fix de `.u-grid-2col`) no los elimina del registro histórico hasta que
el código real los corrija y la suite lo confirme. Riesgo nuevo
identificado esta etapa: **mezclar categorías en un mismo commit** (ver
§24) — el mayor riesgo de proceso de todo el plan, dado el número de
bloques y la tentación de "aprovechar" un commit visual para deslizar
un cambio funcional pequeño.

## 24. Decisiones que no deben mezclarse

Visual / UX / Funcional / Seguridad / Impresión / Hardware — cada
bloque de §20 pertenece a una sola categoría (Bloques 0-7 = Visual/UX
puro; Bloque 8 = Seguridad puro; Bloque 9 = Funcional, una decisión a
la vez, nunca agrupadas; impresión térmica = Hardware, condicionada,
fuera de todos los bloques hasta confirmación). Ningún commit de un
bloque visual toca `views.py`/`services.py`/`forms.py`/`models.py` —
si durante la implementación real de un bloque visual se descubre que
es imposible sin tocar uno de esos archivos, el bloque se detiene y se
reclasifica antes de continuar, nunca se fuerza el cambio funcional
dentro del commit visual.

## 25. Relación con Stitch

**Proyecto**: `Budun ERP — POS` (`projects/5272037951858947708`).
**Pantallas maestras**: las 7 de `docs/pos-redesign-final-direction.md`
§25 (Terminal escritorio/móvil, Register List, Session Open/Close/
Summary, Receipt). **Design System utilizado**: `Atlas ERP`
(`assets/3762514133482931348` dentro de ese proyecto), mismos valores
exactos que `docs/erp-redesign-design-system.md` — nunca "Atlas —
Noche". **Elementos inventados por Stitch, descartados explícitamente,
prohibidos en cualquier implementación**: MXN como moneda fija, IVA
16% hardcodeado, RFC/datos fiscales de cliente, atajos de teclado
(`F2`/`F4`/`F8`/`F9`/`F12`), sello criptográfico SHA-256, escaneo por
cámara, navegación inferior móvil ficticia, ítems de sidebar
inexistentes ("Sesiones", "Arqueo" como grupo separado, "Facturación
CFDI"), firmas de entrega/conformidad, número de ticket con formato no
verificado. **Qué referencia sí debe implementarse**: la composición
estructural (zonas, jerarquía, densidad, prominencia del Total,
ubicación de tarjetas), nunca el contenido de ejemplo ni los campos
inventados.

---

## Cero cambios funcionales — confirmación

Este documento y `docs/pos-redesign-migration-matrix.md` son el único
resultado de esta etapa. Ver reporte final para la verificación de
`git status --porcelain` y `manage.py check`.
