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

Registrados durante FASE 3 (no bloqueantes para cerrar la fase):

10. **Se reseteó el esquema `public` de `erp_saas_dev`** (10 tablas vacías de FASE 2, sin ningún dato real) para poder fijar `AUTH_USER_MODEL = "accounts.User"` antes de la primera migración — Django no permite cambiarlo después sin una migración manual compleja. Acción confirmada explícitamente por el usuario antes de ejecutarse (el sistema la bloqueó como destructiva hasta recibir esa confirmación). Sin pérdida de información real.
11. **Bug de doble-importación de módulos**: insertar `apps/` en `sys.path` (como se hizo en FASE 1) junto con que `apps/` tuviera `__init__.py` provocaba que Django `test` discovery importara los modelos dos veces bajo rutas distintas (`tenants.models` vs `apps.tenants.models`), causando `RuntimeError: ... doesn't declare an explicit app_label`. Se corrigió usando la ruta completa (`apps.accounts`, `apps.tenants`, `apps.core`) de forma consistente en `INSTALLED_APPS`, `MIDDLEWARE` y `config/urls.py`, y eliminando el `sys.path.insert` de `settings.py`. Django deriva automáticamente la etiqueta corta (`accounts`, `tenants`, `core`) del último segmento de esa ruta, así que `AUTH_USER_MODEL` y los `related_name` no cambiaron.
12. **El modelo `IsolationSample` (app `tenants`) no es una entidad de negocio**: existe únicamente para poder probar `TenantScopedModel`/`TenantManager` con datos reales en PostgreSQL. No se expone en ninguna vista ni URL. Los modelos de negocio reales (desde FASE 8) heredarán de `TenantScopedModel` directamente.

Registrados durante FASE 4 (no bloqueantes para cerrar la fase):

13. **Se eliminó el campo `username` de `accounts.User`** para pasar a login por correo electrónico (`USERNAME_FIELD = "email"`). Se verificó que había 0 usuarios reales antes de aplicar la migración — sin pérdida de datos. Ver `docs/authentication.md`.
14. **Bug real encontrado durante el desarrollo**: el redirect post-login intentaba usar `request.tenant`, pero `TenantMiddleware` calcula ese valor ANTES de que la vista autentique al usuario (en la misma request), así que siempre daba `None` para un usuario que en realidad sí tenía tenant. Detectado por un test que falló (`test_login_correcto_redirige_a_perfil_si_ya_tiene_tenant`) y corregido resolviendo el tenant con una consulta fresca a `Membership` en la propia vista, no leyendo `request.tenant`.
15. **Los tests de FASE 3 (`apps/tenants/tests.py`) usaban `create_user(username=...)`**, parámetro que ya no existe tras el cambio anterior. Se corrigieron las 5 llamadas afectadas sin tocar la lógica de ninguna prueba; los 16 tests de aislamiento siguen verificando exactamente lo mismo que en FASE 3.
16. **Sin verificación de email al registrarse, sin rate limiting en login, y sin selector de tenant para usuarios con múltiples membresías**: deliberadamente fuera de alcance de FASE 4 (ver "Pendiente" en `docs/authentication.md`). El rate limiting es alcance natural de FASE 18 — Security Hardening.
17. **`EMAIL_BACKEND=console` en desarrollo**: los correos de recuperación de contraseña se imprimen en la terminal/log, no se envían realmente. Un proveedor SMTP real para producción es una decisión de FASE 21 — Hostinger Deployment.

Registrados durante FASE 5 (no bloqueantes para cerrar la fase):

18. **Bug real encontrado durante el desarrollo**: `layout_app.html` usaba `{{ request.user.get_full_name|default:request.user.email }}`; con un visitante anónimo (la página `/estilo/` es pública a propósito) el argumento `request.user.email` fallaba al resolverse por completo y Django rompía el render (a diferencia de una variable simple, que se sustituye silenciosamente por vacío). Se corrigió con `{% firstof request.user.get_full_name request.user.email "Invitado" %}`. Ver `docs/design-system.md`.
19. **Solo dos breakpoints responsive reales** (≤1024px y ≤640px), no cuatro distintos para "Desktop/Laptop/Tablet/Mobile" como se pidió literalmente: Desktop y Laptop comparten el layout expandido porque no hay todavía ninguna diferencia de contenido real que justifique un tercer breakpoint. Documentado explícitamente en `docs/design-system.md` en vez de simular una granularidad inexistente.
20. **El componente Paginación es puramente presentacional**: no hay todavía ninguna lista real paginada en el sistema (los módulos de negocio llegan en FASE 8+). Queda listo para conectarse al `Paginator` de Django cuando se necesite.
21. **La página `/estilo/` (Design System) es pública** (sin login) a propósito, para poder verificarla con smoke tests HTTP simples sin necesitar una sesión autenticada. No expone ningún dato real, solo componentes con datos de ejemplo.
