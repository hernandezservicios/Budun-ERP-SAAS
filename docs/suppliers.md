# Proveedores (FASE 9)

`apps/customers` — ver `docs/customers.md` para la arquitectura completa
compartida con `Customer` (separación de responsabilidades, búsqueda,
auditoría, Multi-Tenancy, performance, Design System). Este documento
cubre las diferencias específicas de `Supplier`.

## Modelo `Supplier`

Hereda `TenantScopedModel` (FASE 3) y el mismo mixin `ContactoMixin` que
`Customer` (identificación fiscal extensible, contacto, datos
comerciales, notas, estado) — ver `docs/customers.md` para el detalle de
esos campos compartidos.

### Diferencia deliberada con `Customer`: sin nombre de persona separado

`Supplier` **no tiene** `first_name`/`last_name` (a diferencia de
`Customer`). Se identifica por:

| Campo | Notas |
|---|---|
| `legal_name` | Razón social — para un proveedor persona física, es simplemente su nombre completo |
| `trade_name` | Nombre comercial (heredado del mixin compartido) |

**Regla de integridad** (`CheckConstraint`): debe haber al menos uno de
`legal_name` o `trade_name`.

`display_name` (propiedad): `legal_name` si existe, si no `trade_name`.

### Diferencias de campos con `Customer` (por diseño, no un descuido)

El usuario especificó listas de campos distintas para Cliente y
Proveedor. `Supplier` **no tiene**: `secondary_phone` (teléfono
secundario), `alternate_email` (correo alternativo), `postal_code`
(código postal), `credit_limit` (límite de crédito) ni
`commercial_notes` (notas comerciales separadas) — todos esos campos
solo existen en `Customer`, siguiendo literalmente la especificación de
la fase.

## Datos comerciales: preparados, sin motor financiero

Igual principio que `Customer` (ver `docs/customers.md`): `payment_terms`,
`credit_days`, `credit_enabled` y `currency` son configuración real ya
disponible hoy ("este proveedor nos da 30 días de crédito"). Lo que NO
existe todavía es el motor de cuentas por pagar (`balance`, ledger de
pagos) — llegará como un modelo relacionado nuevo (p. ej.
`SupplierAccount`) cuando FASE 12 (Compras) o Billing lo requieran,
nunca como un campo desnormalizado en `Supplier`.

## Preparación para fases futuras

- **FASE 12 — Compras**: `Purchase`/`PurchaseItem` deben referenciar a
  `Supplier` mediante su propia FK — `Supplier` no necesita saber nada
  de compras, la relación se declara desde el lado de `Purchase`.
- **FASE 13 — Gastos**: un `Expense` podrá opcionalmente referenciar a
  un `Supplier` cuando el gasto corresponda a él — también vía FK desde
  `Expense`, no al revés.
- **FASE 14 — Reportes**: "compras por proveedor" debe poder construirse
  agregando `PurchaseItem` agrupado por `Supplier`, reutilizando
  `services.get_active_suppliers`/`list_suppliers` como fuente de la
  lista de proveedores, no reimplementando la consulta.

## Multi-Tenancy y Performance

Ver `docs/customers.md` — la cobertura de tests y el diseño de
`services.list_suppliers`/`get_active_suppliers` son exactamente
paralelos a los de `Customer` (misma lista blanca de ordenamiento,
mismo criterio de búsqueda por campos análogos, mismo aislamiento
verificado en `test_isolation.py`).

## Qué NO se construyó en esta fase (deliberado)

Motor financiero de cuentas por pagar, Compras, Gastos, Reportes — ver
`docs/customers.md` para la lista completa compartida.
