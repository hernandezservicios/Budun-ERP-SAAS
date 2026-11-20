# FASE 7 — POS LAB PROFUNDO — ETAPA 4 — POS FINAL VISUAL DIRECTION + STITCH

Formaliza la dirección visual final del POS a partir de
`docs/pos-redesign-design-lab.md` (Etapa 3, aprobada) y produce
pantallas de referencia en Stitch. Cero código Django modificado.
Stitch es referencia visual, nunca fuente de verdad funcional — cada
pantalla se contrastó contra `docs/pos-redesign-discovery.md` y
`docs/pos-redesign-risk-map.md` antes de aceptarse.

---

## 1. Dirección final adoptada

**Síntesis, no selección arbitraria**: la dirección final no es
ninguna de las tres direcciones del Lab tomada en bloque — es una
combinación deliberada, justificada punto por punto en §2.

- **Base estructural**: Dirección B (POS Balanceado Atlas) — tarjetas
  (`.tarjeta`) para cada zona (Búsqueda/Resultados, Carrito, Cliente,
  Descuento, Totales, Checkout), mismo lenguaje visual que las 13
  pantallas Atlas ya cerradas en FASE 5.
- **Especialización de densidad y checkout**: de la Dirección A (POS
  Operativo Compacto) — el carrito usa la densidad de fila compacta de
  A, y el checkout se trata como una franja de cierre claramente
  separada, siempre alcanzable.
- **Especialización de objetivo táctil**: de la Dirección C (POS
  Táctil/Híbrido) — pero **acotada únicamente a los controles de alta
  frecuencia** (Agregar, Quitar, Confirmar y cobrar), no a toda la
  interfaz — evita el efecto "todo son botones gigantes" que la propia
  Etapa 3 advirtió como riesgo de C.

## 2. Fundamento de la dirección

- **Por qué B como base**: la instrucción de esta etapa es explícita
  — "NO crear un POS visualmente independiente del ERP" — y de las
  tres direcciones del Lab, B es la única diseñada explícitamente para
  "sentirse como Budun ERP Atlas + especialización POS" (§5 de
  `docs/pos-redesign-design-lab.md`). Tomarla como base minimiza el
  riesgo de fragmentar la identidad visual que el usuario ya cerró y
  aprobó en FASE 5.
- **Por qué se incorpora la densidad/checkout de A**: los principios
  de Etapa 2 (`docs/pos-redesign-design-system.md` §1) priorizan
  explícitamente velocidad, lectura inmediata y carrito siempre
  comprensible por encima de la consistencia con Atlas (prioridad 10
  de 11 en la lista) — la densidad de A responde directamente a esas
  prioridades sin romper el vocabulario visual de B (misma paleta,
  misma tipografía, mismos componentes, solo distinta densidad de
  fila).
- **Por qué se incorpora el objetivo táctil de C, pero acotado**: el
  POS se opera con mouse/teclado en la mayoría de los mostradores
  reales documentados (Etapa 1 no encontró evidencia de que el negocio
  opere exclusivamente en tablets), pero los controles de alta
  frecuencia (Agregar, Quitar, Cobrar) se benefician de un objetivo
  ampliado incluso con mouse/trackpad (mayor precisión, menos error) —
  aplicar la escala completa de C a toda la interfaz sería
  sobre-optimizar para un escenario (tablet pura) no confirmado como
  el único real.
- **Qué se descarta explícitamente y por qué**:
  - El estilo sin tarjetas de A (separadores simples en vez de
    `.tarjeta`) — descartado por completo: se aleja visualmente del
    resto del ERP Atlas más de lo que el principio "no independiente
    del ERP" permite.
  - La escala tipográfica/de espaciado ampliada de C en toda la
    interfaz (no solo en objetivos táctiles) — descartada: haría que
    el POS luciera desproporcionado frente al resto de pantallas
    administrativas que el mismo usuario opera a diario.
  - El grid Cliente/Descuento apilado siempre (incluso en escritorio),
    propuesto por C — descartado para escritorio (se usa 2 columnas
    real, `.u-grid-2col`), pero **sí adoptado para tablet/móvil** (ver
    §17), donde prevenir toques accidentales pesa más que la densidad.

