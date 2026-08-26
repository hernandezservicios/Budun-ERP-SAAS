# Libro Mayor (FASE 14)

> Este archivo es un puntero deliberado, no un documento duplicado.
> El diseño completo del Libro Mayor (`get_general_ledger`) vive en
> [`docs/accounting.md`](accounting.md), sección 8 ("Reportes
> contables"), junto con el Balance de Comprobación, el Libro Diario,
> el Balance General y el Estado de Resultados — los cinco reportes
> contables comparten la misma regla (leen siempre directamente de
> `JournalEntry`/`JournalEntryLine`, nunca recalculan desde otra
> fuente) y se explican juntos para no repetirla cinco veces. Ver
> también la sección 11 de ese mismo archivo, que documenta por qué se
> consolidó el contenido en vez de triplicarlo en tres archivos
> separados.

En resumen (el detalle completo está en la sección enlazada arriba):

- `get_general_ledger(tenant, account, ...)` devuelve los movimientos
  cronológicos de UNA cuenta con saldo acumulado, calculado en la
  dirección de su `normal_balance` (débito o crédito) — permite
  drill-down al asiento origen de cada línea.
- Nunca un campo de saldo desnormalizado en `Account`: el saldo se
  deriva siempre sumando `JournalEntryLine` en el momento de la
  consulta.
