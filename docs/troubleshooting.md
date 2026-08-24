# Troubleshooting

## Django no conecta a PostgreSQL
1. Verificar servicio PostgreSQL.
2. Verificar puerto 5432.
3. Verificar DB/user/password.
4. Verificar `.env`.
5. Probar con pgAdmin.
6. Ejecutar `python manage.py check` y tests de DB.

## API de Inventario
Verificar key, tenant, scopes, rate limit, endpoint y logs seguros.

## Producción
Verificar Gunicorn, Nginx, PostgreSQL, DNS, SSL y health endpoints.
