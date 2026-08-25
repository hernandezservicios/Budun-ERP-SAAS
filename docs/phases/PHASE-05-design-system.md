# FASE 5 — Design System

## Objetivo
Crear design system y shell visual: layout, sidebar, header, buttons, cards, tables, forms, states. Moderno, profesional, sobrio, legible, azul/verde con neutrales.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] UI responsive — dos breakpoints reales (≤1024px, ≤640px); sidebar colapsa a off-canvas.
- [x] contraste/legibilidad — pares de color verificados manualmente contra WCAG AA (≥4.5:1), ver `docs/design-system.md`.
- [x] componentes consistentes — 19 componentes en un único sistema de tokens, verificables en `/estilo/`.
- [x] no apariencia Django Admin — UI propia completa; Django Admin sigue existiendo solo como herramienta interna de staff.

## Verificación
- [x] `python manage.py check` o la validación equivalente está en verde.
- [x] Tests relevantes ejecutados. — 54/54 (`manage.py test`).
- [x] Smoke test realizado cuando aplique. — `GET` real de `/`, `/cuentas/login/`, `/cuentas/registro/`, `/estilo/`, `/cuentas/perfil/` (redirige).
- [x] Seguridad revisada para el alcance de la fase. — Sin cambios de lógica de negocio; CSRF/sesión intactos; `/estilo/` no expone datos reales.
- [x] Documentación actualizada. — `docs/design-system.md` (nuevo).
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Ver historial de Git.

## Verificación detallada (pedida por el usuario)
1. **Templates** — todas las plantillas de FASE 1/4 migradas al nuevo sistema (`base.html`, `layout_app.html`, auth, perfil); 2 nuevas (404/500).
2. **Componentes** — 19 construidos y visibles en `/estilo/` con datos de ejemplo.
3. **Accesibilidad** — skip link, `:focus-visible` global, ARIA completo en tabs/modales/dropdowns/toasts, `aria-label` en botones de solo-ícono, `prefers-reduced-motion` respetado.
4. **Contraste** — verificado manualmente (fórmula WCAG de luminancia relativa); ver tabla en `docs/design-system.md`.
5. **Consistencia visual** — un único archivo de tokens (`base.css`) consumido por todos los componentes (`design-system.css`).
6. **Responsive** — verificado por CSS (dos breakpoints reales, documentados explícitamente en vez de simular cuatro).
7. **Regresión de FASE 4** — 26 tests de `apps/accounts` sin cambios de lógica, todos en verde.
8. **Regresión de FASE 3** — 16 tests de `apps/tenants` sin cambios de lógica, todos en verde.
9. **Tests** — 54/54 OK (9 nuevos de Design System/accesibilidad/error pages).
10. **Django check** — sin errores.
11. **Smoke test HTTP** — realizado sobre `runserver` real, no solo el test client.
12. **Documentación** — `docs/design-system.md`, `CURRENT_PHASE.md`, `PHASE_HISTORY.md`, `KNOWN_ISSUES.md`.
13. **Git commit** — ver historial de Git.

## Evidencia (FASE 5)
- Bug real encontrado y corregido: `{% firstof %}` en vez de `|default:` con un argumento que fallaba para usuarios anónimos (ver `docs/design-system.md`).
- Página de referencia pública `/estilo/`, usada como evidencia real (no una maqueta separada) para verificar los 19 componentes.
- Ningún módulo de negocio (productos, inventario, ventas, POS, compras, gastos, reportes, API, PayPal, Billing) fue construido. El componente Cards existe pero no se usó como patrón dominante en ninguna página.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 6 — Landing + Pricing.
