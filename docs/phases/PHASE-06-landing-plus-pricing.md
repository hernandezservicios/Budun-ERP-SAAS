# FASE 6 — Landing + Pricing

## Objetivo
Landing pública, features, benefits, FAQ, CTA y pricing inicial conectado a modelos/config.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] Páginas públicas funcionales — landing en `/` con 10 secciones, `GET` real → 200.
- [x] responsive — grids `auto-fit`/`minmax` + breakpoint puntual en ≤640px (ver `docs/landing.md`).
- [x] CTA al registro — botones "Crear cuenta gratis" en hero, cada plan de precios y CTA final, todos apuntando a `accounts:registro`.
- [x] pricing legible — 3 planes en tarjetas, con lista de características y precio destacado en el plan recomendado.

## Verificación
- [x] `python manage.py check` o la validación equivalente está en verde.
- [x] Tests relevantes ejecutados. — 60/60 (`manage.py test`).
- [x] Smoke test realizado cuando aplique. — `GET` real de `/`, `/cuentas/login/`, `/cuentas/registro/`, `/estilo/`.
- [x] Seguridad revisada para el alcance de la fase. — Sin cambios de lógica de negocio/autenticación/tenant; página pública sin datos sensibles.
- [x] Documentación actualizada. — `docs/landing.md` (nuevo).
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Ver historial de Git.

## Verificación detallada (pedida por el usuario)
- **Tests**: 60/60 OK.
- **Regresión FASE 3** (`apps/tenants`, 16 tests) y **FASE 4** (`apps/accounts`, 26 tests): sin cambios de lógica, en verde.
- **Regresión FASE 5** (`apps/core` Design System, 9 tests): sin cambios de lógica, en verde.
- **Django check**: sin errores.
- **Smoke test HTTP**: real, vía `runserver` + curl.
- **Responsive**: grids fluidos + breakpoint en ≤640px; ver limitación documentada en `KNOWN_ISSUES.md` (sin captura de pantalla real).
- **Accesibilidad**: FAQ con `<details>/<summary>` nativos, diagrama API/IA con `role="img"` + `aria-label` descriptivo, iconos decorativos `aria-hidden`, hereda skip link/foco visible de FASE 5.
- **Documentación**: `docs/landing.md`.

## Evidencia (FASE 6)
- Precios: única fuente de datos (`apps/core/pricing.py`), verificado con test que escanea todas las plantillas del proyecto.
- SEO: `<meta name="description">`, `og:type`, `og:title`, `og:description` — bloques reutilizables en `base.html` para cualquier página futura.
- Un único `<h1>` y un `<h2>` por sección (verificado con test).
- Integración API/IA presentada explícitamente como "Próximamente" / "Todavía no está disponible" — ninguna API ni PayPal funcional construidos (verificado con test).
- Página de FASE 1 (`core/home.html`) eliminada, reemplazada por `core/landing.html`; URL y nombre de vista sin cambios (nada roto).
- Cards reservado solo para Precios; el resto de secciones usa un grid simple sin bordes/sombra (instrucción explícita del usuario).

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 7 — Dashboard.
