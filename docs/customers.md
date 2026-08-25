# Clientes (FASE 9)

`apps/customers` — módulo profesional de Clientes y Proveedores, primer
dominio de negocio construido después de Inventario (FASE 8). Este
documento cubre `Customer`; ver `docs/suppliers.md` para `Supplier` y
`docs/customer-documents.md`/`docs/supplier-documents.md` para los
documentos adjuntos.

## Modelo `Customer`

Hereda `TenantScopedModel` (FASE 3): aislamiento automático por tenant.
Comparte la mayoría de sus campos con `Supplier` a través del mixin
abstracto `ContactoMixin` (ver `models.py`), pero es un modelo
independiente — no hay ninguna relación entre ambos.

### Identidad

Un cliente puede ser una persona, una empresa, o ambos a la vez (una
empresa con una persona de contacto):

| Campo | Notas |
|---|---|
| `party_type` | `persona` / `empresa` — clasificación explícita, ver "Datos:" pedido por el usuario |
| `first_name` / `last_name` | Nombre de la persona (de contacto o titular) |
| `company_name` | Empresa (razón social del cliente, si aplica) |
| `trade_name` | Nombre comercial (puede aplicar tanto a una persona con negocio propio como a una empresa) |

**Regla de integridad** (`CheckConstraint`): debe haber al menos uno de
`first_name`, `last_name`, `company_name` o `trade_name` — un cliente
sin ningún nombre no es válido. Verificado con `IntegrityError` incluso
saltándose el formulario.

`display_name` (propiedad) combina estos campos de forma legible:
"Empresa (Nombre Apellido)" si hay ambos, o el que esté disponible.

### Identificación fiscal extensible

