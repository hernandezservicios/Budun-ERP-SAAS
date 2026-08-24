# Estado actual del proyecto

```text
Fase actual: 2
Estado: PASS (cerrada, pendiente de autorización para FASE 3)
Última fase cerrada: FASE 2 — PostgreSQL Foundation
Próxima acción: esperar autorización explícita del usuario para iniciar FASE 3 — Multi-Tenancy
```

## Regla
Claude debe actualizar este archivo al inicio y al cierre de cada fase.

## Resumen de FASE 2
Django ahora se conecta a PostgreSQL real. El usuario creó `erp_saas_dev` (base de datos) y `erp_saas_app` (rol de aplicación, dueño de la base, con `CREATEDB` para tests) directamente en pgAdmin 4, incluyendo la contraseña, que nunca se compartió por chat. `.env` quedó configurado con esas credenciales (archivo local, no commiteado). `python manage.py migrate` aplicó las migraciones estándar de Django (auth, admin, contenttypes, sessions) sin errores. `python manage.py check` en verde. `python manage.py test` corrió 3/3 pruebas usando `TestCase` (ya no `SimpleTestCase`), lo que obliga a Django a crear y destruir una base de datos de pruebas real en PostgreSQL. Smoke test HTTP real (`runserver` con la configuración oficial, sin trucos temporales) devolvió 200 con el contenido esperado en español. Se verificaron las 10 tablas esperadas en el esquema `public` de `erp_saas_dev` (vía consulta directa y pendiente de confirmación visual opcional del usuario en pgAdmin 4). Detalle completo en `docs/phases/PHASE-02-postgresql-foundation.md` y en `docs/postgresql.md`.
