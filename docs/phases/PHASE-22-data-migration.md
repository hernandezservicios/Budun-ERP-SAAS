# FASE 22 — Data Migration

## Objetivo
Migrar datos local→Hostinger con pg_dump/pg_restore y verificación de conteos/consistencia.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] restore correcto
- [ ] conteos coinciden
- [ ] smoke tests

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`. Nota (ver
`docs/products.md`): la importación/exportación de productos vía Excel
(construida como extensión de FASE 8, ver
`ADENDUM_FASE_8_IMPORTACION_PRODUCTOS_EXCEL.md`) podrá
reutilizarse para cargas iniciales de catálogo, pero la migración
completa de datos de esta fase mantiene su propio procedimiento de
reconciliación e integridad (`pg_dump`/`pg_restore` + verificación de
conteos) — la importación de Excel nunca sustituye ese proceso.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
