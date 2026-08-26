# Períodos Contables (FASE 14)

> Este archivo es un puntero deliberado, no un documento duplicado.
> El diseño completo de `AccountingPeriod` vive en
> [`docs/accounting.md`](accounting.md), sección 2 ("Período contable").
> Ver también la sección 11 de ese mismo archivo, que documenta por qué
> se consolidó el contenido en vez de triplicarlo en tres archivos
> separados.

En resumen (el detalle completo, con el diagrama de estados y las
reglas de cierre/reapertura, está en la sección enlazada arriba):

- `AccountingPeriod` no tiene número comercial vía `DocumentSequence`
  — se identifica por su rango de fechas (`name`, ej. «2025-01»), no es
  un documento que se emite.
- Dos períodos del mismo tenant nunca se solapan en fechas, salvo que
  uno ya esté `CLOSED`.
- `close_period` exige `SUM(débitos) == SUM(créditos)` de todas las
  líneas `POSTED` del período antes de permitir el cierre.
- Reabrir un período `CLOSED` exige un motivo explícito, auditado.
