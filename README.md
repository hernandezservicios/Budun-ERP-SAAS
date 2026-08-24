# ERP SaaS Claude Kit

Kit profesional para iniciar un SaaS ERP Multi-Tenant desde cero utilizando **Antigravity como IDE y Claude como agente principal**.

## Arquitectura

- Django
- PostgreSQL
- pgAdmin 4
- Windows + Python virtualenv para desarrollo
- Hostinger VPS para producción
- Gunicorn + Nginx/servidor web apropiado
- Git/GitHub
- PayPal + PayPal MCP
- REST API `/api/v1/`
- API de Inventario para CRM IA

## No usar

Docker, Docker Compose, Docker Desktop, MySQL, MariaDB o WAMP como dependencia del proyecto.

## Inicio

1. Abre esta carpeta en Antigravity.
2. Usa Claude como agente principal.
3. Claude debe leer `CLAUDE.md`, `AGENTS.md` y `docs/MASTER-PROMPT.md`.
4. Claude ejecutará FASE 0 y FASE 1 únicamente.
5. Para PostgreSQL local debe seguir `docs/setup/windows-postgresql-pgadmin-step-by-step.md`.
6. Al cerrar cada fase debe actualizar `docs/project-status/` y crear un commit.

## Base de datos

La base de datos no se integra mágicamente con pgAdmin. Claude puede automatizar la configuración mediante terminal si tiene permisos, y usará pgAdmin 4 para verificación; algunas credenciales o confirmaciones pueden requerir tu intervención. El runbook incluido explica exactamente el proceso.

## API de Inventario

Está integrada oficialmente en FASE 15, con Base URL `/api/v1/`, API Key por tenant, regeneración/revocación, prueba de conexión, estado, auditoría, rate limiting y acceso read-only inicial para agentes CRM IA.

## Fases

Exactamente 25: FASE 0 a FASE 24.
