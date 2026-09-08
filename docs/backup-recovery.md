# Backup y Recuperación

> **Estado: pendiente de ejecución — FASE 20 (Backups + Disaster
> Recovery) todavía no autorizada.** Este documento es la referencia
> CONSOLIDADA de backup/recuperación de todo el proyecto (FASE 0–19):
> para cada categoría marca **Construido** (lo que ya existe hoy,
> verificado contra el código/configuración real, no solo un plan) y
> **Pendiente en FASE 20** (con la razón explícita). Nunca declara
> "ya implementado" nada que no lo esté — hoy no existe ningún script
> de backup, restore automatizado, checksum, retention, scheduling,
> cifrado ni runbook probado en el repositorio (verificado por
> búsqueda exhaustiva: no hay ningún archivo relacionado con backup
> fuera de este documento y de `docs/phases/PHASE-20-backups.md`). El
> checklist completo de 31 secciones y los criterios de aceptación
> viven en `docs/phases/PHASE-20-backups.md`.

## 1. Estrategia (tres componentes, nunca solo la base de datos)
Una recuperación completa del sistema requiere los tres componentes
por separado — PostgreSQL nunca recupera archivos:

```text
Database Backup (PostgreSQL)
+
Application Files / Media Backup (media-private/, catalog-media/)
+
Configuration Recovery (.env, dependencias, servicios del sistema)
```

**Pendiente en FASE 20**: implementar y probar los tres componentes
de forma real, no solo documentarlos.

## 2. PostgreSQL
**Construido (entorno real de desarrollo, verificado)**: PostgreSQL
18.6 (`django.db.backends.postgresql` / psycopg 3), base de datos
`erp_saas_dev`, rol de aplicación `erp_saas_app` (dueño de la base,
sin `SUPERUSER`), rol de mantenimiento `postgres` (superusuario, solo
desde pgAdmin 4, ver `docs/postgresql.md`). `pg_dump.exe`/
`pg_restore.exe` ya están instalados y disponibles en el `PATH` del
sistema (`C:\Program Files\PostgreSQL\18\bin`) — confirmado en este
entorno, no asumido. Práctica ya seguida informalmente por el equipo
(sin script todavía): antes de un cambio destructivo real,
backup manual vía pgAdmin 4 → verificar → aplicar el cambio → probar
(ver `docs/postgresql.md` sección "Backup").
**Pendiente en FASE 20**: script real de backup con `pg_dump`
(formato, compresión y compatibilidad evaluados explícitamente —
`--format=custom` es el candidato natural por soportar restore
selectivo y compresión nativa, decisión a confirmar en la
implementación); registro de fecha/hora, base, versión de
PostgreSQL, tamaño, duración, resultado, checksum y ubicación; nunca
incluir la contraseña de `erp_saas_app` en el comando en texto plano
visible (usar `PGPASSWORD` de entorno o `.pgpass`, nunca un argumento
`-W` interactivo en un script no interactivo).

## 3. Restore real
**Construido**: ninguno todavía — no existe un procedimiento de
restore real ejecutado ni documentado paso a paso más allá de "usar
`pg_restore`" (`docs/postgresql.md`).
**Pendiente en FASE 20**: backup real → base de datos temporal/aislada
(nunca `erp_saas_dev` ni la base de pruebas efímera de
`manage.py test`) → restore → conexión real → verificación. La base
principal de desarrollo nunca debe destruirse para probar un restore.

## 4. Restore verification
**Pendiente en FASE 20**: verificar conexión, presencia de todas las
tablas y migraciones aplicadas (`manage.py showmigrations`), conteos
críticos y relaciones/constraints, y datos representativos de cada
dominio del proyecto (tenants, productos, inventario/seriales,
ventas, pagos, compras, gastos, RRHH/nómina, contabilidad, Billing,
auditoría) — nunca dar un restore por válido solo porque el comando
terminó sin error.

## 5. Integridad y checksum
**Pendiente en FASE 20**: checksum criptográfico estándar (`SHA-256`,
mismo algoritmo ya usado en el proyecto para `ApiKey`/`Integration`
en `apps.api.crypto`, sin introducir un segundo mecanismo de hash) por
archivo de backup, calculado inmediatamente después de generarlo y
verificado antes de cualquier restore — un backup truncado, corrupto
o con checksum incorrecto debe rechazarse explícitamente, nunca
usarse en silencio.

## 6. Retention
**Pendiente en FASE 20**: política diaria/semanal/mensual a definir e
implementar; el último backup válido nunca se borra automáticamente,
incluso si la política de retención normal lo indicaría — regla de
seguridad explícita que debe probarse con un test dedicado, no solo
documentarse.

