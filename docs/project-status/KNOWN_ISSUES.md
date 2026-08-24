# Problemas conocidos

Registrados durante FASE 0 (no bloqueantes para cerrar la fase):

1. **Python 3.14.4 es la única versión instalada localmente**, mientras que `.github/workflows/tests.yml` usa Python 3.12 en CI. No se detectó ningún bloqueo real: se verificó (vía `pip download`, sin instalar) que Django 5.2.17, psycopg 3.3.4 (incluida la rueda binaria `psycopg_binary-3.3.4-cp314-cp314-win_amd64.whl`), djangorestframework 3.18.0, python-dotenv y gunicorn tienen paquetes compatibles con Python 3.14 en Windows. Aun así, dado que Python 3.14 es muy reciente, conviene tenerlo presente si aparece algún comportamiento inesperado al crear el entorno virtual en FASE 1; alinear la versión local con la de CI (o viceversa) es una decisión pendiente del usuario, no un error actual.
2. ~~**pgAdmin 4 no fue abierto ni verificado visualmente por Claude**~~ — **RESUELTO EN FASE 2**: el usuario abrió pgAdmin 4, se conectó al servidor `PostgreSQL 18` y creó la base de datos y el rol de aplicación directamente ahí.
3. ~~**No se probó una conexión autenticada real a PostgreSQL**~~ — **RESUELTO EN FASE 2**: Django ya se conecta correctamente a `erp_saas_dev` con el rol `erp_saas_app`.
4. **`psql` no estaba en el PATH del sistema**; se corrigió agregando `C:\Program Files\PostgreSQL\18\bin` al PATH de usuario (no al PATH de sistema, y sin usar `setx` para evitar el riesgo de truncado). Las terminales abiertas antes de este cambio no lo verán hasta reiniciarse.

Registrados durante FASE 1 (no bloqueantes para cerrar la fase):

5. ~~**`python manage.py runserver` y `python manage.py test` no funcionan todavía con la configuración oficial (PostgreSQL)**~~ — **RESUELTO EN FASE 2**: ambos funcionan contra PostgreSQL real.
6. ~~**`DB_PASSWORD=change-me` en `.env`**~~ — **RESUELTO EN FASE 2**: `.env` tiene la contraseña real, configurada por el usuario directamente en el archivo, nunca compartida por chat.

Registrados durante FASE 2 (no bloqueantes para cerrar la fase):

7. **El rol `erp_saas_app` inicialmente se creó sin el privilegio `CREATEDB`**, lo que impedía a `manage.py test` crear su base de datos de pruebas efímera (error: "se ha denegado el permiso para crear la base de datos"). Se corrigió pidiéndole al usuario ejecutar `ALTER ROLE erp_saas_app CREATEDB;` en pgAdmin 4. Ya verificado y funcionando.
8. **La contraseña elegida por el usuario para `erp_saas_app` es corta y de baja complejidad** (uso exclusivamente local, no expuesto a Internet, `pg_hba.conf` ya exige `scram-sha-256`). No es bloqueante para desarrollo local, pero se recomienda usar una contraseña más robusta antes de FASE 21 (Hostinger Deployment) o al reforzar seguridad en FASE 18. El valor exacto nunca se documenta en el repositorio, solo vive en `.env` (no commiteado).
9. **La verificación visual de las tablas de `erp_saas_dev` en el árbol de pgAdmin 4 (clic en Schemas → public → Tables) queda como confirmación opcional del usuario**; Claude ya verificó las 10 tablas esperadas mediante una consulta directa a `information_schema.tables` mostrando el mismo resultado.
