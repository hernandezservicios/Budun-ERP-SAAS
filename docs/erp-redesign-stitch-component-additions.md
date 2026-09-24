# DESIGN SYSTEM COMPONENT ADDITIONS (FASE 4)

Componentes que aparecieron como necesidad real durante la generación de
las pantallas maestras en Stitch y que no estaban en las 20 secciones
originales de `docs/erp-redesign-design-system.md` (FASE 2). Ninguno se
improvisó silenciosamente — cada uno se documenta aquí para tu revisión
antes de incorporarse formalmente al Design System.

---

## 1. Barra de progreso de recepción (Progress bar)

- **Necesidad**: la columna "Recepción" del listado de Compras necesita
  comunicar visualmente qué fracción de una orden de compra ya fue
  recibida — un dato real que el ERP ya calcula (`docs/erp-redesign-map.md`:
  "`PurchaseOrderItem` nunca guarda `received_quantity`/`pending_quantity`
  como campo: se calculan siempre agregando sobre `PurchaseReceiptItem`").
  Ya se había identificado como candidato en el Decision Log de FASE 3
  (Lab, decisión 6).
- **Pantalla donde aparece**: Compras — Escritorio (`1925f3f08c95454b9ddad749a8b56f43`),
  columna "Recepción" de la tabla de órdenes de compra.
- **Razón**: una fracción numérica sola ("7/10") es legible pero lenta de
  escanear en una lista larga; una barra de progreso permite comparar el
  avance de recepción entre varias órdenes de un vistazo, sin agregar
  ninguna acción ni estado nuevo — es una representación visual de un
  dato que ya existe, no una funcionalidad nueva.
- **Comportamiento**: de solo lectura, sin interacción — nunca un control
  editable (la recepción real se registra en la pantalla de detalle de la
  orden, no aquí). Color semántico: `success` al 100%, `warning` en
  progreso parcial, vacío/gris si la orden aún no tiene ninguna recepción
  registrada. Longitud proporcional al porcentaje calculado; fracción
  numérica siempre visible al lado, nunca solo el color.
- **Relación con componentes existentes**: usa el token `radius-pill` ya
  definido en el spec (§5 Radius, "toggle, barra de progreso") — el
  Design System de FASE 2 ya reservaba ese radio para este caso, aunque
  el componente en sí no se había diseñado todavía. Reutiliza los mismos
  4 colores semánticos de `Badges` (§13) para su relleno — no introduce
  ningún color nuevo.

**Estado**: pendiente de tu aprobación explícita para sumarse como
componente #18 del Design System (sección 3 del spec, "Componentes
base"). Hasta entonces, su uso queda limitado a esta pantalla de
referencia — no se escala a ninguna otra pantalla real sin esa
aprobación.

---

## 2. Campo oculto por permiso ("dato sensible")

- **Necesidad**: representar visualmente que un campo existe pero su
  valor está oculto por `can_view_sensitive_employee_data` — sin ocultar
  el campo por completo, que ocultaría también su existencia. Ya
  identificado y resuelto conceptualmente en el Decision Log de FASE 3
  (Lab, decisión 5); esta fase solo confirma que el patrón se sostiene al
  aplicarse en una pantalla Stitch completa.
- **Pantalla donde aparece**: Detalle de empleado — Escritorio
  (`506ef2dddb1444e49a489e2e478570e8`), campo "Salario" del panel Datos.
- **Razón**: es la única forma de que el diseño refleje honestamente una
  regla de permisos real del ERP (`docs/erp-redesign-map.md`, §10) sin
  inventar un valor ni mentir por omisión.
- **Comportamiento**: ícono de candado (línea, monocromo) + texto "Solo
  visible para el propietario" en `text-muted`, en el lugar exacto donde
  iría el valor real. Nunca un blur decorativo del número — un blur
  todavía sugiere que hay un valor "cerca", cuando la regla real es
  binaria (se ve completo o no se ve nada).
- **Relación con componentes existentes**: no es un componente nuevo en
  sí — es un ESTADO adicional del patrón "vista de detalle" (§17 del
  spec) para cualquier campo de definición. Se documenta aquí porque, a
  diferencia de la barra de progreso, no necesita aprobación por
  separado: ya se deriva directamente de una regla de permisos real
  documentada, no introduce color, radio ni spacing nuevo.

**Estado**: no requiere aprobación adicional — es una consecuencia
directa de una regla de permisos ya real y documentada, aplicada con los
tokens que el Design System ya tenía. Se añade como nota en la sección
17 (Detail views) del spec en la próxima revisión del documento.

---

## Componentes explorados y descartados de esta lista

Ninguno. Las 13 pantallas maestras se generaron usando exclusivamente
los 17 componentes ya validados en el Atlas ERP Design Lab (FASE 2) más
estos dos hallazgos — no se detectó ninguna otra necesidad de componente
nuevo durante la generación.