## 7. Scheduling
**Pendiente en FASE 20**: ejecución programada. Preferir `cron`/
`systemd timer` del VPS de producción (Hostinger, FASE 21) sobre un
scheduler propio en Django — el proyecto no depende de `runserver`
para ninguna tarea recurrente hoy (mismo criterio que descartó Celery/
Redis para tareas de Billing en FASE 17, `apps.billing` usa comandos
de administración pensados para cron real, sin ejecutarlos todavía).
En desarrollo (Windows, sin `cron`), un backup manual/on-demand es
aceptable — la automatización real de calendario es responsabilidad
del entorno de producción.

## 8. Local + Off-site
**Construido**: ninguna infraestructura de almacenamiento externo
existe todavía — el proyecto no tiene ningún proveedor de
almacenamiento en la nube configurado (sin S3, sin equivalente).
**Pendiente en FASE 20**: arquitectura local + copia off-site
(mecanismo concreto a decidir en la implementación, sin inventar un
servicio no aprobado — mismo principio que "Redis solo si una fase
posterior demuestra necesidad real" de `CLAUDE.md`). Un backup nunca
debe exponerse vía HTTP bajo ninguna circunstancia.

## 9. Cifrado
**Pendiente en FASE 20**: evaluar cifrado, en particular para la
copia off-site. Sin criptografía propia inventada (usar una
herramienta estándar ya establecida); la clave de cifrado nunca se
guarda junto al backup que protege.

## 10. Media y archivos (uploads)
**Construido (verificado en `config/settings.py`)**: dos raíces de
almacenamiento físicamente separadas y ya en uso — `MEDIA_ROOT`
(`media-private/`, documentos privados: `CustomerDocument`/
`SupplierDocument`/`InvoiceDocument`/`PaymentProof`, nunca servidos
como estático público, ver `docs/security.md` sección "Uploads y
media") y `CATALOG_MEDIA_ROOT` (`catalog-media/`, `ProductImage`
público servido por UUID, ampliación final de FASE 15). Ambas son
carpetas del sistema de archivos local, sin backup automatizado hoy.
**Pendiente en FASE 20**: backup/restauración real y probada de
ambas carpetas junto con la base de datos — un restore de solo la
base de datos sin sus archivos dejaría referencias a documentos
inexistentes (`PaymentProof.file`, `ProductImage.image`, etc.).

## 11. Configuración y recuperación
**Construido**: `.env.example` ya documenta, sin valores reales, cada
variable necesaria para reconstruir el entorno — Django
(`DJANGO_SECRET_KEY`/`DJANGO_ALLOWED_HOSTS`/
`DJANGO_CSRF_TRUSTED_ORIGINS`), base de datos (`DB_ENGINE`/`DB_NAME`/
`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`), correo
(`EMAIL_BACKEND`/`DEFAULT_FROM_EMAIL`), PayPal/Billing
(`PAYPAL_ENVIRONMENT`/`PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`/
`PAYPAL_WEBHOOK_ID` — nunca `PAYPAL_ACCESS_TOKEN`, que no existe por
diseño, ver `docs/paypal.md`), `REDIS_URL` (reservada, sin uso real
todavía) y `APP_BASE_URL`. `.env` real está excluido de Git en todo
el proyecto (nunca commiteado, verificado desde FASE 1).
**Pendiente en FASE 20**: procedimiento documentado paso a paso para
reconstruir la configuración completa (PostgreSQL, storage, dominio/
hosts cuando aplique en FASE 21, secretos, PayPal) a partir de una
máquina nueva — nunca incluir un secreto real sin protección en ese
procedimiento.

## 12. Secrets
**Pendiente en FASE 20**: separar explícitamente los datos del
sistema (contenido del backup de base de datos/media) de los
secretos de infraestructura (`.env` real) — una política de custodia
segura y separada para los segundos, nunca guardados junto al backup
de datos ni en el mismo canal de distribución.

## 13. RPO / RTO
**Propuesta inicial, no una decisión empresarial definitiva** (el
negocio todavía no ha fijado valores — per `docs/phases/PHASE-20-backups.md`
sección 15, se documenta un punto de partida razonable a validar en
la implementación real): RPO propuesto de 24 horas (backup diario
completo, alineado con la cadencia diaria/semanal/mensual de
retención de la sección 6) y RTO propuesto de algunas horas en un VPS
de un solo proceso (Hostinger, FASE 21) — ambos sujetos a medición
real una vez exista un restore drill (sección 14) que los valide o
los corrija.

## 14. Disaster Recovery Runbook
**Pendiente en FASE 20**: procedimiento reproducible completo —
identificar el incidente, proteger la evidencia, aprovisionar el
entorno, instalar PostgreSQL, restaurar la base de datos, restaurar
media, configurar el entorno (`.env`), ejecutar `migrate`/`check`,
verificar integridad, correr un smoke funcional y habilitar el
servicio. Debe quedar documentado como pasos ejecutables, no como
descripción general.

## 15. Restore Drill
**Pendiente en FASE 20**: ejecutar al menos un restore completo real
con datos de prueba representativos, dejando evidencia real de
backup, checksum, duración, restauración y verificación — nunca un
resultado inventado o asumido.

## 16. Failure Testing
**Pendiente en FASE 20**: probar backup fallido, credenciales
inválidas, almacenamiento no disponible, archivo corrupto, checksum
incorrecto, restore incompleto y espacio insuficiente cuando sea
simulable de forma real. Un backup fallido nunca debe poder marcarse
como válido.

## 17. Monitoring / Notifications
**Pendiente en FASE 20**: detección de backup fallido, verificación
fallida, almacenamiento lleno, backup demasiado antiguo y off-site no
disponible. Puede quedar preparado para monitorización futura (sin
inventar infraestructura de alertas nueva no aprobada) sin bloquear
el resto de la fase.

## 18. Seguridad
**Construido (heredado de FASE 18, aplica también aquí)**: ningún
directorio de media se sirve públicamente hoy (`MEDIA_ROOT`/
`CATALOG_MEDIA_ROOT` fuera de cualquier ruta estática expuesta,
verificado en `docs/security.md`); ninguna credencial de base de
datos vive en el repositorio.
**Pendiente en FASE 20**: revisar permisos de archivos del backup,
ubicación fuera del web root del servidor de producción, ownership,
acceso restringido a administración/plataforma, ausencia total de
descarga pública, logs sin secretos, cifrado y retención — un backup
nunca debe quedar públicamente accesible.

## 19. Multi-Tenant / platform isolation
**Construido (doctrina ya vigente, aplica directamente a esta fase)**:
un backup completo de `erp_saas_dev` contiene, por diseño, los datos
de TODOS los tenants a la vez (la separación multi-tenant es una
columna `tenant_id` dentro de la misma base, no bases separadas por
tenant, ver `ARCHITECTURE.md`) — el acceso a un backup es
necesariamente de plataforma/infraestructura.
**Pendiente en FASE 20**: verificar y documentar explícitamente que
ningún usuario tenant (ni siquiera `OWNER`) puede iniciar, descargar o
acceder a un backup global — la operación de backup/restore es
exclusiva de quien administra la infraestructura, nunca expuesta en
ninguna UI de tenant ni de Super Admin de negocio (`apps.billing`
Super Admin administra Billing, no infraestructura — dominios
distintos, mismo criterio que separa Billing de RRHH en `CLAUDE.md`).

## 20. Performance
**Pendiente en FASE 20**: medir duración, tamaño, compresión y
duración del restore con datos reales — evitar impacto innecesario
sobre operaciones comerciales (ej. evaluar si un backup en horario de
menor actividad es necesario una vez el proyecto tenga datos de
producción reales en FASE 21+).

## 21. Naming y automatización
**Pendiente en FASE 20**: esquema de nombres consistente para los
archivos de backup (ej. `erp_YYYYMMDD_HHMMSS.dump` + su checksum, sin
incluir secretos en el nombre) y, si se construye un script,
idempotente, con manejo de errores y códigos de salida correctos,
logs seguros, verificación de espacio disponible, checksum, aplicación
de retención y protección explícita del último backup válido.

## 22. Restore Version Compatibility
**Construido (hecho verificado, no una decisión)**: la versión real
de PostgreSQL de este entorno es 18.6 (`docs/postgresql.md`).
**Pendiente en FASE 20**: registrar la versión de PostgreSQL y el
formato de backup usados en cada backup real, y documentar la
compatibilidad esperada — nunca asumir compatibilidad universal con
una versión futura de PostgreSQL todavía no probada.

## 23. Tests y Smoke Test
**Pendiente en FASE 20**: tests automatizados para checksum,
retención, backup inválido, verificación de restore, manejo de
fallas, control de acceso y fuga de secretos, combinados con un
restore/smoke real (crear datos de prueba → backup real → checksum →
restore a una base aislada → `manage.py check` → `makemigrations
--check --dry-run` → verificar datos → verificar media → smoke
funcional) — mismo estándar de evidencia real ya exigido en FASE 8–19
(nunca un resultado de prueba inventado o asumido).

## Qué NO se construye con este documento
Esta sincronización es exclusivamente documental — no crea ningún
script de backup, no ejecuta ningún `pg_dump` fuera de los ya
disponibles manualmente por el usuario en pgAdmin 4, no cambia
`config/settings.py` ni ninguna infraestructura, y no implementa
ninguno de los 20 puntos "Pendiente en FASE 20" listados arriba. La
implementación real de todos ellos, con evidencia (comandos
ejecutados, checksums reales, duración medida, restore drill
ejecutado) queda para cuando el usuario autorice explícitamente
FASE 20 — ver `docs/phases/PHASE-20-backups.md` para el checklist
completo y los criterios de aceptación.
