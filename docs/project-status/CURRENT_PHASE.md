# Estado actual del proyecto

```text
Fase actual: 7
Estado: PASS (cerrada, pendiente de autorización para FASE 8)
Última fase cerrada: FASE 7 — Dashboard
Próxima acción: esperar autorización explícita del usuario para iniciar FASE 8 — Products + Inventory
```

## Regla
Claude debe actualizar este archivo al inicio y al cierre de cada fase.

## Resumen de FASE 7
Se construyó el Panel administrativo (`apps/dashboard`) en `/panel/`, ahora destino real tras login/onboarding (antes era el perfil). Jerarquía visual de 6 secciones (encabezado/contexto, KPIs, tendencias, alertas, actividad reciente, acciones rápidas) usando exclusivamente el Design System de FASE 5 — sin colección de cards: los KPI tienen un estilo propio distinto de `.tarjeta`. Capa de servicios (`apps/dashboard/services.py`) como punto de extensión: cada función de KPI que todavía no tiene módulo real se marca `estado="vacio"` (nunca un número inventado); el único dato real disponible hoy (miembros del equipo, actividad de altas) viene de PostgreSQL (`tenants_membership`), filtrado explícitamente por tenant en cada consulta. Se agregó un índice compuesto a `Membership` para el patrón de consulta del panel. Aislamiento Multi-Tenant y ausencia de N+1 verificados con tests explícitos (comparación de número de queries con 1 vs. 10 miembros). Manejo de error gracioso (una fuente de datos que falla no rompe la página). 73/73 tests OK (regresión de FASE 3/4/5/6 sin cambios de lógica salvo el redirect post-login/onboarding, ahora al Panel). `manage.py check` en verde. Documentado en `docs/dashboard.md`.
