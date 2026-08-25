# FASE 17 — Billing SaaS

## Objetivo
Planes, suscripciones, estados, límites y sincronización con PayPal.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] tenant→plan→subscription
- [ ] limits
- [ ] status sync
- [ ] cancel flow

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 10 — Revisado, sin cambios de diseño necesarios

FASE 10 agregó el motor comercial de los TENANTS (`apps/sales`, ventas
de cada empresa cliente del SaaS) — conceptualmente distinto del
Billing del propio SaaS (lo que Budun ERP le cobra a cada tenant por
usar la plataforma). Revisado explícitamente: no hay ninguna relación
directa; esta fase no necesita consumir `apps.sales`. Si en el futuro
se quisiera facturar a un tenant basándose en su volumen de ventas
(p. ej. un plan por transacción), sería una agregación de solo lectura
sobre `Sale`/`Payment`, nunca una dependencia estructural.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
