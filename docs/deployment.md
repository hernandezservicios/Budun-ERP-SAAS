# Deployment

## Local
Windows + virtualenv + PostgreSQL + Django.

## Producción
Hostinger VPS + PostgreSQL + Gunicorn + Nginx/servidor web + SSL.

## Flujo
GitHub → tests → build/package → deploy → migrations seguras → health check → smoke test.

Mantener rollback documentado.
