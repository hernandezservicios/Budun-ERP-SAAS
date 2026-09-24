# ERP DESIGN LAB — DECISION LOG (FASE 3)

Registro de las decisiones de diseño exploradas en el
[Atlas ERP Lab](https://claude.ai/artifact/XVrBtYd9pgiw77zxJoetqK). Sin
rankings ni "mejor/peor" — cada entrada documenta el problema, las
alternativas exploradas y la dirección propuesta para continuar hacia
Stitch (FASE 4), con su razón visual o funcional. La decisión final de qué
congelar es del usuario; esto es un registro, no una resolución.

---

### 1. Composición del Dashboard

- **Problema**: la misma información real (4 KPIs, 2 alertas, 2 eventos de
  actividad, 2 accesos rápidos) puede organizarse de varias formas.
- **Opciones exploradas**: A — Operativo (grid de KPIs + dos paneles en
  paralelo); B — Analítico (2 KPIs con tendencia en tamaño grande, feed
  único combinando alertas y actividad); C — Compacto (todo en una columna
  de pares etiqueta:valor, sin tarjetas separadas).
- **Propuesta para continuar**: A (Operativo).
- **Razón**: coincide con el uso real de hoy (vistazo rápido, no un panel
  de trabajo prolongado) y no depende de datos que el backend no calcula
  todavía — B requiere una serie histórica para la tendencia (`↑12%`) que
  el Discovery no confirmó como disponible; introducirla sería una
  funcionalidad nueva, no solo una composición visual.
- **Componente afectado**: KPI Cards, Cards, Alerts.

### 2. Densidad de tabla en listados

- **Problema**: cuántas densidades de tabla necesita el ERP y cuándo usar
  cada una.
- **Opciones exploradas**: A — Estándar; B — Compacta; C — Mayor jerarquía
  visual (barra de acento de 3px por estado, cliente más grande).
- **Propuesta para continuar**: confirmar la regla ya establecida en FASE 2
  (`docs/erp-redesign-design-system.md`, §10) — Estándar por defecto en
  listados de negocio (Ventas, Clientes, Productos), Compacta reservada a
  libros de alto volumen (Caja, Libro Mayor, Nómina). C queda documentada
  como explorada pero no se propone congelar: introduce un tercer patrón
  visual que la especificación deliberadamente evitó, salvo que aparezca
  una necesidad real distinta de las ya mapeadas.
- **Componente afectado**: TableStandard, TableFinancial.

### 3. Distribución del Detail view

- **Problema**: cómo priorizar información vs. acciones en una vista de
  detalle real (Venta, con líneas + pagos + documentos + actividad).
- **Opciones exploradas**: A — Información primero (resumen y pestañas al
  frente, acciones discretas); B — Acción primero (barra de acción
  destacada arriba, resumen condensado); C — Denso empresarial (dos
  columnas, totales siempre visibles sin cambiar de pestaña).
- **Propuesta para continuar**: A como patrón por defecto (ya es el patrón
  aprobado en FASE 2 para Cliente/Proveedor/Producto/Empleado); C como
  variante específica para detalles con muchas líneas y una cifra que debe
  permanecer visible mientras se revisan ítems (candidato real: asiento
  contable, orden de compra con muchas líneas). B queda documentado como
  explorado; no se propone para ningún flujo concreto todavía porque
  ningún detalle real del Discovery tiene una única acción tan dominante
  como para justificar sacrificar el resumen.
- **Componente afectado**: DetailView, Tabs, Cards.

### 4. Layout de formulario

- **Problema**: cuántas columnas y si agrupar en secciones para
  formularios de tamaño medio (Gasto, con 6 campos reales).
- **Opciones exploradas**: A — Una columna; B — Dos columnas sin
  secciones; C — Secciones con grilla de 2 columnas dentro de cada una.
- **Propuesta para continuar**: C como patrón por defecto para formularios
  de 5+ campos con agrupación lógica clara (ya es el patrón aprobado en
  FASE 2, `FormLayout`); A para formularios cortos (≤4 campos, una sola
  agrupación conceptual). B queda documentado como explorado pero no se
  propone congelar: mezclar campos de distintas secciones conceptuales en
  una grilla plana dificulta la lectura en formularios más largos como
  Empleado u Orden de compra.
- **Componente afectado**: FormFields, FormLayout.

### 5. Tratamiento de datos sensibles (RRHH)

- **Problema**: cómo comunicar visualmente que un campo existe pero está
  oculto por permisos (`can_view_sensitive_employee_data`), sin ocultar el
  campo por completo (que ocultaría la existencia del dato, no solo su
  valor).
- **Opciones exploradas**: solo una — ícono de candado + nota de texto
  ("Solo visible para el propietario") en el lugar exacto donde iría el
  valor.
- **Propuesta para continuar**: congelar este tratamiento como el patrón
  oficial para cualquier campo con gating de sensibles (salario, datos
  bancarios) — nunca un blur decorativo ni la omisión silenciosa del campo.
- **Componente afectado**: DetailView (nuevo estado de campo: "oculto por
  permiso").

### 6. Progreso de recepción en Compras

- **Problema**: `PurchaseOrderItem` no guarda cantidad recibida como
  campo — se calcula agregando sobre `PurchaseReceiptItem` (regla de FASE
  12) — pero el Lab necesitaba una forma visual de mostrar ese porcentaje
  calculado.
- **Opciones exploradas**: solo una — barra de progreso (`radius-pill`,
  color `success` al 100%, `warning` en progreso) + fracción numérica.
- **Propuesta para continuar**: elemento nuevo, no incluido originalmente
  en las 20 secciones del ERP DESIGN SYSTEM SPEC (FASE 2) — se propone
  incorporarlo formalmente como componente "Barra de progreso" si se
  aprueba, ya que resuelve una necesidad real confirmada (Discovery,
  Compras) y no una decoración añadida sin motivo.
- **Componente afectado**: nuevo — Progress bar (pendiente de sumar al
  spec si se aprueba).

### 7. Modo Noche en el POS

- **Problema**: el POS real no tiene hoy ninguna adaptación a poca luz de
  mostrador (Discovery, hallazgo de `apps.pos`); Atlas define un tema
  Noche pensado exactamente para ese caso.
- **Opciones exploradas**: Modo Día (igual al resto del ERP) vs. Modo
  Noche (fondo oscuro, acentos aclarados) — ambos probados sobre la misma
  pantalla de Terminal en el Lab.
- **Propuesta para continuar**: NO se resuelve en esta fase — es una
  decisión de producto (¿el POS debería abrir en Noche por defecto en
  ciertos horarios o cajas, o quedar siempre en Día como el resto del
  ERP?) que corresponde a la FASE 7 (POS Lab profundo), no a esta
  exploración general. Se deja documentada para que se decida
  explícitamente en esa fase.
- **Componente afectado**: todos los tokens de color (tema completo).

### 8. Tira "Lista → Detalle → Acciones" (Ventas)

- **Problema**: cómo mostrar que Clientes/Cotizaciones/Proformas/Ventas se
  sienten como un único sistema sin repetir 4 pantallas completas ya
  cubiertas en otras secciones del Lab.
- **Opciones exploradas**: solo una — tres tarjetas miniatura conectadas
  por flechas, mostrando el mismo componente de badge/tabla/botón en cada
  paso.
- **Propuesta para continuar**: esta tira es un recurso explicativo del
  Lab, no un componente de producto — no se traslada literalmente a
  Stitch ni a la implementación. Lo que se confirma es el principio que
  ilustra (mismos componentes atraviesan los 4 módulos), ya capturado
  como regla en el ERP DESIGN SYSTEM SPEC.
- **Componente afectado**: ninguno (herramienta de explicación, no un
  patrón nuevo).

---

## Qué queda fuera de esta fase

El aislamiento frente al SaaS Super Admin (tokens/CSS separados, sidebar
claro vs. oscuro) y los 17 componentes base (Buttons, Badges, Alerts,
Tabs, etc.) ya fueron decididos y congelados en FASE 2 — el Lab los aplicó
sobre pantallas reales sin reabrirlos. Ningún hallazgo de esta fase
requirió modificarlos.