`identification_type` (Cédula, RNC, Pasaporte, Tax ID, Otro) es un
`CharField` con `choices`, no una tabla aparte: agregar un tipo nuevo
(p. ej. para un país nuevo) es agregar una línea a
`IdentificationType` en `models.py`, nunca una migración que
reestructure la tabla — así lo pidió explícitamente el usuario
("la arquitectura debe permitir añadir nuevos tipos sin rehacer el
modelo"). `identification_number` es el valor libre asociado.

**Regla de integridad**: si hay número de identificación, debe haber
también un tipo (`CheckConstraint` — no se guarda un número "huérfano"
sin saber qué es). Único por tenant (parcial: solo aplica a valores no
vacíos).

### Contacto

`email` (único por tenant, parcial), `alternate_email`, `phone`,
`secondary_phone`, `address`, `city`, `state_province`, `postal_code`,
`country`.

### Datos comerciales: preparados, sin motor financiero

Ver la sección "Preparación arquitectónica" más abajo.

### Notas y estado

`notes` (general), `commercial_notes` (específica de la relación
comercial), `is_active` (desactivar/reactivar, nunca un borrado físico).

## Preparación arquitectónica: crédito y saldos futuros

El usuario pidió explícitamente preparar el dominio para crédito/cuentas
por cobrar **sin implementar el motor financiero todavía**. La línea que
se trazó:

- **Configuración, ya real (campos existentes hoy)**: `payment_terms`
  (condiciones de pago: contado, 15/30/60 días, otro), `credit_days`
  (días de crédito), `credit_enabled` (crédito habilitado, sí/no),
  `credit_limit` (límite de crédito, `Decimal`, nunca negativo),
  `currency` (moneda), `commercial_notes`. El usuario ya puede
  configurar hoy, por ejemplo, "este cliente tiene 30 días de crédito,
  límite $5,000, en USD" — son datos de configuración reales, no
  simulados.
- **Motor financiero, deliberadamente NO construido**: no existe
  `balance`, ni ningún movimiento/ledger de cuentas por cobrar. Calcular
  un saldo requiere transacciones reales (ventas, pagos) que no existen
  hasta FASE 10 (Ventas) y una fase de Billing/cuentas por cobrar. Un
  campo `balance` desnormalizado hoy sería un número inventado, no un
  dato real — se evitó deliberadamente, mismo principio que llevó a no
  tener nunca un `current_stock` en `Product` (FASE 8): el
  cálculo se hace desde el histórico real, nunca desde un campo que se
  pueda desincronizar.
- **Extensión futura esperada**: cuando Ventas/Billing necesiten un
  saldo real, lo natural es un modelo relacionado nuevo (con su propio
  ledger append-only — mismo patrón que `StockMovement`/`InventoryUnit`
  en FASE 8) vinculado por FK a `Customer`, nunca un campo `balance`
  sobre este modelo. **Actualización (sincronización previa a FASE 11,
  FASE 10 ya construida)**: `Payment`/`PaymentAllocation` ya son ese
  ledger para pagos aplicados a facturas (ver `docs/payments.md`); el
  ledger de saldo a favor/anticipos/notas de crédito anticipado aquí
  como `CustomerAccount` se especificó formalmente como
  `CustomerCreditLedger` en `docs/accounts-receivable.md` — mismo
  concepto, nombre definitivo fijado ahí. Ese documento es la fuente de
  verdad de diseño para cuando se construya, no este.

## Arquitectura (separación de responsabilidades)

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Modelos | `models.py` | Estructura de datos, constraints, índices, `ActivityLog` |
| Servicios | `services.py` | Búsqueda/filtro/orden reutilizables, documentos, auditoría |
| Validación de archivos | `file_validation.py` | Extensión + firma binaria + tamaño (ver `docs/customer-documents.md`) |
| Formularios | `forms.py` | Validación de entrada (identificación/email únicos, al menos un nombre) |
| Vistas | `views.py` | Deliberadamente delgadas; bases compartidas `_Contact*` parametrizadas por modelo |
| Plantillas | `templates/customers/*.html` | Presentación, Design System de FASE 5 (tabs para Datos/Documentos/Historial/Actividad) |

## Búsqueda, filtros, ordenamiento y paginación

`services.list_customers(tenant, *, search, only_active, order)`:
búsqueda por nombre, apellido, empresa, nombre comercial, identificación,
correo o teléfono (`icontains`, insensible a mayúsculas). El
`order` se valida contra una lista blanca (`ORDENAMIENTOS_CUSTOMER`) —
nunca se pasa el valor crudo del querystring a `.order_by()`, para no
poder inyectar un ordenamiento sobre un campo/relación arbitraria desde
la URL. Paginación de 20 por página (`ListView.paginate_by`).

## Auditoría (`ActivityLog`)

Bitácora **mínima, acotada a este módulo**: registra creación, edición,
desactivación, reactivación, subida/eliminación/descarga de documentos,
con tenant, tipo de entidad, ID, nombre visible en el momento del
evento, usuario y fecha. Visible en la pestaña "Actividad" del detalle
de cada cliente/proveedor. **No es** el sistema de auditoría transversal
que construirá FASE 15 (Roles + Audit) para todo el proyecto — ese
podrá generalizar o sustituir este modelo más adelante.

## Historial de ventas: honesto, todavía vacío

La pestaña "Historial" del detalle de cliente muestra un estado vacío
explícito ("disponible desde FASE 10 — Ventas"), no datos simulados —
mismo principio que los KPIs "Ventas del mes"/"Gastos del mes" del Panel
(FASE 7).

## Multi-Tenancy

Cobertura de tests dedicada (`test_isolation.py`): lectura, búsqueda,
filtros, paginación, edición, desactivación, documentos (subida,
descarga, eliminación) y bitácora — Tenant A nunca accede a nada de
Tenant B, ni manipulando IDs en la URL, ni combinando un ID de cliente
propio con un `document_pk` ajeno, ni manipulando la sesión
(`active_tenant_id`, regresión de FASE 3).

## Performance

Verificado con comparación de conteo de queries (3 vs. 15
clientes/proveedores en el listado; 2 vs. 10 documentos en el detalle):
no crece, gracias a que no hay ningún acceso a relación sin
`select_related` en las plantillas.

## UX y Design System

Exclusivamente componentes de FASE 5: `.tabla`, `.badge`, `.estado-vacio`,
`.encabezado-pagina`, `.migas`, `.alerta`, `.campo`, `.tabs__*` (ARIA,
con navegación por teclado) para separar Datos/Documentos/Historial/
Actividad sin saturar la página con tarjetas. Sin identidad visual
nueva.

## Qué NO se construyó en esta fase (deliberado)

Motor financiero de crédito/cuentas por cobrar (balance, ledger de
pagos), Ventas, POS, Compras, Gastos, Reportes, API de Inventario,
PayPal, Billing.
