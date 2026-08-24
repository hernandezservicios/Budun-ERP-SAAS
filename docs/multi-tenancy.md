# Multi-Tenancy

Single database con aislamiento por tenant a nivel de aplicación.

## Reglas
- Toda entidad empresarial debe estar vinculada al tenant.
- Current tenant debe establecerse de forma segura.
- Managers/querysets/service layer deben limitar datos.
- Permissions backend obligatorios.
- API Keys pertenecen a un tenant.
- Tests A/B obligatorios.
