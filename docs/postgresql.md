# PostgreSQL

## Desarrollo
PostgreSQL instalado en Windows y administrado con pgAdmin 4.

## Conexión
Django usa variables de entorno. Puerto estándar: 5432 salvo que el entorno real indique otro.

## Buenas prácticas
Constraints, foreign keys, índices selectivos, Decimal para dinero, transacciones, migraciones versionadas.

## Backup
Preferir `pg_dump`/`pg_restore` y documentar también backup/restore desde pgAdmin 4.

## Configuración real de conexión (FASE 2 — PostgreSQL Foundation)

Estado: **conectado y verificado** el 2026-08-24.

| Parámetro | Valor |
|---|---|
| Motor | PostgreSQL 18.6 (`django.db.backends.postgresql` / psycopg 3) |
| Host | `127.0.0.1` |
| Puerto | `5432` |
| Base de datos | `erp_saas_dev` |
| Rol de aplicación | `erp_saas_app` (dueño de `erp_saas_dev`, `LOGIN`, `CREATEDB`; sin `SUPERUSER`) |
| Rol de mantenimiento | `postgres` (superusuario, usado solo desde pgAdmin 4 para tareas administrativas; Django nunca lo usa) |
| Autenticación | `scram-sha-256` (definido en `pg_hba.conf`) |

Notas:
- El rol `erp_saas_app` tiene `CREATEDB` para que `python manage.py test` pueda crear/destruir su propia base de datos de pruebas efímera (`test_erp_saas_dev`); no tiene ningún otro privilegio elevado.
- La contraseña de `erp_saas_app` **no se documenta aquí ni en ningún otro archivo del repositorio**: vive únicamente en `.env` (excluido de Git) y fue configurada directamente por el usuario en pgAdmin 4 / `.env`, nunca compartida en el chat.
- Ambos roles (`postgres` y `erp_saas_app`) ya estaban registrados/creados por el usuario en pgAdmin 4 antes de que Claude ejecutara ninguna migración.
- Tablas verificadas en `erp_saas_dev` (esquema `public`) tras `python manage.py migrate`: `auth_group`, `auth_group_permissions`, `auth_permission`, `auth_user`, `auth_user_groups`, `auth_user_user_permissions`, `django_admin_log`, `django_content_type`, `django_migrations`, `django_session`. Ninguna tabla de negocio todavía (correcto para esta fase).
