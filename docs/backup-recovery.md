# Backup y Recuperación

## Desarrollo
Usar pg_dump y pgAdmin 4.

## Producción
Programar backups, retention y restore drills. Antes de cambios destructivos: backup → verify → change → test.

## Disaster recovery
Recrear VPS → instalar PostgreSQL/Django/Gunicorn/Nginx → restaurar DB → migrar/verificar → health check → DNS/SSL.
