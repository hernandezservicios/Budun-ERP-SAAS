# AGENTS.md — Proyecto ERP SaaS

## Agente principal
Claude es el agente principal de desarrollo. Antigravity es únicamente el IDE/entorno de trabajo.

## Fuente de verdad
1. `CLAUDE.md`
2. `docs/MASTER-PROMPT.md`
3. `docs/phases/PHASES.md`
4. `docs/project-status/CURRENT_PHASE.md`
5. ADRs en `docs/adr/`

## Reglas no negociables
- No Docker.
- No MySQL/MariaDB.
- PostgreSQL es la base de datos oficial.
- pgAdmin 4 es la herramienta gráfica de administración local.
- Django se ejecuta localmente con virtualenv y `runserver` durante desarrollo.
- Producción: Hostinger VPS + Linux + Gunicorn + Nginx/servidor web apropiado + PostgreSQL.
- Todo el producto visible al usuario debe estar en español.
- UI moderna, profesional, limpia y muy legible; azul/verde sobrios y colores semánticos solamente.
- El sistema es Multi-Tenant y nunca puede filtrar datos entre tenants.
- API de Inventario `/api/v1/` integrada oficialmente en FASE 15, read-only inicialmente.
- PayPal y PayPal MCP se implementan progresivamente, primero Sandbox.
- Hay exactamente 25 fases, FASE 0 a FASE 24. No saltar ninguna.
- No continuar a la siguiente fase hasta cerrar y verificar la actual.

## Regla para el usuario no técnico
Claude debe ejecutar todo lo que pueda. Cuando una acción requiera una credencial, contraseña, aprobación o acceso externo que no esté disponible, debe dar instrucciones exactas paso a paso y esperar únicamente ese dato/acción.

## Regla de documentación
Cada cambio arquitectónico importante se registra en un ADR. Cada fase actualiza `docs/project-status/`.
