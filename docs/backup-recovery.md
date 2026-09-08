# Backup y Recuperación

> **Estado: FASE 20 — Backups + Disaster Recovery ejecutada.** Este
> documento es la referencia CONSOLIDADA de backup/recuperación de
> todo el proyecto: para cada categoría marca **Construido** (con
> evidencia real — comandos ejecutados, tamaños, duraciones, checksums,
> conteos verificados) y, cuando aplica, **Pendiente / diferido** (con
> la razón explícita, nunca un descuido). El detalle completo con
> números reales del restore drill de cierre vive en el reporte de
> cierre entregado al usuario; este documento resume el estado final.
> Checklist de 31 secciones con evidencia marcada en
> `docs/phases/PHASE-20-backups.md`.

## 1. Estrategia (tres componentes, nunca solo la base de datos)
**Construido**: los tres componentes existen como comandos
independientes, cada uno con su propio backup/restore/verificación —
nunca se asume que uno cubre a los otros:

```text
Database Backup (apps.backups, pg_dump/pg_restore reales)
+
Application Files / Media Backup (media-private/ y catalog-media/, SIEMPRE por separado)
+
Configuration Recovery (documentado — .env nunca se respalda automáticamente, ver sección 12)
```

`python manage.py backup_all` ejecuta los dos primeros en un solo
comando (pensado para invocarse desde el scheduler del sistema
operativo, ver sección 9); `python manage.py disaster_recovery_drill`
ejecuta y verifica los tres extremo a extremo en una sola corrida.

## 2. PostgreSQL
**Construido**: `apps.backups.services.database.run_pg_dump` invoca
`pg_dump` real (formato `custom`, `-F c` — soporta restore selectivo y
compresión nativa, el formato recomendado por la documentación oficial
de PostgreSQL para uso con `pg_restore`, a diferencia del `.sql` plano
pensado para inspección humana) contra PostgreSQL 18.6
(`erp_saas_dev`, rol `erp_saas_app`). La contraseña viaja SOLO por la
variable de entorno `PGPASSWORD` del subproceso — nunca como argumento
de línea de comandos ni en ningún log (verificado con un test que
fuerza credenciales inválidas y confirma que la contraseña nunca
aparece en el mensaje de error). Cada backup registra fecha/hora
(consciente de zona horaria, `django.utils.timezone.now()`), base,
versión real de PostgreSQL (`SHOW server_version`), tamaño, duración,
checksum y ubicación relativa — nunca la ruta absoluta del servidor —
en un `.meta.json` sidecar y en el modelo `BackupRun` (ver sección
17). Evidencia real de cierre: backup de `erp_saas_dev` → 641 085
bytes, 0.92 s, checksum SHA-256 real.

## 3. Restore real
**Construido**: `restore_database`/`disaster_recovery_drill` ejecutan
un restore REAL — nunca `pg_restore --list`. Flujo real: backup ya
generado → `create_isolated_database` crea una base NUEVA con nombre
generado (`erp_saas_dev_restorecheck_<timestamp>`, siempre con el
marcador `_restorecheck_`, rechazado explícitamente si falta — ver
`UnsafeDatabaseNameError`) → `pg_restore` real hacia esa base aislada
→ verificación real (sección 4) → `drop_isolated_database` la elimina
al terminar. La base principal de desarrollo (`erp_saas_dev`) NUNCA se
destruye ni se sobrescribe — solo se lee (vía `pg_dump`). Evidencia
real de cierre: restore de un backup de 641 KB → base aislada
`erp_saas_dev_restorecheck_20260908095752` → 9.91 s → eliminada al
terminar (confirmado: una consulta posterior a esa base falla, no
queda ningún rastro).

## 4. Restore verification
**Construido**: `apps.backups.services.verification.verify_restored_database`
cuenta filas REALES con SQL directo (`psycopg`, `SELECT COUNT(*)`
sobre la tabla física de cada modelo — nunca a través del manager de
Django, ver el porqué en la sección "Decisión de diseño" más abajo)
sobre 15 tablas representativas de cada dominio explícitamente
nombrado en la especificación de fase (tenants, usuarios/membresías,
categorías, productos, movimientos de stock, unidades serializadas,
ventas, pagos, compras, gastos, RRHH, nómina, contabilidad, Billing,
auditoría) más `django_migrations` (confirma que las migraciones están
realmente aplicadas, no solo que las tablas existen). Los conteos se
comparan contra un snapshot tomado al momento del backup
(`counts_at_backup` en el `.meta.json`) — una discrepancia se reporta
explícitamente (`mismatches`), nunca se oculta. Nunca se declara
`VERIFIED` solo porque `pg_restore` terminó con exit code 0: un
`pg_restore --no-owner --no-privileges` real puede devolver código
distinto de cero por advertencias no fatales (objetos que ya no
aplican) — la verificación real de conteos es la que decide. Evidencia
real de cierre: 73 migraciones aplicadas, 15/15 tablas con conteo
idéntico al esperado, 0 discrepancias.

