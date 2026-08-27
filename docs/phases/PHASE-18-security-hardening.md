# FASE 18 — Security Hardening Profesional

> **Estado: EJECUTADA.** Ver `docs/security.md` para el estado
> consolidado control por control (Construido/Verificado/Diferido) y
> el reporte de cierre entregado al usuario para el detalle hallazgo
> por hallazgo (Hallazgo/Severidad/Impacto/Reproducción/Corrección/
> Test/Resultado). Los "Criterios de aceptación" se marcaron abajo con
> evidencia real — cada casilla indica el alcance REAL verificado, no
> una auditoría exhaustiva de cada vista/campo del proyecto (~100
> vistas). Lo explícitamente diferido (CSP real, `SECURE_SSL_REDIRECT`,
> rate limiting por endpoint fuera de auth, batería negativa exhaustiva
> vista-por-vista) queda documentado, nunca oculto.

## Objetivo
Auditar, endurecer y corregir la seguridad real de todo el ERP SaaS construido en FASES 0–17. La fase es de hardening, pruebas negativas, revisión de código, corrección y evidencia. No crear funcionalidades de negocio nuevas.

## Cobertura obligatoria
Auditar como mínimo: autenticación, recuperación de contraseña, sesiones, cookies, CSRF, autorización, roles, permisos granulares, escalación de privilegios, Super Admin, aislamiento Multi-Tenant, Inventory API, Catalog API, Integration/App Secret, PayPal, webhooks, Billing SaaS, transferencias, comprobantes, uploads, media pública, reportes, exportaciones, contabilidad, POS/caja, ventas, compras, gastos, RRHH/nómina, auditoría, rate limiting, headers HTTP, configuración/secretos, logs y errores.

## Regla incremental
Modificar solamente lo necesario para resolver vulnerabilidades, hardening, controles de seguridad o tests de esta fase. No iniciar FASE 19 ni construir funcionalidades futuras.

## Auditoría previa
Leer CLAUDE.md, docs/MASTER-PROMPT.md, ARCHITECTURE.md, FASES 0–17 y estado del proyecto. Inspeccionar código real, sin asumir que la documentación coincide siempre con él.

## Autenticación
Revisar login/logout, password reset, cambio de contraseña, enumeración, sesiones, expiración, cookies Secure/HttpOnly/SameSite, invalidación, fuerza bruta y respuestas consistentes. Nunca loguear contraseñas ni secretos.

## Autorización y privilege escalation
Verificar SUPER ADMIN, OWNER, ADMIN, MANAGER, CASHIER, EMPLOYEE y MEMBER y todos los permisos. Probar bypass por URL, POST manual, IDs, parámetros, formularios, endpoints, métodos HTTP y UI-only controls. Intentar acceso no autorizado a plataforma, permisos, Billing, auditoría, credenciales, datos sensibles, PayPal y funciones administrativas.

## Multi-Tenant
Probar IDs/UUID/URLs/POST/FK/exports/reportes/media/archivos/Inventory API/Catalog API/Billing/comprobantes/pagos/documentos y objetos serializados. Tenant A nunca puede acceder a Tenant B. Revisar especialmente managers tenant-scoped usados fuera de contexto.

## Super Admin / Platform Isolation
Verificar que rutas y operaciones de plataforma requieran el nivel correcto; que un tenant no pueda modificar billing_status, aprobar transferencias, administrar BankAccounts de plataforma ni integraciones globales.

## Inventory API
Auditar ApiKey, hash, revocación, rotación, scopes, rate limit, paginación y respuestas. Confirmar endpoints read-only realmente read-only.

## Catalog API
Auditar whitelist y serializers. Nunca exponer IMEI, serial, costo, margen, proveedor, movimientos internos, clientes privados, pagos, caja, contabilidad o RRHH sensible. Probar manipulación de campos.

## Integration/App Secret
Auditar creación, almacenamiento, cifrado/hash, rotación, revocación, scopes, UI, logs, errores y auditoría. Nunca revelar secretos.

