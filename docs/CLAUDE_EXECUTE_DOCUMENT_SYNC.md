# INSTRUCCIÓN — SINCRONIZAR FASE 19 PERFORMANCE

## IMPORTANTE
Solo sincronización documental.
NO implementar optimizaciones.
NO crear índices, cache, código, migraciones ni modelos.
NO iniciar FASE 20.

## PASO 1
Lee:
`docs/phases/PHASE-19-performance.md`

## PASO 2
Audita:
- CLAUDE.md
- docs/MASTER-PROMPT.md
- ARCHITECTURE.md
- docs/performance.md si existe
- FASES 0–18
- CURRENT_PHASE.md
- PHASE_HISTORY.md
- KNOWN_ISSUES.md
- DECISIONS.md

## PASO 3
Actualiza el archivo existente manteniendo exactamente el nombre real del proyecto. Si existe `docs/phases/PHASE-19-performance.md`, no crear duplicado.

## PASO 4
Integrar el alcance completo de performance:
PostgreSQL/query plans, índices justificados, N+1, ORM, paginación, Inventory, Catalog, Sales/POS, Purchases/CxP, Accounting, Reports, Exports, Billing SaaS, PayPal/webhooks, cache, concurrencia, memory/CPU, benchmarks y regression tests.

## PASO 5
No crear documentación duplicada. Consolidar en las fuentes existentes y actualizar estado del proyecto.

## PASO 6
Verificar:
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `git diff`

La sincronización debe producir cambios documentales únicamente.

## REPORTE
Entregar:
- archivos modificados;
- contradicciones;
- decisiones;
- confirmación de cero cambios funcionales;
- checks/tests;
- commit;
- working tree.

## REGLA DE PARADA
DETENTE. No implementar FASE 19. No iniciar FASE 20.