## 5. Integridad y checksum
**Construido**: SHA-256 (`apps.backups.services.checksum`, mismo
algoritmo ya usado en el proyecto para `ApiKey`/`Integration` en
`apps.api.crypto`) calculado inmediatamente después de cada backup,
sidecar `.sha256` en formato compatible con `sha256sum` de línea de
comandos. Verificado ANTES de cualquier restore (`perform_database_restore_drill`
rechaza con `stage="checksum"` sin siquiera intentar crear una base
si el checksum no coincide o no existe sidecar). Prueba de corrupción
real: copiar un backup real, alterar un byte, confirmar que la
verificación falla con el checksum exacto esperado/real en el mensaje
— y que el archivo original permanece intacto.

## 6. Retention
**Construido**: `apps.backups.services.retention` — ventanas diaria/
semanal/mensual (`BACKUP_RETENTION_DAILY_DAYS`/`_WEEKLY_WEEKS`/
`_MONTHLY_MONTHS`, configurables por entorno, 7/4/12 por defecto), un
representante por semana ISO y por mes calendario fuera de la ventana
diaria. El backup válido MÁS RECIENTE nunca se borra, incondicionalmente
— incluso si es el ÚNICO backup y tiene 400 días de antigüedad (probado
explícitamente). Los backups `FAILED` nunca participan de la
clasificación (el propio comando que falla limpia su archivo parcial
de inmediato, ver sección 21) — la retención nunca tiene que decidir
sobre un backup roto. `python manage.py cleanup_backups --dry-run`
reporta qué se eliminaría sin borrar nada; sin `--dry-run` aplica de
verdad. Fallo real de eliminación (permiso denegado, archivo bloqueado)
se reporta en `RetentionReport.errors` sin interrumpir el resto del
proceso — un backup que no se pudo borrar nunca se declara eliminado.

## 7. Scheduling
**Construido (comando) / documentado (instalación del scheduler)**:
`python manage.py backup_all` es el ÚNICO comando que un scheduler
del sistema operativo necesita invocar — base de datos + media privada
+ media de catálogo, en ese orden, con exit code correcto
(`CommandError` → código de salida distinto de cero) para que el
scheduler detecte un fallo. Nunca depende de `runserver` ni de un
proceso Django persistente (mismo criterio que ya descartó Celery/
Redis para las tareas de cron de `apps.billing` en FASE 17).

**Windows (desarrollo)** — Task Scheduler, ejemplo real con las rutas
de este entorno:
```text
schtasks /create /tn "ERP Backup Diario" /sc daily /st 02:00 ^
  /tr "\"C:\Budun ERP SAAS\.venv\Scripts\python.exe\" \"C:\Budun ERP SAAS\manage.py\" backup_all" ^
  /ru SYSTEM
```

**Linux (producción, FASE 21 — Hostinger)** — cron o systemd timer,
ejemplo documentado (no instalado en este entorno, no es un VPS):
```text
# crontab -e (usuario de la aplicación, nunca root)
0 2 * * * /opt/erp-saas/.venv/bin/python /opt/erp-saas/manage.py backup_all >> /var/log/erp-backup.log 2>&1
```
```ini
# /etc/systemd/system/erp-backup.timer (alternativa a cron)
[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
```
No se instaló ningún scheduler real en este entorno de desarrollo
Windows (no hay `cron`, y una tarea diaria de Task Scheduler no aporta
valor en una máquina de desarrollo que no está siempre encendida) — la
instalación real en producción es responsabilidad de FASE 21
(Hostinger Deployment), fuera del alcance explícito de esta fase.

