# Estado actual del proyecto

```text
Fase actual: 0
Estado: PASS (cerrada, pendiente de autorización para FASE 1)
Última fase cerrada: FASE 0 — Auditoría del entorno
Próxima acción: esperar autorización explícita del usuario para iniciar FASE 1 — Project Foundation
```

## Regla
Claude debe actualizar este archivo al inicio y al cierre de cada fase.

## Resumen de FASE 0
Entorno Windows auditado. PostgreSQL 18 instalado y en ejecución (puerto 5432), pgAdmin 4 instalado, Python 3.14.4, Git 2.55, Node 25.9/npm 11.12 disponibles, sin Docker/MySQL/WAMP en uso. Repositorio Git ya inicializado (rama `main`, sin commits) con `user.name`/`user.email` globales configurados. No se creó `manage.py`, `.venv` ni ningún módulo ERP: eso corresponde a FASE 1 en adelante. Detalle completo en `docs/phases/PHASE-00-auditoría-del-entorno.md` (checklist marcado) y en el reporte entregado en el chat.
