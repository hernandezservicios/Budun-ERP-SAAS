# FASE 7 — Dashboard

## Objetivo
Dashboard con KPIs reales, tablas, alertas, quick actions y arquitectura preparada para reportes.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] Datos reales — "Miembros del equipo" y "Actividad reciente" vienen de PostgreSQL (`tenants_membership`); los KPIs de módulos inexistentes se marcan `estado="vacio"`, nunca un número inventado.
- [x] tenant scoped — toda consulta de `apps/dashboard/services.py` filtra explícitamente por `tenant`; sin consultas globales.
- [x] responsive — hereda el shell de FASE 5; grids con `auto-fit`/`minmax`.

## Verificación
- [x] `python manage.py check` o la validación equivalente está en verde.
- [x] Tests relevantes ejecutados. — 73/73 (`manage.py test`).
- [x] Smoke test realizado cuando aplique. — `GET` real de `/panel/` autenticado.
- [x] Seguridad revisada para el alcance de la fase. — Login requerido, redirect a onboarding sin tenant, sin exposición de datos de otro tenant (verificado con tests explícitos).
- [x] Documentación actualizada. — `docs/dashboard.md` (nuevo).
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Ver historial de Git.

## Verificación detallada (pedida por el usuario)
1. **Tests**: 73/73 OK.
2. **Regresión FASE 3/4/5/6**: sin cambios de lógica, salvo el redirect post-login/onboarding (ahora al Panel, cambio intencional documentado).
3. **Django check**: sin errores.
4. **Smoke test HTTP real**: realizado sobre `runserver`.
5. **Multi-Tenant**: verificado con `DashboardIsolationTests` (4 tests), incluyendo regresión directa de manipulación de sesión.
6. **Queries/performance**: `select_related("user")` en actividad reciente; `.count()` para KPIs; índice compuesto nuevo en `Membership`; test que prueba que el número de queries no crece de 1 a 10 miembros (ausencia de N+1 verificada, no solo asumida).
7. **Responsive**: hereda el shell de FASE 5, sin capturas de pantalla reales (limitación ya documentada desde FASE 6).
8. **Documentación**: `docs/dashboard.md`.
9. **Commit**: ver historial de Git.

## Evidencia (FASE 7)
- Jerarquía visual de 6 secciones en el orden pedido, sin colección de cards (KPI con estilo propio, distinto de `.tarjeta`).
- Capa de servicios (`apps/dashboard/services.py`) como punto de extensión explícito para FASE 8+.
- Estados de UX cubiertos: success (datos reales), empty (KPIs/actividad/alertas), error (fallo simulado con `mock.patch`, sin 500), loading (vista previa tipo skeleton en Tendencias, justificado por ser una app 100% server-rendered).
- Ningún módulo de negocio (productos, inventario, ventas, POS, compras, gastos, API, PayPal, Billing) fue construido; sus KPIs/acciones se muestran como "vacío" o "Próximamente" (botones deshabilitados, nunca enlaces rotos).

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 8 — Products + Inventory.
