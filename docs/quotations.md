# Cotizaciones (FASE 10)

`Quotation`/`QuotationItem` — propuesta comercial sin compromiso. Ver
`docs/sales.md` para la arquitectura compartida (snapshot histórico,
cálculo de totales, numeración, Multi-Tenancy).

## Estados y transiciones

`DRAFT` → `SENT` → `ACCEPTED` / `REJECTED` / `EXPIRED` → `CANCELED` /
`CONVERTED`. Validadas en `services.QUOTATION_TRANSITIONS`:

| Desde | Hacia |
|---|---|
| `DRAFT` | `SENT`, `CANCELED`, `CONVERTED` |
| `SENT` | `ACCEPTED`, `REJECTED`, `EXPIRED`, `CANCELED`, `CONVERTED` |
| `ACCEPTED` | `CONVERTED`, `CANCELED` |
| `REJECTED` / `EXPIRED` / `CANCELED` / `CONVERTED` | (terminales) |

`CONVERTED` es alcanzable desde `DRAFT`/`SENT`/`ACCEPTED` — se permite
convertir directamente sin pasar por `ACCEPTED` porque el usuario pidió
explícitamente soportar "Cotización → Venta/Factura directa cuando no
sea necesaria una proforma", incluso desde un borrador.

Solo se puede **editar** (agregar/quitar líneas) una cotización en
`DRAFT` (`services._require_editable_quotation`).

## Vigencia

`issue_date` (default: hoy) y `expiry_date` (opcional).
`services.expire_due_quotations(tenant=None)` marca como `EXPIRED` toda
cotización en `DRAFT`/`SENT` con `expiry_date` pasada — pensada para
ejecutarse sin request activa (comando de administración o tarea
programada futura; no se construyó el `cron`/scheduler en sí, solo la
función idempotente que lo haría, ver "Qué NO se construyó" en
`docs/sales.md`).

## Conversión

- `convert_quotation_to_proforma(quotation, user)`: crea una
  `ProformaInvoice` con las mismas líneas (copiadas tal cual, sin
  volver a tomar el snapshot del producto), `source_quotation` apunta a
  la cotización de origen (`OneToOneField` — impide convertir la misma
  cotización dos veces a nivel de base de datos, además del chequeo de
  estado). La cotización queda `CONVERTED` con `converted_at`/
  `converted_by`.
- `convert_quotation_to_sale(quotation, user)`: igual, pero crea
  directamente una `Sale` en `DRAFT` (sin proforma intermedia).
- Intentar convertir una cotización ya `CONVERTED` (o en cualquier
  estado terminal) lanza `InvalidSalesOperation` con un mensaje claro,
  antes de tocar la base de datos.

## Duplicar

`duplicate_quotation(quotation, user)`: crea una cotización nueva en
`DRAFT` (número nuevo, sin ninguna referencia de origen/conversión) con
las mismas líneas — útil para repetir una propuesta similar sin volver
a capturar todo desde cero.

## Cotización e inventario: nunca reduce stock, puede consultarlo

Una cotización **no** reduce inventario ni crea una reserva por sí
sola. `services.get_available_to_promise(product)` puede consultarse en
cualquier momento para mostrar disponibilidad real (QUANTITY: stock
menos reservas activas; SERIALIZED: conteo de unidades `EN_STOCK`, que
ya excluye las reservadas). Si una línea de cotización es de un
producto SERIALIZADO, puede indicarse ya la unidad concreta
(`inventory_unit`, vía IMEI/serie) — eso no la reserva; solo dejará
constancia de cuál se tenía en mente al cotizar.

## Impresión

`quotation_print.html` — vista HTML imprimible (`@media print`), no un
PDF binario. Ver `docs/invoice-documents.md`.

## Documentos adjuntos y auditoría

Ver `docs/invoice-documents.md` y `docs/sales.md` (`SalesActivityLog`).

## Multi-Tenancy

Cobertura en `apps/sales/tests/test_isolation.py`: lectura, listados,
conversión, IDs manipulados — Tenant A nunca accede a una cotización de
Tenant B.
