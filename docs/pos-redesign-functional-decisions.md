# FASE 7 — POS LAB PROFUNDO — ETAPA 5 — POS DECISIONES FUNCIONALES

## 1. Objetivo

Resolver, clasificar y documentar las 10 decisiones funcionales
pendientes acumuladas en Etapas 1-4, para que una futura etapa de
implementación no tenga que improvisar decisiones de negocio, UX,
seguridad o impresión sobre la marcha. Cero código modificado en esta
etapa — es exclusivamente análisis y documentación.

## 2. Fuentes

`docs/pos-redesign-discovery.md`, `docs/pos-redesign-risk-map.md`
(fuente original de las 8 primeras decisiones), `docs/pos-redesign-design-system.md`
§26 (consolida las 10, agrega 2 nuevas), `docs/pos-redesign-design-lab.md`
§26, `docs/pos-redesign-final-direction.md` §23, más verificación
directa de código real esta etapa: `apps/permissions/services.py`
(`has_permission`, `require_permission`, `PermissionRequiredMixin`),
`apps/permissions/catalog.py`, `apps/approvals/services.py`/`models.py`,
`apps/pos/tests/_helpers.py`, `apps/sales/tests/_helpers.py`.

## 3. Las 10 decisiones (recuperadas íntegras, ninguna perdida, ninguna agregada)

1. Brecha de autorización real en `apps.pos`/`apps.sales`.
2. `cash.view` no aplicado en `CashSessionSummaryView`.
3. Validación de disponibilidad de stock/unidad al agregar al carrito.
4. Cierre de caja por denominaciones.
5. Movimiento manual de caja y tipo `adjustment` sin UI.
6. Devolución de mercancía accesible desde el flujo del POS.
7. Persistencia de `amount_received`/`change_amount` y su reflejo en el recibo.
8. Integración de `TaxCode`/`SaleItemTax` al POS.
9. Edición de cantidad de una línea ya agregada al carrito.
10. Impresión térmica 58/80mm.

---

## 4. Permisos (decisiones #1 y #2)

**Verificación adicional de código real esta etapa** (más allá de lo ya
documentado en Etapa 1): `apps/permissions/services.py` ya tiene
construido **todo el mecanismo necesario** para cerrar esta brecha —
`has_permission(tenant, user, code)` (línea 37-61: jerarquía
superusuario/OWNER → `UserPermissionOverride` → `RolePermission` →
`DEFAULT_ROLE_PERMISSIONS` del catálogo), `require_permission(request,
code)` (línea 64-75, lanza `PermissionDenied`/403), y un
**`PermissionRequiredMixin` ya escrito y listo para usar** (línea
78-85, `permission_code = "..."` declarativo) que **ninguna vista de
`apps.pos`/`apps.sales` usa todavía** — solo 3 vistas de caja llaman a
`require_permission` directamente, sin usar el mixin.

**Hallazgo nuevo — riesgo de regresión de tests, verificado, no
estimado**: `apps/pos/tests/_helpers.py:28,34` crea el fixture del
cajero con `Membership.Role.CASHIER` (línea 34) — rol que **ya tiene
`pos.use`, `cash.*`, `sales.create`, `sales.view` en
`DEFAULT_ROLE_PERMISSIONS`** por defecto. `apps/sales/tests/_helpers.py:43`
y los fixtures de `test_concurrency.py`/`test_isolation.py` usan
exclusivamente `Membership.Role.OWNER`, que `has_permission` autoriza
siempre sin consultar el catálogo. **Conclusión verificada**: aplicar
`require_permission`/`PermissionRequiredMixin` a las vistas señaladas
en `docs/pos-redesign-risk-map.md` §1-2 tiene **riesgo real de
regresión de test cercano a cero** — ningún fixture de test conocido
quedaría bloqueado. Esto reduce sustancialmente la incertidumbre técnica
de la decisión #1, aunque no la convierte en un problema puramente
técnico.