## 8. Local + Off-site
**Construido**: `apps.backups.services.offsite.LocalOffsiteAdapter`
copia (real, `shutil.copy2`, probado) el backup ya generado a un
SEGUNDO directorio configurable vía `BACKUP_OFFSITE_ROOT` (típicamente
otro disco/punto de montaje) — nunca reemplaza la copia local, siempre
además de ella. `CloudOffsiteAdapter` es una interfaz PLACEHOLDER
documentada a propósito (lanza `NotImplementedError` con un mensaje
explícito) para cuando el negocio apruebe un proveedor externo real
(S3/GCS/Azure/Backblaze) — no se inventa ninguno aquí. La copia
off-site es SIEMPRE best-effort: un fallo ahí (probado con un `OSError`
forzado) nunca marca como fallido el backup local ya generado con
éxito. Sin `BACKUP_OFFSITE_ROOT` configurado (el caso de este entorno
de desarrollo), cada backup queda claramente marcado
`offsite_ok=False` con el motivo — nunca se finge una copia externa
que no ocurrió. Un backup nunca se expone vía HTTP (esta app no
declara ningún `urls.py`/vista, verificado con un test).

## 9. Cifrado
**Construido (opcional)**: `apps.backups.services.encryption` usa
`openssl enc -aes-256-cbc -pbkdf2 -salt` (herramienta estándar del
sistema, ya parte del stack vía Git para Windows en desarrollo y del
paquete `openssl` de cualquier VPS Linux real, necesario para SSL/
Nginx per `CLAUDE.md` — nunca una dependencia Python nueva ni
criptografía propia) — probado con un round-trip real (cifrar →
descifrar → bytes idénticos) y con rechazo real de una clave
incorrecta. La clave (`BACKUP_ENCRYPTION_KEY`, variable de entorno) se
pasa a `openssl` por STDIN, nunca como argumento de línea de comandos
ni en ningún archivo dentro de `BACKUP_ROOT` — verificado con un test
que confirma que la clave nunca aparece en el `.meta.json`. Sin
`BACKUP_ENCRYPTION_KEY` configurada (el caso de este entorno de
desarrollo), cada backup queda `encrypted=false` con una nota
explícita — nunca se finge un cifrado que no ocurrió. Gestión de
clave: vive únicamente en `.env` (excluido de Git) o en un gestor de
secretos de plataforma en producción, nunca junto al backup que
protege.

## 10. Media y archivos (uploads)
**Construido**: `backup_media`/`apps.backups.services.media` respaldan
`media-private/` (documentos privados: `CustomerDocument`/
`SupplierDocument`/`InvoiceDocument`/`PaymentProof`) y `catalog-media/`
(`ProductImage`, público) SIEMPRE en archivos `.tar.gz` SEPARADOS —
nunca mezclados, misma disciplina de separación pública/privada que
`docs/security.md` sección "Uploads y media". Cada árbol lleva su
propio checksum SHA-256 y metadata. Un árbol vacío o inexistente
produce un backup de cero archivos, nunca un error. Evidencia real de
cierre: `media-private/` → 165 archivos, 9030 bytes, 0.13 s;
`catalog-media/` → 1 archivo, 314 bytes.

## 11. Media verification
**Construido**: `restore_media`/`disaster_recovery_drill` extraen
SIEMPRE a un directorio AISLADO (nunca sobrescriben `media-private/`/
`catalog-media/` reales en uso) usando `tarfile.extractall(filter="data")`
(rechaza rutas absolutas y `../` — nunca confía en el contenido del
archivo para decidir dónde escribir, mismo criterio ya aplicado a la
importación de productos de FASE 8) y verifica el checksum ANTES de
extraer. `verify_media_restore` compara cantidad de archivos y tamaño
byte a byte entre el árbol original y el restaurado, reportando
explícitamente archivos faltantes/sobrantes/con tamaño distinto.
Evidencia real de cierre: ambos árboles restaurados a un directorio
temporal aislado, 0 diferencias (165/165 y 1/1 archivos, tamaños
idénticos). Nunca se expone ningún archivo restaurado durante la
prueba (directorio temporal fuera de cualquier ruta servida,
eliminado al terminar el proceso).

