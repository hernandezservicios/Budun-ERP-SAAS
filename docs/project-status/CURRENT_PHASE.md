# Estado actual del proyecto

```text
Fase actual: 1
Estado: PASS (cerrada, pendiente de autorización para FASE 2)
Última fase cerrada: FASE 1 — Project Foundation
Próxima acción: esperar autorización explícita del usuario para iniciar FASE 2 — PostgreSQL Foundation
```

## Regla
Claude debe actualizar este archivo al inicio y al cierre de cada fase.

## Resumen de FASE 1
Proyecto Django creado (`config/` como paquete de settings, apps en `apps/`, app `core` de fundación con una página de verificación en español). Entorno virtual `.venv` creado e instalado con `requirements.txt` (Django 5.2.17, psycopg 3.3.4 con rueda binaria, djangorestframework 3.18.0, python-dotenv, gunicorn). `.env` local creado a partir de `.env.example` con `SECRET_KEY` real generado y `DB_PASSWORD` en placeholder (la contraseña real de PostgreSQL se define en FASE 2). `python manage.py check` en verde y `python manage.py test` en verde (3/3, usando `SimpleTestCase` porque la vista no toca base de datos). El arranque HTTP completo (`runserver`) se verificó con una base de datos SQLite **temporal y explícita** (permitido por CLAUDE.md solo como herramienta de prueba puntual) porque la conexión real a PostgreSQL requiere el usuario/contraseña de aplicación que se crea en FASE 2; con la configuración oficial (PostgreSQL), `runserver` fallará hasta que FASE 2 cree la base de datos y el usuario reales — esto es esperado y no es un defecto. Detalle completo en `docs/phases/PHASE-01-project-foundation.md`.