## 3. Relación con Atlas

Se conserva sin excepción: tipografía (IBM Plex Sans + IBM Plex Mono
vía `.u-cifra`), paleta completa de color, iconografía SVG de línea,
lenguaje de botones (`.btn`/`.btn--primario`/`.btn--contorno`),
badges, campos (`.campo`/`_campo.html`), mensajes
(`django.contrib.messages`), estados, radios (`--radio-sm/md/lg`),
sombras (`--sombra-sm` únicamente), espaciado (`--espacio-*`),
tratamiento numérico (`.u-cifra`/`.u-num`). Ninguno de estos elementos
se reemplaza ni se duplica — mismo criterio ya aplicado en las 13
pantallas Atlas de FASE 5.

La especialización POS se concentra exclusivamente en: densidad
operativa del carrito, jerarquía del Total, composición de Terminal,
objetivo táctil de controles de alta frecuencia, y responsive
específico del grid Cliente/Descuento y las filas de pago.

## 4. `.shell--erp` + `.shell--pos`

Arquitectura formalizada (no implementada):

```
.shell--erp   → base/lenguaje Atlas ERP (heredado sin cambios)
    └── .shell--pos   → contexto POS (convivencia, no reemplazo)
            └── .pos-*   → componentes específicos POS (namespace obligatorio)
```

Sin contradicción encontrada durante esta etapa respecto a lo ya
definido en Etapa 2/3 — se confirma **convivencia** (`class="shell
shell--erp shell--pos"`), no reemplazo, porque el POS ya hereda
`.shell--erp` pasivamente hoy (sidebar/topbar Atlas, confirmado en
Etapa 1) y esa herencia se conserva.

## 5. Principios visuales

Los 11 de `docs/pos-redesign-design-system.md` §1, sin modificar. Se
reafirma el orden de prioridad usado para resolver los conflictos de
síntesis en §2: velocidad y carrito comprensible por encima de
consistencia estética pura, pero nunca por encima de "ausencia de
funcionalidad inventada" (principio 11, nunca subordinado a ningún
otro).

## 6. Densidad

- **Carrito**: densidad compacta (estilo A) — filas con `--espacio-2`
  vertical.
- **Búsqueda/resultados**: densidad compacta (estilo A).
- **Cliente/Descuento/Checkout**: densidad estándar Atlas (estilo B,
  dentro de `.tarjeta`).
- **Totales**: el Total rompe la densidad estándar deliberadamente
  (tipografía `--texto-3xl`, ver §11).

## 7. Terminal

Composición final: **Variante B de Etapa 3** (tarjetas apiladas,
identidad Atlas) como esqueleto, con dos ajustes de A: el carrito
recibe más ancho/prioridad visual que las demás tarjetas (nunca su
propio contenedor sin `.tarjeta`, solo mayor proporción del layout), y
el checkout se posiciona como cierre visual claro del flujo, sin
mezclarse con Cliente/Descuento en la misma franja.

Orden vertical/de zonas: Búsqueda → (Resultados + Carrito en paralelo,
carrito más ancho) → Cliente/Descuento (franja de 2 tarjetas) →
Totales → Checkout. Coincide exactamente con el flujo real de
`docs/pos-redesign-discovery.md` §2.1 — ningún paso agregado, quitado
ni reordenado.

## 8. Carrito

Columnas reales sin cambios: Producto (+ SKU + IMEI/serie truncado) →
Cantidad → Precio → Descuento → Impuesto → Total de línea → Quitar.
Densidad compacta (§6). Botón "Quitar" con objetivo táctil ampliado
(control de alta frecuencia, §2). Edición de línea **no incluida como
funcional** — sigue siendo `docs/pos-redesign-design-system.md` §7.8,
decisión **B**, no resuelta.

## 9. Cliente

`<select>` real + cliente actual/"Consumidor final". Campo "Buscar
cliente" no tratado como funcional (decisión **D**, sin cambios desde
Etapa 2/3).

## 10. Descuento