## PayPal/Webhooks
Auditar Client Secret, access token, webhook ID, firma, replay, duplicados, out-of-order, eventos desconocidos, idempotencia, SSRF cuando aplique, payload size, timeouts y errores. Nunca procesar webhook no verificado ni confiar en el navegador.

## Billing SaaS
Auditar Plans, Subscription, Invoice, Payment, Allocation, Credit, Advance, Credit Note, Refund, Transfer, Payment Proof, Verification y lifecycle del Tenant. Buscar bypass para activar tenants sin pago, marcar facturas pagadas, crear crédito, cambiar históricos, cross-tenant allocations, autoaprobación de comprobantes o extensión no autorizada.

## Transferencias y comprobantes
Auditar ownership, MIME spoofing, extensión, tamaño, path traversal, storage, descarga, URLs, reemplazo, duplicación y cross-tenant. Comprobantes privados.

## Uploads y media
Revisar ejecutables disfrazados, double extension, MIME falso, contenido incompatible, archivos enormes, path traversal, caracteres especiales y acceso público accidental. Mantener separación ProductImage pública vs media privada.

## XSS / CSRF / Injection / mass assignment
Probar XSS almacenado/reflejado, HTML/template injection, CSRF, SQL/command/header injection, unsafe redirects. Revisar nombres, descripciones, notas, referencias, observaciones, mensajes y auditoría. Buscar formularios/serializers/services que acepten campos sensibles sin whitelist.

## HTTP Security
Revisar HSTS, CSP, X-Frame-Options/frame-ancestors, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, cookies, HTTPS redirects y CORS. No activar políticas incompatibles sin probar.

## Secrets, logging y errores
Buscar secrets en Git, DEBUG, ALLOWED_HOSTS, CORS/CSRF origins, claves hardcodeadas, tracebacks y logs inseguros. Errores no deben filtrar tokens, secretos, Authorization headers, SQL sensible ni información de otros tenants.

## Rate limiting / abuse
Revisar login, password reset, APIs, webhooks y endpoints sensibles. Establecer límites razonables.

## Reports / Exports
Auditar autorización, aislamiento, datos sensibles, nombres de archivos, CSV injection, PDF/XLSX, rutas temporales y URLs.

## Audit Log
Verificar actor, tenant/platform context, timestamps y eventos críticos. Nunca registrar secretos, contraseñas o tokens.

## Concurrency
Usar PostgreSQL real y TransactionTestCase/equivalente. Probar operaciones simultáneas de permisos, pagos, allocations, approvals, Billing, activaciones, webhooks y rotaciones de credenciales. Buscar TOCTOU/races.

## Negative Testing
Crear pruebas para otro tenant, rol/permiso insuficiente, IDs manipulados, sesión/token inválido, payload extra y campos prohibidos.

## Security Smoke Test
Cuando aplique, realizar contra PostgreSQL real: auth/authz, aislamiento A/B, Billing, API, Catalog, webhook, upload privado y exportación.

## Dependencias
Revisar vulnerabilidades con herramienta fiable si existe. No actualizar paquetes masivamente sin justificar compatibilidad.

## Security Checklist
Mantener checklist viva con:
Hallazgo → Impacto → Reproducción → Corrección → Test → Resultado.
No declarar PASS sin evidencia.

## Bug policy
Cada vulnerabilidad real debe reproducirse, corregirse, tener test de regresión y volver a probarse. Falsos positivos documentados.

## No inventar vulnerabilidades
No cambiar comportamiento sin justificación técnica.

## Documentación
Actualizar:
- CLAUDE.md
- docs/MASTER-PROMPT.md
- ARCHITECTURE.md si cambia doctrina
- docs/security.md (crear si no existe)
- docs/phases/PHASE-18-security-hardening.md
- CURRENT_PHASE.md
- PHASE_HISTORY.md
- KNOWN_ISSUES.md
- DECISIONS.md

No crear duplicados.

## Verificación obligatoria
Ejecutar:
- python manage.py check
- python manage.py makemigrations --check --dry-run
- suite completa
- tests de seguridad/negativos
- smoke tests cuando aplique

