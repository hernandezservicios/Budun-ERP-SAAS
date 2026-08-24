# ADR-002 — No usar Docker

## Decisión
Docker queda excluido del proyecto por incompatibilidad del entorno local del propietario.

## Consecuencia
Desarrollo: Windows + Python virtualenv + PostgreSQL + pgAdmin 4.
Producción: Hostinger VPS + Linux + PostgreSQL + Django/Gunicorn + Nginx/servidor web apropiado.
