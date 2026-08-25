# FASE 13 — Expenses

## Objetivo
Gastos, categorías, adjuntos opcionales y reportes base.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] CRUD
- [ ] tenant scoped

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 8 — Inventario Serializado

FASE 8 agregó inventario serializado (`InventoryUnit`, ver
`docs/inventory.md`). Revisado explícitamente: Gastos (registro de
egresos de la empresa, sin relación directa con unidades de inventario)
no consume esa interfaz — no se requiere ningún cambio de diseño en esta
fase por ese motivo. Se documenta aquí solo para dejar constancia de que
se revisó, tal como pidió el usuario para todas las fases 10–15.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