## Criterios de aceptación
- [x] checklist completa — 20 categorías auditadas (código real, no solo documentación); ver `docs/security.md` sección por sección.
- [x] negative tests completos — nuevos: `LoginThrottlingTests`/`PasswordResetThrottlingTests` (apps.accounts), `PortalMultiTenantIsolationTests` (apps.billing, IDOR), `PayPalWebhookHttpTests` (webhook sin firma/cabeceras), `ApiKeyRotationConcurrencyTests`, formula-injection CSV/XLSX (apps.reports) — no exhaustivo sobre cada vista del proyecto, representativo de las superficies de mayor riesgo.
- [x] auth/authz revisadas — hallazgo real corregido (throttling login/reset); privilege escalation auditado (sin superficie de invitación/cambio de rol construida todavía; `settings.manage` correctamente restringido; OWNER siempre autorizado antes de mirar overrides).
- [x] multi-tenant revisado — `TenantQuerySet.for_current_tenant()` confirmado fail-closed; Portal de Facturación auditado con test nuevo; Super Admin de Billing confirmado 100% gated y usando `all_objects` donde corresponde.
- [x] APIs revisadas — Inventory/Catalog API: cobertura de clave expirada/revocada/scope ya existente confirmada por inspección; concurrencia de rotación de `ApiKey` agregada.
- [x] PayPal/webhooks revisados — cobertura HTTP real de la vista del webhook agregada (sin cabeceras, csrf_exempt, rate limit); SSRF vía `cert_url` descartado por inspección del código (nunca se sigue esa URL).
- [x] Billing revisado — Super Admin 100% gated (22+5 vistas auditadas); IDOR del Portal cerrado con test.
- [x] secrets revisados — sin hallazgos nuevos; `mask_secret`/redacción de auditoría ya cubrían esto desde FASE 15/16.
- [x] uploads/media revisados — `PaymentProof` confirmado reutilizando `apps.customers.file_validation` (sin hallazgo, patrón correcto ya existente).
- [x] sessions/cookies revisados — sin cambios necesarios (`HttpOnly`/`Secure` condicional ya correctos desde FASE 3/4).
- [x] headers/CORS revisados — HSTS y `Permissions-Policy` agregados; corregida una imprecisión documental (`Referrer-Policy`/`Cross-Origin-Opener-Policy` ya activos por defecto de Django); CSP y `SECURE_SSL_REDIRECT` diferidos con razón explícita.
- [x] reports/exports revisados — CSV/XLSX Formula Injection encontrado y corregido con test negativo real.
- [x] concurrency revisada — rotación de `ApiKey` bajo hilos reales (nuevo); rotación de `Integration` queda pendiente, documentado.
- [x] audit revisado — dos acciones nuevas (`LOGIN_THROTTLED`/`PASSWORD_RESET_THROTTLED`) agregadas y auditadas; sin hallazgos de secretos filtrados.
- [x] dependencias evaluadas — `pip-audit` real ejecutado; único hallazgo (rango de Pillow) corregido sin actualización masiva.
- [x] documentación actualizada — `docs/security.md`, `KNOWN_ISSUES.md` (#112-115), `DECISIONS.md` (#82-88), `CURRENT_PHASE.md`, `PHASE_HISTORY.md`, este archivo.
- [x] regresión verde — ver reporte de cierre para el conteo exacto final.
- [x] smoke test cuando aplique — no se ejecutó un smoke test nuevo contra PostgreSQL real más allá de la suite automatizada (que ya corre contra PostgreSQL real en este proyecto, ver `docs/setup/*`); no se identificó un flujo de seguridad que solo pudiera reproducirse fuera de la suite de tests.
- [x] working tree limpio — verificado antes de cerrar (ver reporte de cierre).
- [x] Git commit — ver reporte de cierre para el/los hash(es).

## Regla de parada
FASE 18 termina aquí. No iniciar FASE 19. Entregar reporte completo con hallazgos, correcciones, tests y evidencia. DETENERSE.
