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

## Nota de FASE 8 — Interfaz de Inventario Serializado a consumir

La API de Inventario (`/api/v1/...`, ver también `CLAUDE.md`) debe
exponer el inventario serializado agregado en FASE 8 respetando el
mismo principio READ-ONLY y de aislamiento por API Key/tenant definido
para el resto de la API:

- `GET /api/v1/products/{id}/` debe incluir `inventory_tracking_type`.
- Un scope/endpoint adicional (p. ej. `GET /api/v1/inventory/units/` o
  bajo `/api/v1/products/{id}/units/`) debe exponer las `InventoryUnit`
  del producto, filtradas siempre por el tenant dueño de la API Key —
  nunca por un `tenant_id` recibido en la petición.
- Nunca exponer el IMEI/serie completo si el scope de la API Key no lo
  requiere explícitamente; cuando se exponga (p. ej. para que un CRM IA
  pueda buscar por IMEI), debe ser una decisión de scope explícita, no
  el comportamiento por defecto — mismo principio de seguridad ya
  aplicado en `apps/inventory/services.py` (nunca exponer el
  identificador completo innecesariamente en logs o errores).
- Reutilizar `services.search_catalog`/`services.get_current_stock` como
  la fuente de datos de estos endpoints, no reimplementar las consultas.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
