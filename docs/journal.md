# Libro Diario / Asiento Contable (FASE 14)

> Este archivo es un puntero deliberado, no un documento duplicado.
> El diseño completo de `JournalEntry`/`JournalEntryLine` vive en
> [`docs/accounting.md`](accounting.md), sección 3 ("Asiento contable")
> y sección 4 ("Inmutabilidad — reverso, nunca edición"). El reporte
> "Libro Diario" cronológico (`get_general_journal`) está en la
> sección 8. Ver también la sección 11 de ese mismo archivo, que
> documenta por qué se consolidó el contenido en vez de triplicarlo en
> tres archivos separados.

En resumen (el detalle completo está en las secciones enlazadas
arriba):

- Cada línea de un asiento es débito O crédito, nunca ambos ni
  ninguno.
- Un asiento solo puede quedar `POSTED` si `SUM(débito) == SUM(crédito)`
  — nunca se permite un asiento descuadrado.
- Todas las líneas de un mismo asiento comparten la misma moneda; el
  período debe estar abierto; todas las cuentas referenciadas deben
  permitir contabilización (`allows_posting=True`) y estar activas.
- Numerado vía la misma `DocumentSequence` de Ventas/Compras/Gastos/
  Nómina (prefijo «AST-»), nunca un contador propio.
- Un asiento `POSTED` nunca se edita ni se borra — toda corrección es
  un reverso (`reverse_journal_entry`), idempotente.