## 12. Configuración y recuperación
**Construido**: `.env.example` documenta, sin valores reales, cada
variable necesaria para reconstruir el entorno — Django, base de
datos, correo, PayPal/Billing, y las nuevas de esta fase
(`BACKUP_ROOT`/`BACKUP_RETENTION_*`/`BACKUP_MIN_FREE_BYTES`/
`BACKUP_ENCRYPTION_KEY`/`BACKUP_OFFSITE_ROOT`, todas opcionales con
valores por defecto sensatos). El procedimiento de reconstrucción
completo vive en el Disaster Recovery Runbook (sección 14). `.env`
real está excluido de Git en todo el proyecto (verificado desde
FASE 1) y ningún comando de esta fase lo lee ni lo copia — verificado
con un test que confirma que `MEDIA_ROOT`/`CATALOG_MEDIA_ROOT` nunca
coinciden con la raíz del proyecto (donde vive `.env`).

## 13. Secrets
**Construido (disciplina de código, verificada con tests)**: ningún
comando de esta fase respalda `.env`, contraseñas, API secrets o
tokens OAuth — el backup de base de datos solo contiene lo que
`pg_dump` extrae de PostgreSQL (que nunca almacena `DJANGO_SECRET_KEY`/
`PAYPAL_CLIENT_SECRET`/etc., variables de entorno de plataforma) y el
backup de media solo contiene los dos árboles de archivos declarados.
La contraseña de base de datos y `BACKUP_ENCRYPTION_KEY` nunca
aparecen en `BackupRun.error_message` ni en ningún `.meta.json` —
verificado con tests dedicados que fuerzan un fallo con credenciales
reales de prueba y confirman su ausencia en cualquier salida
persistida.

## 14. RPO / RTO
**Propuesta inicial, no una decisión empresarial definitiva** (el
negocio todavía no ha fijado valores, per `docs/phases/PHASE-20-backups.md`
sección 15): RPO propuesto de 24 horas (backup diario, alineado con la
cadencia diaria/semanal/mensual de retención). RTO: el restore drill
real de cierre midió ~10-12 segundos para restaurar la base completa
de desarrollo (641 KB, 73 migraciones, ~200 filas totales en las 15
tablas críticas) más ~1 segundo para ambos árboles de media — **estas
cifras son de un dataset de desarrollo, no de producción a escala**,
y se citan como punto de partida medido, no como el RTO real de
producción. Un RTO propuesto de un par de horas para un VPS de un
solo proceso (Hostinger, FASE 21) es razonable como primera
aproximación (provisionar el entorno + restaurar + verificar +
habilitar el servicio), sujeto a re-medición contra un dataset de
producción real cuando exista.

## 15. Disaster Recovery Runbook
**Construido** — procedimiento reproducible real:
1. Identificar el incidente y su alcance (¿solo datos? ¿también
   media? ¿corrupción parcial?).
2. Preservar evidencia: copiar el estado actual (si es recuperable)
   antes de tocar nada.
3. Provisionar el entorno (VPS/máquina nueva).
4. Instalar PostgreSQL (misma versión mayor que generó el backup —
   ver sección 22) + Python/virtualenv + dependencias
   (`pip install -r requirements.txt`).
5. Restaurar `.env` desde el mecanismo de custodia de secretos
   (nunca desde el propio backup — sección 13).
6. `createdb` + `pg_restore --no-owner --no-privileges <backup>.dump`
   sobre la base real (no una aislada — este es el escenario de
   desastre real, a diferencia del restore drill de verificación).
7. Restaurar media: `restore_media --backup <archivo> --target-dir <MEDIA_ROOT real>`
   para cada árbol.
8. `python manage.py migrate` + `python manage.py check`.
9. `python manage.py backup_health` + verificación manual de conteos
   representativos (mismo principio que la sección 4).
10. Smoke funcional: login, ver un producto, ver una venta.
11. Habilitar el servicio (Gunicorn/Nginx en producción).
12. Monitorizar de cerca las primeras horas.
Nunca se ejecuta este procedimiento de forma destructiva sobre
producción como prueba — el restore DRILL (sección 16) es la forma
segura de practicarlo, siempre contra una base/directorios aislados.

## 16. Restore Drill
**Construido, con evidencia real de cierre** —
`python manage.py disaster_recovery_drill` ejecuta el ciclo completo
en un solo comando: backup de base de datos real → checksum → restore
a base aislada real → verificación de 15 tablas + migraciones → backup
de ambos árboles de media → restore a directorios aislados →
verificación de archivos — y termina con `CommandError` (exit code
distinto de cero) si cualquier paso falla. Resultado de la corrida de
cierre: **TODO OK** — ver secciones 2-4 y 10-11 para las cifras reales
exactas.

