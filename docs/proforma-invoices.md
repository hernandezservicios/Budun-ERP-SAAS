# Proformas / Prefacturas (FASE 10)

`ProformaInvoice`/`ProformaInvoiceItem` — documento comercial intermedio
entre la cotización y la venta. Ver `docs/sales.md` para la arquitectura
compartida.

## Estados y transiciones

`DRAFT` → `ISSUED` → `EXPIRED` / `CANCELED` / `CONVERTED`. Validadas en
`services.PROFORMA_TRANSITIONS`:

| Desde | Hacia |
|---|---|
| `DRAFT` | `ISSUED`, `CANCELED` |
| `ISSUED` | `EXPIRED`, `CANCELED`, `CONVERTED` |
| `EXPIRED` / `CANCELED` / `CONVERTED` | (terminales) |

Solo se puede editar (agregar/quitar líneas) en `DRAFT`. Solo se puede
**reservar stock** (ver abajo) o **convertir a venta** estando `ISSUED`
— una proforma en borrador todavía no representa un compromiso real.

## Origen: desde cotización o independiente

- `convert_quotation_to_proforma` (ver `docs/quotations.md`) crea la
  proforma con `source_quotation` ya asignado.
- `services.create_proforma(tenant, user=..., ...)` crea una proforma
  **standalone**, sin cotización previa — el usuario pidió
  explícitamente soportar ambos caminos ("crear desde cotización;
  crear independientemente cuando tenga sentido").

## Proforma e inventario: reserva EXPLÍCITA, nunca automática

Emitir una proforma (`ISSUED`) **no** reserva stock por sí sola —
requisito explícito del usuario. La reserva es una acción separada:

`services.reserve_stock_for_proforma(proforma, user)`:
1. Exige que la proforma esté `ISSUED` (rechaza en cualquier otro
   estado).
2. Por cada línea, crea una `Reservation` (ver `docs/reservations.md`):
   - Producto SERIALIZADO → transiciona la `InventoryUnit` de esa línea
     a `RESERVADO` (reutilizando la máquina de estados de FASE 8).
   - Producto QUANTITY → reserva la cantidad de esa línea, rechazando
     la operación completa si no hay disponibilidad suficiente para
     **alguna** línea (todo o nada, dentro de la misma llamada — cada
     reserva individual ya es atómica y bloquea su propio producto/
     unidad).

Cancelar o dejar vencer una proforma **libera automáticamente** las
reservas activas que originó (`_release_reservations_for_source`,
llamado desde `transition_proforma_status`): las unidades SERIALIZADAS
vuelven a `EN_STOCK`, las reservas de cantidad se marcan `RELEASED`.

## Conversión a venta

`convert_proforma_to_sale(proforma, user)`: crea una `Sale` en `DRAFT`
con las mismas líneas; `source_proforma` apunta a la proforma
(`OneToOneField` — impide convertir la misma proforma dos veces), y si
la proforma a su vez venía de una cotización, `source_quotation` se
propaga también a la venta para conservar la trazabilidad completa de
la cadena Cotización → Proforma → Venta. La proforma queda `CONVERTED`
con `converted_at`/`converted_by`.

Las reservas activas originadas por esta proforma se marcan
`CONVERTED` (no `RELEASED`) recién cuando la **venta** se confirma
(`confirm_sale`), no en el momento de la conversión Proforma→Venta —
mientras la venta siga en `DRAFT`, la reserva/unidad sigue
representando el mismo compromiso físico.

## Vigencia

Igual que Cotizaciones: `services.expire_due_proformas(tenant=None)`
marca como `EXPIRED` toda proforma `ISSUED` con `expiry_date` pasada.

## Impresión, documentos adjuntos y auditoría

Ver `docs/invoice-documents.md` y `docs/sales.md`.

## Multi-Tenancy

Cobertura en `test_isolation.py`: lectura, conversión, IDs manipulados.
