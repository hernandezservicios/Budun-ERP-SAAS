# FASE 15 — Roles + Audit + Inventory API

## Objetivo
Roles/permisos, audit log y API de Inventario para CRM IA.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] roles efectivos en backend
- [ ] audit log
- [ ] /api/v1/health/
- [ ] products/categories/inventory endpoints
- [ ] API Key por tenant
- [ ] regenerate/revoke
- [ ] connection test
- [ ] status/last test
- [ ] read-only
- [ ] scopes/rate limit
- [ ] API docs
- [ ] A/B API isolation

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