Sin cambios respecto a Etapa 3 §12 — UI de descuento distinguida del
mecanismo de `apps.approvals`, que permanece intacto.

## 11. Totales

Total en bloque separado dentro de la tarjeta de Totales,
`--texto-3xl`, color `--pos-color-primario`/`#4D78B6`, cifra
monoespaciada. Subtotal/Descuento/Impuesto en texto secundario más
pequeño. Moneda real del tenant (`sale.currency`), sin selector — la
doctrina de multi-moneda sigue sin implementarse.

## 12. Checkout

Franja de cierre, formset real de 2 filas de pago (`método` + `monto`)
con `flex-wrap: wrap` real (corrige el defecto de Etapa 1). Botón
"Confirmar y cobrar" de ancho completo, objetivo táctil ampliado
(control de alta frecuencia).

## 13. Pagos

4 métodos reales (`cash`/`card`/`transfer`/`other`), sin ninguno
inventado — confirmado de nuevo contra `PaymentMethod` real.

## 14. IMEI/Serial

Mismo tratamiento de Etapa 3 §16 — badge + campo `unit_identifier` con
`<label>` real, sin escaneo/lector físico/validación anticipada
inventados.

## 15. Caja

Mismo tratamiento de Etapa 3 §17 — Register List, Session Open,
Session Close, Session Summary con el mismo lenguaje visual
(badge/`.kpi`/`.tabla`), Cash Movement UI como punto de entrada
condicionado a confirmación previa (sin cambios de clasificación).

## 16. Receipt

`sale_receipt.html` sigue siendo HTML + `window.print()`, sin PDF
backend, sin integración fiscal — confirmado de nuevo. Tratamiento
visual: mismos datos reales (tenant, número, cliente, fecha, vendedor,
líneas con SKU/IMEI-serie, cantidad, precio, descuento, impuesto,
total, pagos, notas), Total destacado igual que en el Terminal.
Impresión térmica sigue como propuesta futura, no implementada.

## 17. Responsive

- **Desktop/Laptop**: Terminal completo como en §7, Cliente/Descuento
  en 2 columnas (`.u-grid-2col`, ya existente).
- **Tablet**: Cliente/Descuento se apilan (adopción del criterio de C,
  §2) — más seguro para uso táctil que forzar 2 columnas estrechas.
  Carrito con scroll contenido (`.tabla-envoltorio`).
- **Mobile**: todo apilado en una columna, filas de pago con
  `flex-wrap: wrap`, botón de cobro de ancho completo.

## 18. Touch

Objetivo táctil ampliado (44px mínimo) **solo** en controles de alta
frecuencia (Agregar, Quitar, Confirmar y cobrar) — el resto de la
interfaz usa la escala estándar de Atlas, evitando el "todo son
botones gigantes" que Etapa 3 marcó como riesgo de una adopción total
de C.

## 19. Keyboard

Orden de tabulación según el flujo real (§7), foco visible heredado de
`base.css`, `autofocus` candidato en el campo de búsqueda (atributo
HTML declarativo). **Sin shortcuts** — cualquier atajo de teclado
(`F2`/`F12`/etc.) que aparezca en las capturas de Stitch es una
invención de la herramienta, no una funcionalidad real (ver §21).

## 20. Accesibilidad

Sin cambios respecto a Etapa 2/3: labels reales (`_campo.html`), foco
visible, contraste heredado, iconos SVG (nunca emoji — corrige el
único hallazgo real de inconsistencia de Etapa 1/3).

## 21. Estados

Mismo mapeo de `docs/pos-redesign-design-system.md` §21, sin estados
nuevos.

## 22. Permisos

Sin resolver la brecha real (§19 de Etapa 1/`docs/pos-redesign-risk-map.md`
§1-2). Tratamiento visual únicamente: disponible / restringido
(`disabled` + tooltip) / pendiente de aprobación — mismo criterio de
Etapa 3 §23, reafirmado.

## 23. Decisiones pendientes

