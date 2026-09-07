# INSTRUCCIÓN — SINCRONIZAR IMPORTACIÓN MASIVA DE PRODUCTOS EXCEL

## IMPORTANTE
Solo documentación. NO implementar todavía.

## PASO 1
Lee:
`ADENDUM_FASE_8_IMPORTACION_PRODUCTOS_EXCEL.md`

## PASO 2
Audita:
- CLAUDE.md
- docs/MASTER-PROMPT.md
- ARCHITECTURE.md
- docs/inventory.md si existe
- docs/phases/PHASE-8*.md
- docs/reports.md
- FASES 9–19
- CURRENT_PHASE.md
- PHASE_HISTORY.md
- KNOWN_ISSUES.md
- DECISIONS.md
- FASES_OFICIALES_0_24_ACTUALIZADAS.md

## PASO 3
Integra la especificación en la documentación existente de Productos/Inventario, manteniendo nombres reales y sin duplicados.

La funcionalidad pertenece principalmente a FASE 8. Documenta su relación con FASE 14, FASE 19 y FASE 22.

## PASO 4
No crear código, modelos, migraciones, endpoints ni plantillas reales durante esta sincronización.

## PASO 5
La importación de productos NO puede crear una segunda fuente de stock ni modificar unidades/movimientos sin usar `apps.inventory.services`.

## PASO 6
Verifica:
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `git diff`

Solo cambios documentales.

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
DETENTE. No implementar la importación. No iniciar otra fase.
