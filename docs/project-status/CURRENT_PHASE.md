# Estado actual del proyecto

```text
Fase actual: 6
Estado: PASS (cerrada, pendiente de autorización para FASE 7)
Última fase cerrada: FASE 6 — Landing + Pricing
Próxima acción: esperar autorización explícita del usuario para iniciar FASE 7 — Dashboard
```

## Regla
Claude debe actualizar este archivo al inicio y al cierre de cada fase.

## Resumen de FASE 6
Se construyó la landing pública en `/` (reemplazando la página de verificación de FASE 1), con las 10 secciones pedidas (propuesta de valor, audiencia, problemas, módulos, cómo funciona, ventajas, seguridad, integración API/IA presentada como "Próximamente", precios, FAQ) usando exclusivamente el Design System de FASE 5. Los precios vienen de una única fuente configurable (`apps/core/pricing.py`, valores placeholder pendientes de decisión real de negocio) y se verificó con un test que ningún monto se duplica en otras plantillas. Se agregó SEO básico (meta description, Open Graph) como bloques reutilizables en `base.html`. FAQ implementado con `<details>/<summary>` nativos (accesible sin JS). Ninguna API ni PayPal funcional fue construida — solo se presentan como capacidad futura. 60/60 tests OK (regresión de FASE 3/4/5 sin cambios de lógica + nuevos de landing/pricing). `manage.py check` en verde. Smoke tests HTTP reales. Documentado en `docs/landing.md`.
