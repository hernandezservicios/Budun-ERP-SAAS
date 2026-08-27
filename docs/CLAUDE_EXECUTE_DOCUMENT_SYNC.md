# INSTRUCCIÓN — SINCRONIZAR FASE 18 SECURITY HARDENING

## IMPORTANTE
SOLO sincronización documental.
NO implementar hardening todavía.
NO crear modelos/migraciones/endpoints.
NO iniciar FASE 19.

## PASO 1
Lee:
`docs/phases/PHASE-18-security-hardening.md`

## PASO 2
Audita:
- CLAUDE.md
- docs/MASTER-PROMPT.md
- ARCHITECTURE.md
- docs/security.md si existe
- FASES 0–17
- CURRENT_PHASE.md
- PHASE_HISTORY.md
- KNOWN_ISSUES.md
- DECISIONS.md

## PASO 3
Actualiza la FASE 18 existente manteniendo exactamente el nombre real del archivo del proyecto. Si ya existe `docs/phases/PHASE-18-security-hardening.md`, NO crear duplicado.

## PASO 4
Integra el alcance completo:
auth, authz, roles/permisos, privilege escalation, Multi-Tenant, Super Admin, Inventory API, Catalog API, Integration/App Secret, PayPal/webhooks, Billing SaaS, transferencias/comprobantes, uploads/media, XSS/CSRF/injection, mass assignment, HTTP headers/CORS, secrets, logs/errores, rate limiting, reports/exports, audit, concurrency y negative testing.

## PASO 5
No crear documentación duplicada. Consolidar en las fuentes existentes.

## PASO 6
Actualizar estados de proyecto y fuentes de verdad.

## PASO 7
Verificar que NO haya cambios funcionales:
- python manage.py check
- python manage.py makemigrations --check --dry-run
- revisar git diff
- ejecutar suite completa si el entorno lo permite

El diff funcional debe quedar vacío.

## REPORTE
Entrega:
- archivos modificados
- contradicciones encontradas
- decisiones aplicadas
- confirmación de cero cambios funcionales
- checks/tests
- commit
- working tree

## REGLA DE PARADA
DETENTE.
No implementar FASE 18.
No iniciar FASE 19.
