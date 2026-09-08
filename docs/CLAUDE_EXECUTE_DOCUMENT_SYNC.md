# INSTRUCCIÓN — SINCRONIZAR FASE 20 BACKUPS + DISASTER RECOVERY

## IMPORTANTE
SOLO documentación.

NO implementar backups.
NO crear scripts funcionales.
NO crear migraciones.
NO cambiar infraestructura.
NO iniciar FASE 21.

## PASO 1
Leer:
`docs/phases/PHASE-20-backups.md`

## PASO 2
Auditar:
- CLAUDE.md
- docs/MASTER-PROMPT.md
- ARCHITECTURE.md
- docs/billing.md
- docs/inventory.md
- documentación de uploads/media
- FASES 0–19
- CURRENT_PHASE.md
- PHASE_HISTORY.md
- KNOWN_ISSUES.md
- DECISIONS.md

## PASO 3
Actualizar el archivo existente de FASE 20 manteniendo exactamente su nombre real. No crear una segunda FASE 20.

## PASO 4
Integrar:
- PostgreSQL backup/restore
- verification
- checksum/corruption detection
- retention
- scheduling
- local/off-site
- encryption
- media/files
- configuration recovery
- RPO/RTO
- disaster recovery runbook
- restore drill
- failure testing
- monitoring
- security
- Multi-Tenant/platform isolation
- performance
- tests/smoke

## PASO 5
No implementar nada funcional durante esta sincronización.

## PASO 6
Verificar:
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `git diff`

El diff funcional debe permanecer vacío.

## REPORTE
Entregar archivos modificados, contradicciones, decisiones, confirmación de cero cambios funcionales, checks/tests, commit y working tree.

## REGLA DE PARADA
DETENTE. No implementar FASE 20. No iniciar FASE 21.