Mismas 10 de `docs/pos-redesign-design-lab.md` §26, sin resolver
ninguna en esta etapa. Se añade una nota: las capturas de Stitch de
esta etapa **no deben interpretarse como que alguna de estas 10
decisiones fue tomada** — donde Stitch mostró un dato o control
relacionado (cambio calculado, movimientos manuales de caja, un
supervisor de cierre), es composición visual de la herramienta, no una
resolución funcional (ver §21 más abajo, "Elementos inventados por
Stitch").

## 24. Qué queda fuera

Modo Noche (no se generó ninguna pantalla en el design system "Atlas —
Noche", deliberadamente — ver §25), POS operativo real sin tocar,
impresión térmica, PDF backend, edición de carrito, corrección de
permisos, cualquier nuevo método de pago.

## 25. Referencia Stitch

**Proyecto**: `Budun ERP — POS` (`projects/5272037951858947708`),
deliberadamente separado del proyecto `Budun ERP — Atlas` de FASE 4
para mantener el alcance de esta etapa identificable, pero reutilizando
literalmente el mismo Design System real de Atlas (`Atlas ERP`, LIGHT,
FIDELITY, primario `#4d78b6`/`#325f9b`, mismos tokens que
`docs/erp-redesign-design-system.md`) — recreado dentro de este
proyecto como `assets/3762514133482931348` porque la referencia
cruzada de un asset entre proyectos distintos no fue respetada por la
herramienta (ver limitación técnica abajo). **Nunca se usó ni se generó
ninguna pantalla con el design system "Atlas — Noche"** — coherente con
la prohibición permanente de Modo Noche.

**7 pantallas maestras generadas** (todas corregidas a la paleta Atlas
real tras la generación, ver limitación técnica):

| # | Pantalla | Dispositivo | Screen ID |
|---|---|---|---|
| 1 | Terminal POS | Escritorio | `bb9b9a4d5010457e82aefd239256dbe6` |
| 2 | Terminal POS | Móvil/táctil | `4d4fb70c1fcc4688a8ab417d4b1c2cd8` |
| 3 | Cajas registradoras (Register List) | Escritorio | `3e9b0a298b444e1a9a5065fb1df71a6d` |
| 4 | Abrir caja (Session Open) | Escritorio | `ed73444b41f74589a1510716e03eae1f` |
| 5 | Cerrar caja (Session Close) | Escritorio | `079f3093bd844bc1a28a41484a3c003e` |
| 6 | Resumen de sesión (Session Summary) | Escritorio | `47052083d08446749c955565b0478d54` |
| 7 | Recibo de venta (Receipt) | Escritorio | `dd17df858273438aa2a107a4ca957f5a` |

**Limitación técnica encontrada esta etapa** (nueva, no documentada en
fases anteriores): al generar la primera pantalla (Terminal escritorio)
pasando el `designSystem` como referencia al asset ya existente del
proyecto `Budun ERP — Atlas` (`assets/8315432074048865179`), la
herramienta **ignoró la referencia cruzada entre proyectos** y generó
su propio design system automático ("Atlas Dense Operations", paleta
no aprobada). Se corrigió creando el design system real dentro del
proyecto POS (`assets/3762514133482931348`, mismos valores exactos que
Atlas Día) y aplicándolo retroactivamente a cada pantalla con
`apply_design_system`. Las pantallas #3 a #7 ya generaron directamente
con la paleta correcta al referenciar el asset ya existente dentro del
mismo proyecto. Documentado como limitación de la herramienta, igual
que la desaturación de color de FIDELITY documentada en FASE 4 — nunca
un motivo para tratar el color de Stitch como fuente de verdad; la
fuente de verdad del color siempre es `docs/erp-redesign-design-system.md`.

**Elementos inventados por Stitch — NO representan funcionalidad ni
datos reales** (catalogados explícitamente, coherente con la regla
"Stitch es referencia visual, no fuente de verdad funcional"):

- **Atajos de teclado** (`[F2]`, `[F4]`, `[F8]`, `[F9]`, `[F12]`,
  `[Enter]`) en Terminal escritorio y en las pantallas de caja — el
  POS real no tiene ningún shortcut implementado (Etapa 1/3, §19 de
  este documento). Ignorar por completo en cualquier implementación.
- **Moneda MXN fija** — el sistema real usa la moneda configurada del
  tenant (`sale.currency`), nunca una moneda fija; la doctrina de
  multi-moneda ni siquiera está implementada (Etapa 1).
- **Datos fiscales de cliente** (RFC, "Distribuidora Metálica del
  Norte S.A.", cuenta B2B, términos de crédito visibles en el
  terminal) — el terminal real no muestra RFC/crédito, solo
  `display_name` (Etapa 3 §11).
- **Nombres/SKU de producto ficticios** ("Taladro Percutor Industrial
  18V XR", "Sensor Fotoeléctrico Omron E3Z", etc.) — datos de
  demostración visual únicamente, el catálogo real es el de cada
  tenant.
- **Ticket/folio numerado** (`#TK-2024-00892`, `#VTA-2024-00892`) — el
  formato real de numeración de venta es el de `DocumentSequence`
  (`Sale.number`), no verificado contra este formato específico; no
  asumir este patrón como real.
- **Ítems de sidebar inexistentes** ("Sesiones", "Arqueo", "Caja y
  Turnos" como grupo unificado, "Facturación CFDI") — el sidebar Atlas
  real agrupa exactamente "Punto de venta" con POS Terminal/Cobros/
  Cajas (`templates/layout_app.html`, FASE 5), sin esos ítems
  adicionales.
- **IVA 16% hardcodeado** — el sistema real usa `SaleItem.tax_rate`
  configurable por producto/tenant, nunca una tasa fija de país.
- **"Supervisor de cierre" y "sello criptográfico SHA-256"** en
  Session Summary — ningún campo de este tipo existe en `CashSession`
  real; invención total de Stitch.
- **Firmas de entrega/conformidad y QR de verificación** en el recibo
  — no existen en `sale_receipt.html` real ni se propone agregarlos.
- **Escaneo de código de barras con cámara** en Terminal móvil
  ("Cámara activa") — no existe ningún JS/integración de cámara en el
  POS real (Etapa 1 confirmó cero JS propio del POS).
- **Barra de navegación inferior móvil** ("Venta/Ticket/Clientes/
  Caja") — no existe esa navegación en el proyecto real; el POS usa el
  mismo sidebar/topbar Atlas que el resto del ERP.
- **Desglose completo de cambio con referencia SPEI** en el checkout —
  el vocabulario y el desglose exacto mostrado es invención de Stitch;
  la realidad funcional del cambio/vuelto sigue siendo la decisión
  pendiente de §23.10 (documentada en el recibo con la etiqueta
  "Pendiente de definición" tal como se instruyó explícitamente en el
  prompt de generación).

**Ningún elemento de esta lista debe trasladarse a una futura
implementación Django** — son composición visual de Stitch sobre datos
de demostración, nunca especificación funcional.

## 26. Criterios que deberá cumplir la futura implementación

Una futura implementación Django deberá poder compararse contra estas
7 pantallas y cumplir: misma jerarquía (Búsqueda→Carrito→Cliente→
Descuento→Totales→Checkout), misma estructura de tarjetas, mismos
componentes reales (nunca los inventados de §25), mismos estados
reales, densidad aproximada de carrito/búsqueda compacta con el resto
en densidad estándar Atlas, mismo tratamiento del Total (bloque
separado, `--texto-3xl`, color primario), misma relación Terminal/
Carrito (carrito con mayor proporción visual), misma lógica responsive
de §17, misma relación `.shell--erp`/`.shell--pos` de §4 — pero
siempre subordinada al código funcional real, nunca a lo que Stitch
dibujó de más.

---

## Confirmación de reglas absolutas respetadas

`git status --porcelain` (ver reporte final): sin cambios en `apps/`,
`templates/`, `static/`, modelos, vistas, forms, services, URLs,
permisos, migraciones ni tests. `manage.py check`: sin problemas. Todo
el trabajo de Stitch vive en la plataforma Stitch (proyecto
`projects/5272037951858947708`), fuera del repositorio — ningún
archivo generado por Stitch se descargó ni se copió al repositorio.