## 17. Failure Testing
**Construido, con tests reales** (no simulacros hipotéticos): 
credenciales de base de datos inválidas (`BackupFailedError`, sin
dejar `.dump` parcial, sin filtrar la contraseña); host/puerto
inalcanzable; espacio en disco insuficiente (`InsufficientStorageError`,
simulado vía `shutil.disk_usage` per lo que la propia especificación
permite — "cuando sea razonablemente simulable"); backup corrupto/
checksum incorrecto (byte alterado real, detectado); restore de un
dump truncado (verificación real reporta `ok=False`, nunca declara
éxito); fallo de eliminación durante retención (`OSError` real
capturado, reportado, el backup no desaparece de "conservados"). Ningún
escenario probado permite que una operación fallida se reporte como
exitosa.

## 18. Monitoring / Notifications
**Construido (el dato) / diferido (el canal de alerta)**:
`BackupRun` (modelo, plataforma — no tenant-scoped, mismo criterio que
`AuditLog`/`PayPalTransaction`) registra cada ejecución (tipo,
resultado, tamaño, duración, checksum, cifrado, error). 
`apps.backups.services.monitoring.get_backup_health_summary`/
`python manage.py backup_health` detectan backup faltante, fallido o
vencido (más de `max_age_hours`, 30 h por defecto — 24 h de cadencia +
margen) por tipo (base de datos, media privada, media de catálogo) y
terminan con exit code distinto de cero si algo no está al día,
detectable por cualquier scheduler externo sin necesitar
infraestructura de alertas nueva. **Diferido explícitamente**: ningún
canal de notificación real (correo/Slack/webhook) — no está aprobado
ni justificado todavía (mismo criterio que "Redis solo si una fase
posterior demuestra necesidad real" de `CLAUDE.md`); el dato ya queda
preparado para que una integración futura lo consuma.

## 19. Seguridad
**Construido**: `BACKUP_ROOT` vive fuera de `MEDIA_ROOT`/
`CATALOG_MEDIA_ROOT`/cualquier `STATICFILES_DIRS` (verificado con
test) y la app `apps.backups` no declara ningún `urls.py`/`views.py`
en absoluto (verificado con test — ninguna ruta HTTP puede servir un
backup, ni por accidente). En POSIX (producción Linux real), cada
archivo/directorio de backup se restringe a `0600`/`0700` (dueño
únicamente) inmediatamente después de crearse; en Windows (desarrollo)
los permisos POSIX no aplican, se omite en silencio — nunca un error.
Sin fuga de secretos verificada (sección 13). El único acceso a
`BackupRun` es el admin de solo lectura de Django
(`has_add_permission`/`has_change_permission` devuelven `False`,
verificado con test) — nunca la UI principal del proyecto (per
CLAUDE.md), y accesible solo a quien ya tiene acceso al admin
(staff/superusuario de plataforma).

## 20. Multi-Tenant / platform isolation
**Construido**: un backup completo de `erp_saas_dev` contiene, por
diseño, los datos de TODOS los tenants a la vez (la separación
multi-tenant es una columna `tenant_id` dentro de la misma base, ver
`ARCHITECTURE.md`). Esta fase deliberadamente NO agrega ninguna UI ni
endpoint — ni de tenant ni de Super Admin de negocio (`apps.billing`
administra Billing, no infraestructura, dominios distintos, mismo
criterio que separa Billing de RRHH en `CLAUDE.md`) — la única
superficie es el comando de gestión (acceso de shell/infraestructura)
y el admin de solo lectura. Ningún usuario tenant puede listar,
iniciar, descargar ni restaurar un backup — no existe ningún camino de
código que lo permita, verificado por la ausencia total de `urls.py`/
vistas en la app (sección 19). Cualquier UI futura de administración
de backups es exclusivamente platform/admin (`is_superuser`), pendiente
de una fase futura si se decide construirla.

## 21. Performance
**Construido, medido con datos reales de este entorno** (no
producción a escala — ver advertencia de la sección 14): backup de
base de datos ~0.5-0.9 s / 640 KB; backup de media privada ~0.1 s /
9 KB (165 archivos); backup de media de catálogo <0.01 s / 314 bytes
(1 archivo); restore completo a base aislada ~10-12 s (dominado por
recreación de esquema/índices, patrón esperado de `pg_restore`);
restore de media ~0.5 s. `ensure_sufficient_disk_space` se verifica
ANTES de escribir cualquier byte, evitando trabajo desperdiciado si no
hay espacio. Ningún backup se ejecuta automáticamente en horario
comercial en este entorno (invocación manual/bajo demanda en
desarrollo); la franja horaria de ejecución programada en producción
es una decisión de FASE 21.

## 22. Naming y automatización
**Construido**: esquema de nombres oficial — `erp_<db>_YYYYMMDD_HHMMSS.dump`
para base de datos, `erp_media_<privada|catalog>_YYYYMMDD_HHMMSS.tar.gz`
para media, cada uno con sidecars `.sha256`/`.meta.json` (y `.enc` si
está cifrado) — nunca un secreto en el nombre. Cada comando
(`backup_database`/`backup_media`) es idempotente en el sentido de que
una ejecución fallida nunca deja un artefacto ambiguo (el `.dump`/
`.tar.gz` parcial se elimina de inmediato si el proceso falla), usa
códigos de salida correctos (`CommandError` → exit code ≠ 0), produce
logs sin secretos, verifica espacio antes de escribir, aplica checksum
siempre, aplica retención automáticamente salvo `--skip-retention`, y
protege el último backup válido incondicionalmente (sección 6).

## 23. Restore Version Compatibility
**Construido**: cada backup registra la versión REAL de PostgreSQL
que lo generó (`postgres_version` en `BackupRun`/`.meta.json`, vía
`SHOW server_version` — 18.6 en este entorno) y el formato (`custom`).
No se asume compatibilidad universal con una versión futura de
PostgreSQL todavía no probada — un restore hacia una versión mayor
distinta deberá verificarse explícitamente cuando llegue ese caso
real (documentado como advertencia, no una garantía inventada).

## 24. Tests y Smoke Test
**Construido**: 88 tests nuevos (`apps/backups/tests/`) — checksum
(determinismo, formato de sidecar, detección de corrupción, nunca
modifica el original), retención (clasificación diaria/semanal/
mensual con datos sintéticos, protección incondicional del último
válido, eliminación real de archivos, `--dry-run`, manejo de fallo de
eliminación), espacio en disco (mockeado per lo permitido), cifrado
(round-trip real con `openssl`, clave incorrecta, `openssl` no
disponible), off-site (copia real a un segundo directorio, fallo
best-effort), backup/restore de base de datos REAL contra PostgreSQL
(`TransactionTestCase`, firma binaria `PGDMP` real, credenciales
inválidas, host inalcanzable, dump truncado, guardas de seguridad
contra nombres de base no aislados), media (tar.gz real, restore
aislado, comparación de archivos), verificación (conteo real con SQL
directo, discrepancias nunca ocultas), orquestación completa
(`services.jobs`, con `BackupRun` real), comandos de gestión
(`call_command` real), monitoring, seguridad (sin superficie HTTP, sin
fuga de secretos, admin de solo lectura) y el modelo. **1241/1241
tests OK en la regresión completa del proyecto** (1153 previos + 88
nuevos, cero fallas reales — mismos 2 tracebacks ya documentados como
esperados/inofensivos). Smoke real: `disaster_recovery_drill` de
cierre (sección 16), sin datos inventados.

## Decisión de diseño: SQL directo, nunca alias dinámico de Django
`count_critical_tables` cuenta filas con `psycopg` directo sobre la
tabla física de cada modelo (`Model._meta.db_table`), nunca a través
del manager de Django (`Model.objects`/`Model.all_objects`) con un
alias de conexión registrado en tiempo de ejecución. Dos razones: (1)
el test runner de Django exige declarar por adelantado cada alias que
un test vaya a usar (`TestCase.databases`), incompatible con un alias
inventado dentro del propio cuerpo del test — encontrado durante la
construcción de la suite de este módulo; (2) SQL directo cuenta TODAS
las filas por construcción, sin depender de ningún `ContextVar` de
tenant activo — evita por diseño, no por disciplina de código, el
bug-class ya documentado repetidas veces en el proyecto
(`KNOWN_ISSUES.md` #90/#95/#97/#108/#118/#120: `Model.objects` fuera
de una request HTTP real siempre devuelve cero filas). Ver
`KNOWN_ISSUES.md`/`DECISIONS.md` de esta fase para el detalle completo.
