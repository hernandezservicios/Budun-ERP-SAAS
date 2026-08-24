# PostgreSQL

## Desarrollo
PostgreSQL instalado en Windows y administrado con pgAdmin 4.

## Conexión
Django usa variables de entorno. Puerto estándar: 5432 salvo que el entorno real indique otro.

## Buenas prácticas
Constraints, foreign keys, índices selectivos, Decimal para dinero, transacciones, migraciones versionadas.

## Backup
Preferir `pg_dump`/`pg_restore` y documentar también backup/restore desde pgAdmin 4.
