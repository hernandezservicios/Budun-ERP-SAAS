# FASE 9 — Customers + Suppliers

## Objetivo
Módulo profesional y completo de Clientes y Proveedores, preparado para producción, escalabilidad y futuras funciones financieras/comerciales — sin implementar todavía el motor financiero completo de crédito/cuentas por cobrar/pagar.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] CRUD completo — Clientes y Proveedores: crear, editar, visualizar, desactivar/reactivar, búsqueda, búsqueda avanzada, filtros, ordenamiento, paginación, detalle, historial (estado vacío honesto), notas, auditoría.
- [x] tenant isolation — `Customer`/`Supplier`/`CustomerDocument`/`SupplierDocument`/`ActivityLog` heredan `TenantScopedModel`; cobertura de tests explícita de aislamiento A/B.
- [x] validación — identificación fiscal extensible (tipo + número), constraints PostgreSQL (al menos un nombre, tipo si hay número, únicos por tenant), validación de formularios.
- [x] documentos adjuntos — subida/descarga/eliminación con validación de extensión + firma binaria + tamaño (10 MB), nombres de archivo seguros, almacenamiento privado, descarga protegida, sin archivos huérfanos.
- [x] datos comerciales preparados — `payment_terms`, `credit_days`, `credit_enabled`, `currency` (+ `credit_limit`/`commercial_notes` en Cliente) reales; motor financiero (balance/ledger) deliberadamente NO construido.
- [x] auditoría — bitácora `ActivityLog` mínima y acotada a este módulo (creación, edición, desactivación, reactivación, subida/eliminación/descarga de documentos).
- [x] tests pasan — 261/261 (suite completa del proyecto: 86 nuevos de `apps.customers` + regresión de FASE 3-8 sin cambios de lógica de negocio).

## Verificación
- [x] `python manage.py check` está en verde.
- [x] Tests relevantes ejecutados — 261/261 (`apps.customers`: 86 nuevos + regresión de la suite completa del proyecto, FASE 3-8).
- [x] Smoke test HTTP real contra PostgreSQL de desarrollo (crear cliente/proveedor, subir/descargar/eliminar documento, incluyendo archivo disfrazado y extensión prohibida rechazados, desactivar/reactivar, aislamiento cruzado Tenant A/B).
- [x] Seguridad revisada: autorización (`LoginRequiredMixin`+`TenantRequiredMixin`), acceso directo por URL e IDs manipulados (404, nunca 403 que confirme existencia), CSRF (`{% csrf_token %}` en todos los formularios/POST), validaciones de archivo (path traversal, MIME spoofing, extensión falsa, archivos huérfanos), exposición entre tenants.
- [x] Documentación actualizada — `docs/customers.md`, `docs/suppliers.md`, `docs/customer-documents.md`, `docs/supplier-documents.md` (nuevos); FASE 10/11/12/13/14/15 actualizadas con la interfaz que cada una debe consumir.
- [x] `docs/project-status/CURRENT_PHASE.md`, `PHASE_HISTORY.md` y `KNOWN_ISSUES.md` actualizados.
- [x] Git commit creado. — Ver historial de Git.

## Evidencia (FASE 9)

- Arquitectura separada: `models.py` (datos/constraints/señales), `services.py` (búsqueda/filtro/orden/documentos/auditoría), `file_validation.py` (seguridad de archivos), `forms.py` (validación), `views.py` (bases compartidas `_Contact*` parametrizadas, delgadas), `templates/customers/*.html` (Design System de FASE 5, tabs ARIA).
- `ContactoMixin` (abstracto) comparte campos entre `Customer`/`Supplier` sin acoplarlos: cada uno declara sus propias constraints porque la unicidad es POR modelo.
- Identificación fiscal extensible (`IdentificationType` con `choices`: Cédula, RNC, Pasaporte, Tax ID, Otro) — agregar un tipo nuevo no exige rehacer el modelo.
- PostgreSQL: `UniqueConstraint` parciales (identificación/email únicos por tenant, nunca global), `CheckConstraint` (al menos un nombre, tipo de identificación si hay número, `credit_limit` no negativo), índices compuestos.
- Documentos: validación en capas (tamaño, lista negra de extensiones peligrosas, lista blanca, firma binaria real) sin depender de librerías nativas externas; nombres de archivo generados (nunca el original) en `media-private/` (nunca servido como estático público); descarga solo vía vista protegida (login + tenant + pertenencia exacta); limpieza de archivos huérfanos mediante señal `post_delete` (cubre cualquier camino de borrado, no solo el de la vista).
- Datos comerciales: preparados como configuración real (`payment_terms`, `credit_days`, `credit_enabled`, `currency`, `credit_limit`, `commercial_notes`) sin motor financiero (sin `balance`, sin ledger) — documentado explícitamente en `docs/customers.md`/`docs/suppliers.md` con el plan de extensión futura.
- Auditoría mínima (`ActivityLog`), acotada a este módulo, explícitamente distinta del audit log transversal de FASE 15.
- Multi-Tenant: tests explícitos de lectura, búsqueda, filtros, paginación, edición, desactivación, documentos (subida/descarga/eliminación) e IDs manipulados — incluyendo el caso de un `document_pk` real de otro cliente combinado con un `pk` de cliente propio.
- Performance: comparación de conteo de queries (listados y detalle con documentos) verificando ausencia de N+1.
- Bug real de Windows encontrado y corregido durante el desarrollo: un archivo recién descargado en el mismo proceso puede quedar con el handle abierto (el test Client de Django no consume `streaming_content` automáticamente, a diferencia de un servidor WSGI/ASGI real) — el borrado físico ahora captura `OSError` y registra el error sin romper la operación de borrado en PostgreSQL. Ver `KNOWN_ISSUES.md`.
- Ningún módulo de negocio adicional (Ventas, POS, Compras, Gastos, Reportes, API de Inventario, PayPal, Billing, motor financiero de crédito) fue construido.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 10 — Sales Engine.