**Clasificación**: **D — decisión de seguridad/permisos** (ambas
#1 y #2). No se resuelve como "simple UX" — es una decisión de
producto sobre si el sistema debe empezar a rechazar operaciones que
hoy silenciosamente permite. La construcción técnica ya existe
(mecanismo probado en las 3 vistas de caja); lo que falta no es
diseño técnico, es **autorización explícita del propietario** para
activar la verificación en las rutas restantes.

**Recomendación** (sin implementar): activar `require_permission`
usando los códigos ya definidos en el catálogo (`pos.use` en el
terminal, `sales.create`/`update`/`cancel`/`refund` y
`payments.create`/`reverse`/`credit.*`/`credit_note.*` en
`apps/sales/views.py`, `cash.view` en `CashSessionSummaryView`) — no
requiere inventar ningún código de permiso nuevo, todos ya existen en
`PERMISSION_CATALOG`. Requiere aprobación explícita antes de ejecutar,
más una verificación puntual de que ningún flujo de producción real
(fuera de los tests) dependa hoy de la ausencia de este control.

---

## 5. Carrito (decisión #9 — edición de línea)

**Código real verificado** (reconfirmado, sin cambios respecto a Etapa
1/3): agregar un producto crea una `SaleItem` vía `add_sale_item`;
quitar una línea la borra vía `remove_sale_item`; **no existe ningún
endpoint de edición** de una línea ya creada — ni de cantidad, ni de
precio, ni de descuento. El único camino real hoy para "corregir" una
línea es quitarla y volver a agregarla con los valores correctos.

- **Opción 1 (no permite edición)**: es el comportamiento actual,
  confirmado.
- **Opción 2 (edición indirecta)**: no existe — quitar+re-agregar no
  es edición, es dos operaciones distintas sobre dos `SaleItem`
  diferentes (la línea original se borra, no se modifica).
- **Opción 3 (lógica reutilizable)**: `_recalculate_item`/
  `recalculate_document_totals` (`apps/sales/services.py`) ya
  recalculan una línea/documento a partir de cantidad/descuento — esta
  lógica **sí sería reutilizable** si se construyera un endpoint de
  edición, pero hoy no está expuesta para actualizar una línea
  existente, solo para calcularla al crearla.

**Clasificación**: **B — requiere decisión del propietario** (¿el
flujo actual "quitar y re-agregar" es aceptable operativamente, o el
negocio necesita edición directa?) + **C — requiere diseño técnico
posterior** si la respuesta es sí (nuevo endpoint `UpdateItemView`,
reutilizando `_recalculate_item` ya existente, pero no construido).
**No se implementa ninguna opción en esta etapa.**

---

## 6. Checkout (contexto para decisión #7, sin decisión nueva)

Confirmado de nuevo: el checkout real (`CheckoutView.post` +
`services.checkout_sale`) no tiene ninguna decisión pendiente en su
lógica de validación de pago, descuento o crédito — esos mecanismos
(`InsufficientPaymentError`, `DiscountRequiresApproval`,
`CreditOverageRequiresApproval`) están completos y probados (ver §14).
La única decisión pendiente del checkout es el cambio/vuelto (§7).

---

## 7. Cambio / vuelto (decisión #7)

**Comportamiento actual, documentado exactamente**:
- **Dónde se calcula**: `CheckoutView.post` (`apps/pos/views.py`),
  variables locales `total_recibido`/`exceso`/`cambio` — nunca en
  `apps.sales`.
- **Cuándo se calcula**: después de que el cajero envía el formset de
  pago, antes de llamar a `checkout_sale`.
- **Cómo se muestra**: únicamente como mensaje flash de Django tras la
  confirmación ("Venta {number} cobrada. Cambio a entregar: {cambio}.").
- **Si se persiste**: no. `Payment` no tiene campos `amount_received`/
  `change_amount`.
- **Si llega al recibo**: no. `sale_receipt.html` no lo muestra.
- **Si puede perderse después del redirect**: sí — el mensaje flash es
  de un solo uso (patrón estándar de Django messages); si el cajero
  recarga la página del recibo o navega antes de leerlo, el dato del
  cambio ya no es recuperable desde ningún lugar del sistema.
- **Pagos múltiples**: el cambio se resta del último pago en efectivo
  indicado en el formset (`apps/pos/views.py`, iteración en reversa);
  si el excedente no cabe en ningún pago en efectivo, se rechaza el
  checkout completo antes de confirmar nada.
- **Pagos superiores al total sin efectivo** (ej. solo tarjeta/
  transferencia por más del total): el propio código rechaza esto
  explícitamente ("El cambio solo puede entregarse en efectivo, ajusta
  los montos") — no hay forma de generar cambio sin un pago en
  efectivo.

**Clasificación**: **B — requiere decisión del propietario** (¿el
negocio necesita conservar el cambio como dato de auditoría/recibo, o
el mensaje flash actual es suficiente?) + **C — requiere diseño
técnico** si la respuesta es persistirlo (migración de `Payment`,
poblarlo en `checkout_sale`, mostrarlo en el recibo). **No se decide
por el agente** — es una regla comercial sobre qué debe documentar un
comprobante de venta, fuera del alcance de esta etapa de análisis.

---

## 8. Impresión (decisión #10 — térmica)

**Código real verificado**: `sale_receipt.html` usa `window.print()` +
`@media print` con `max-width: 800px`, diseño de hoja carta/A4 estándar
— sin ningún CSS ni vista alternativa para impresoras térmicas
58mm/80mm. Sin dependencias de impresión instaladas (ni `reportlab` ni
`weasyprint` ni controladores de hardware).

Opciones evaluadas (sin implementar ninguna):
- **A — Mantener impresión estándar**: viable si ningún tenant real
  usa hardware térmico hoy; costo cero, pero no resuelve el caso de
  quien sí lo use.
- **B — Crear futura variante térmica (CSS alternativo)**: técnicamente
  acotado (una hoja de estilo `@media print` adicional con ancho fijo),
  pero requiere decidir cómo el usuario la selecciona (¿detección
  automática, poco fiable vía CSS; o una URL/vista explícita
  "Recibo térmico", que ya sería un cambio funcional, no solo visual?).
- **C — Arquitectura de impresión dedicada** (servicio de impresión
  directo a la impresora térmica, sin pasar por el diálogo del
  navegador): fuera de alcance de una aplicación web estándar sin
  hardware/driver conocido — no hay evidencia en el código de que el
  proyecto tenga o planee esa integración.
- **D — Decisión de hardware**: cuál(es) impresora(s)/ancho(s) reales
  usa o usará el negocio no está documentado en ningún lugar del
  repositorio — información que el agente no puede inventar.

**Clasificación**: **E — requiere decisión de impresión/dispositivo**,
condicionada a **B — decisión del propietario** sobre si existe
hardware térmico real en producción. Sin esa información, la opción
recomendable por defecto es **A (mantener el estándar actual)** hasta
que se confirme una necesidad real — no se recomienda construir una
variante térmica especulativa.

---

## 9. PDF y recibo (contexto, no una de las 10, reafirmación)

Confirmado explícitamente, sin ambigüedad: el recibo es y seguirá
siendo HTML + impresión de navegador. No existe PDF backend, no hay
dependencia de PDF aprobada (`apps/sales/models.py` documenta esta
decisión explícitamente en su docstring — instalar una librería de PDF
requeriría decisión explícita separada del usuario, no forma parte de
ninguna de las 10 decisiones pendientes de esta etapa porque **ya fue
decidido y cerrado**: PDF queda fuera). No se reabre esta decisión
aquí.

---

## 10. Responsive del Terminal (no es una de las 10 — ya resuelto en Etapa 3/4, reconfirmado)

Los dos riesgos reales (`grid-template-columns: 1fr 1fr` inline sin
colapsar, filas de pago sin `flex-wrap`) **no requieren decisión del
propietario** — son correcciones puramente técnicas ya especificadas en
`docs/pos-redesign-final-direction.md` §17: aplicar `.u-grid-2col`
(clase ya existente y probada desde FASE 5) y agregar `flex-wrap: wrap`.
**Clasificación: A — puede resolverse con la realidad actual**, sin
cambio estructural de template más allá de sustituir un `style=""`
inline por una clase ya existente, y sin cambio de comportamiento
funcional. No implementado en esta etapa (solo confirmado su estado).

---

## 11. Touch targets (no es una de las 10 — ya resuelto en Etapa 4, reconfirmado)

`docs/pos-redesign-final-direction.md` §2/§18 ya define exactamente
qué controles: Agregar, Quitar, Confirmar y cobrar (controles de alta
frecuencia), objetivo mínimo ~44px, **nunca** aplicado a toda la
interfaz. Es una decisión de diseño ya tomada, no pendiente. Se
reconfirma aquí sin cambios: desktop/laptop no lo requieren
estrictamente (uso con mouse), tablet/mobile sí se benefician
directamente.

---

## 12. Keyboard / atajos (no es una de las 10 — confirmación de descarte)

Reconfirmado explícitamente: **no existen shortcuts POS reales en el
código** (verificado por Etapa 1, `terminal.html` no tiene ningún
listener de teclado más allá del comportamiento nativo del navegador).
Todo atajo (`F2`/`F4`/`F8`/`F9`/`F12`) que aparece en las capturas de
Stitch de Etapa 4 es invención de la herramienta, ya descartada
explícitamente en `docs/pos-redesign-final-direction.md` §21/§25. Si en
el futuro se considera deseable introducir shortcuts reales, es
**nueva funcionalidad, decisión separada** — no forma parte de las 10
decisiones pendientes y no se reabre aquí.

---

## 13. Cash Movement (decisión #5)

**Verificación de código real, exhaustiva**:
1. **Movimientos con UI real**: ninguno de entrada manual. Los únicos
   `CashMovement` generados hoy nacen automáticamente:
   `opening` (al abrir sesión), `sale_cash` (venta en efectivo),
   `cash_refund` (reembolso en efectivo), `customer_advance_cash`
   (anticipo en efectivo) — todos disparados por servicios de
   `apps.pos`, nunca por una pantalla dedicada a "registrar
   movimiento".
2. **Generados automáticamente**: los 4 anteriores + los de fases
   posteriores reutilizados por otros módulos
   (`supplier_payment_cash`/`supplier_advance_cash`/
   `expense_payment_cash`/`payroll_payment_cash`, generados desde
   `apps.purchases`/`apps.expenses`/`apps.payroll`).
3. **Generables manualmente (backend listo, sin UI)**: `cash_in`,
   `cash_out`, `withdrawal` — expuestos en `CashMovementForm`, servidos
   por `CashMovementCreateView`/`require_permission(request,
   "cash.move")`, pero sin ningún botón/enlace en ningún template.
4. **Sin caller en ningún punto de ejecución real**: `adjustment` —
   existe en el enum del modelo y en la lógica de signo de
   `get_expected_cash`, pero ni siquiera está entre las opciones de
   `CashMovementForm`; solo es invocable programáticamente
   (`record_cash_movement(..., ajuste_resta=...)`), nunca desde HTTP.
5. **Qué significa `adjustment`**: una corrección de caja fuera del
   flujo normal de venta/entrada/salida — su ausencia de UI y de
   asociación con `ApprovalRequest.ActionType.cash_movement` (que
   existe en el enum de aprobaciones pero tampoco tiene ningún caller
   real, confirmado en Etapa 1) sugiere que fue diseñado para requerir
   autorización de supervisor antes de habilitarse, pero esa conexión
   nunca se completó.
6. **¿Existe necesidad real de una pantalla de movimiento manual?**: no
   verificable desde el código — es una pregunta de operación real del
   negocio (¿los cajeros necesitan registrar entradas/salidas de
   efectivo fuera de venta/apertura/cierre?), no respondible solo con
   evidencia técnica.

**Clasificación**: `cash_in`/`cash_out`/`withdrawal` → **B** (decisión
del propietario sobre si exponer la UI ya construida) + **C** trivial
si la respuesta es sí (agregar un enlace, backend ya probado).
`adjustment` → **D** (no debe habilitarse sin resolver primero qué
permiso/autorización lo protege — conecta directamente con la decisión
#1; habilitarlo sin eso sería un vector de ajuste de caja no
controlado). **No se crea ninguna pantalla ni se habilita `adjustment`
en esta etapa.**

---

## 14. Approvals — crédito/descuento/overage (verificación: NO es una decisión pendiente)

**Hallazgo de esta etapa**: a diferencia de las 10 decisiones
pendientes, el mecanismo de aprobaciones para descuentos y crédito
excedido **ya está completo, conectado y probado** — no es una
decisión pendiente, y se documenta aquí explícitamente para que
ninguna etapa futura lo trate por error como tal.

Verificado en código: `apps/pos/services.py` (`add_item_to_cart`,
`set_cart_global_discount`, `checkout_sale`) llama a
`apps.approvals.services.check_discount_authorization`/
`check_credit_sale_authorization`, que a su vez usan
`get_effective_policy` (jerarquía usuario→rol→tenant→sin política =
requiere autorización siempre; OWNER siempre exento). Al exceder el
límite, se crea una `ApprovalRequest` real (`ActionType.DISCOUNT`/
`CREDIT_OVERAGE`, `Status.PENDING`); una vez aprobada por un
supervisor (fuera del POS, en `apps.approvals`), el POS la detecta y
la consume exactamente una vez (`mark_consumed`, protegido contra
reutilización). Cubierto por 15 tests reales
(`test_discount_authorization.py` + `test_credit_overage.py`).

**Quién genera las solicitudes**: el propio cajero, indirectamente, al
intentar un descuento/venta a crédito que excede su límite.
**Qué pantallas las muestran**: el terminal (bloque de autorizaciones
aprobadas pendientes de consumir) y el módulo de `apps.approvals`
(donde un supervisor las aprueba/rechaza) — ya cubierto visualmente en
Etapa 3 §12 (Discount Section) y Etapa 4.
**Qué queda pendiente**: nada funcional. Lo único pendiente es
puramente de UI (representación visual, ya resuelta en Etapas 3/4).

**Clasificación**: no aplica clasificación A-E — **no es una decisión
pendiente**, es funcionalidad ya resuelta. No se modifica
`apps.approvals` en esta etapa ni en ninguna futura sin motivo nuevo.

---

## 15. Seguridad — UI vs. autorización real

| Acción | UI actual | Permiso catalogado | Enforcement real | Riesgo | Decisión |
|---|---|---|---|---|---|
| Usar el terminal (agregar/quitar/checkout) | Accesible a cualquier usuario con membresía activa | `pos.use` | **No verificado** | Alto — cualquier rol, incluido `EMPLOYEE`/`MEMBER`, puede vender | **D**, pendiente #1 |
| Ver resumen de una sesión de caja | Accesible por URL directa a cualquier miembro | `cash.view` | **No verificado** | Medio — expone datos de otro cajero dentro del mismo tenant | **D**, pendiente #2 |
| Crear/confirmar/cancelar venta, reembolsar | Accesible a cualquier usuario con membresía activa | `sales.create`/`update`/`cancel`/`refund` | **No verificado** | Alto — anulación/reembolso sin control de rol | **D**, pendiente #1 |
| Registrar/reversar pago | Accesible a cualquier usuario con membresía activa | `payments.create`/`reverse` | **No verificado** | Alto — reversar un pago es una operación financiera sensible | **D**, pendiente #1 |
| Aplicar/ver crédito, notas de crédito | Accesible a cualquier usuario con membresía activa | `credit.view`/`apply`, `credit_note.*` | **No verificado** | Medio-alto | **D**, pendiente #1 |
| Abrir caja | Formulario dedicado | `cash.open` | **Sí, verificado** (`require_permission`) | Bajo — ya controlado | Sin acción |
| Cerrar caja | Formulario dedicado | `cash.close` | **Sí, verificado** | Bajo — ya controlado | Sin acción |
| Registrar movimiento manual (`cash_in`/`out`/`withdrawal`) | **Sin UI** (backend accesible por URL directa) | `cash.move` | **Sí, verificado** en la vista, pero sin punto de entrada visual | Bajo (la verificación existe; el riesgo real es solo de descubribilidad, no de autorización) | **B**, pendiente #5 |
| Crear caja física | Formulario dedicado | — (usa `require_role(OWNER)`, no el catálogo granular) | **Sí, verificado** (mecanismo distinto, binario) | Bajo, pero inconsistente con el resto del sistema de permisos | Fuera de alcance de esta etapa (no una de las 10) |
| Aplicar descuento/crédito excedido | Formularios reales del terminal | N/A (usa `apps.approvals`, no el catálogo de permisos) | **Sí, verificado** (mecanismo distinto y completo) | Bajo — ya controlado | Sin acción (§14) |

Regla explícita reafirmada: **ningún botón oculto o campo deshabilitado
en la UI constituye seguridad real** — solo `require_permission`/
`PermissionRequiredMixin` ejecutándose en el servidor la constituye.

---

## 16. Impacto en la implementación

| Decisión | Impacto técnico |
|---|---|
| #1 Brecha de autorización | Views (múltiples archivos), sin modelo/migración |
| #2 `cash.view` | View (1 archivo) |
| #3 Validación de disponibilidad al agregar | View/Service (`apps.pos`, `apps.sales`) |
| #4 Cierre por denominaciones | Modelo/migración + View/Service + Template (mayor alcance) |
| #5 Cash Movement manual (`cash_in`/`out`/`withdrawal`) | Template + enlace (mínimo) |
| #5b `adjustment` | Permisos + Service (bloqueado hasta resolver #1) |
| #6 Devolución accesible desde POS | Template (si es solo enlace) — View/Service si es flujo propio |
| #7 Cambio/vuelto persistido | Modelo/migración (`Payment`) + Service + Template |
| #8 `TaxCode` en POS | Service + Template + Form |
| #9 Edición de línea | View/Service nuevo (`UpdateItemView`) + Template |
| #10 Impresión térmica | CSS/Template — o Hardware/dispositivo si se decide integración dedicada |

---

## 17. Orden de resolución propuesto

El orden sugerido por la instrucción (Permisos → Checkout/pagos/cambio
→ Carrito → Caja → Receipt/impresión → Responsive/touch) **se confirma
como el orden correcto** tras el análisis técnico — ningún hallazgo de
esta etapa lo contradice. Justificación:

1. **Permisos (#1, #2)** primero: es la única decisión con impacto de
   seguridad real hoy en producción (cualquier rol puede operar el
   POS/anular ventas); además su costo de implementación ya está
   verificado como bajo (mecanismo listo, riesgo de test casi nulo).
2. **Checkout/pagos/cambio (#7)** segundo: afecta directamente la
   trazabilidad financiera de cada venta — cuanto antes se decida, menos
   ventas históricas quedan sin el dato si se opta por persistirlo.
3. **Carrito (#3, #9)** tercero: mejoras de UX/integridad de venta que
   no bloquean nada más, pero sí mejoran la experiencia del cajero día
   a día.
4. **Caja (#4, #5)** cuarto: `cash_in`/`out`/`withdrawal` es de bajo
   costo y puede adelantarse; denominaciones (#4) es la de mayor
   alcance y puede posponerse sin urgencia real.
5. **Receipt/impresión (#10)** quinto: depende de una confirmación de
   hardware que hoy no existe evidencia de que sea urgente.
6. **Responsive/touch**: no son decisiones pendientes (ya resueltas en
   Etapa 3/4) — son las primeras candidatas técnicas a ejecutarse en
   cualquier etapa de implementación, sin depender de ninguna decisión
   de negocio.

**Única salvedad**: #6 (devolución accesible desde POS) y #8
(`TaxCode`) no tienen una dependencia técnica de las demás — pueden
resolverse en cualquier momento del orden anterior según la
disponibilidad/prioridad de negocio del propietario, sin bloquear ni
ser bloqueadas por el resto.

---

## 18. Matriz final

| # | Decisión | Estado actual | Tipo | Impacto | Recomendación | Quién debe aprobar |
|---|---|---|---|---|---|---|
| 1 | Brecha de autorización (`pos.use`/`sales.*`/`payments.*`/`credit.*`) | Pendiente de seguridad | D | Views | Activar `require_permission` con códigos ya existentes; riesgo de test verificado como bajo | Propietario del sistema |
| 2 | `cash.view` no aplicado | Pendiente de seguridad | D (técnicamente A) | View | Agregar `require_permission("cash.view")`, cambio mínimo | Propietario del sistema |
| 3 | Validación de disponibilidad al agregar | Pendiente del propietario + técnica | B + C | View/Service | Conectar `ensure_unit_available_for_sale` ya existente | Propietario del sistema |
| 4 | Cierre de caja por denominaciones | Pendiente técnica (mayor alcance) | C (+ B si se confirma necesidad) | Modelo/migración/View/Template | Posponer hasta confirmar necesidad real; ya reservado en `docs/currency.md` | Propietario del sistema |
| 5 | Cash Movement manual + `adjustment` | Pendiente del propietario | B (+ D para `adjustment`) | Template (bajo) / Permisos (`adjustment`) | Exponer `cash_in`/`out`/`withdrawal` si se confirma necesidad; `adjustment` bloqueado hasta resolver #1 | Propietario del sistema |
| 6 | Devolución accesible desde POS | Pendiente del propietario | B | Template (si es enlace) | Recomendar solo enlace de navegación, no reimplementar lógica en `apps.pos` | Propietario del sistema |
| 7 | Cambio/vuelto persistido | Pendiente del propietario + técnica | B + C | Modelo/migración/Service/Template | Confirmar si es requisito de auditoría antes de tocar `Payment` | Propietario del sistema |
| 8 | `TaxCode`/`SaleItemTax` en POS | Pendiente del propietario + técnica | B + C | Service/Template/Form | Confirmar si algún tenant real lo necesita hoy | Propietario del sistema |
| 9 | Edición de línea del carrito | Pendiente del propietario + técnica | B + C | View/Service/Template nuevo | Confirmar si "quitar y re-agregar" es aceptable operativamente | Propietario del sistema |
| 10 | Impresión térmica 58/80mm | Pendiente de hardware | E (+ B) | CSS/Template o hardware dedicado | Mantener estándar (A) hasta confirmar hardware térmico real en producción | Propietario del sistema |

---

## 19. Decisiones que requieren aprobación humana

Las 10, sin excepción — ninguna se resuelve por sí sola con evidencia
de código; todas requieren que el propietario del sistema confirme
antes de que cualquier etapa de implementación las ejecute.

## 20. Decisiones que ya pueden considerarse técnicamente resueltas (solo pendientes de autorización para ejecutar)

- **#2** (`cash.view`): el *cómo* implementarlo está completamente
  resuelto (una línea, mismo patrón ya usado 3 veces) — solo falta la
  autorización para ejecutarlo, no el diseño técnico.
- **#1**: el mecanismo técnico también está completamente resuelto
  (`require_permission`/`PermissionRequiredMixin` ya existen, códigos
  de permiso ya existen, riesgo de regresión verificado como bajo) —
  lo único pendiente es la autorización de negocio para activarlo.
- Responsive del Terminal y Touch targets (no forman parte de las 10):
  completamente resueltos desde Etapa 3/4, listos para cualquier etapa
  de implementación sin depender de ninguna decisión adicional.

## 21. Decisiones explícitamente fuera de alcance

- PDF backend — ya decidido y cerrado (nunca implementado, sin
  dependencia nueva).
- Modo Noche — fuera de alcance permanente del proyecto completo.
- Atajos de teclado — descartados explícitamente (invención de Stitch,
  no una decisión pendiente real).
- Mecanismo de aprobaciones (`apps.approvals`) — ya completo y probado,
  no es una decisión pendiente (§14).
- Creación de caja física con `require_role(OWNER)` en vez del catálogo
  granular — inconsistencia notada pero no una de las 10 decisiones,
  no se resuelve en esta etapa.

---

## Confirmación de reglas absolutas respetadas

Ningún archivo de `apps/`, `templates/`, `static/`, modelo, vista,
form, service, URL, permiso, migración o test fue modificado en esta
etapa — exclusivamente análisis y documentación, con verificación
directa de código real donde fue necesario para clasificar con
precisión (nunca para implementar).
