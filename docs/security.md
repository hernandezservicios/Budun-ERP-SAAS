# Seguridad

> **Estado: referencia consolidada, sincronizada antes de FASE 18.**
> Este documento reúne los controles de seguridad que YA existen,
> construidos de forma incremental desde FASE 0, y señala explícitamente
> qué queda pendiente de auditoría/endurecimiento/prueba negativa formal
> en **FASE 18 — Security Hardening**
> (`docs/phases/PHASE-18-security-hardening.md`, checklist completo).
> Ningún control aquí descrito como "construido" fue verificado con la
> disciplina exhaustiva (pruebas negativas, concurrencia, checklist
> Hallazgo→Impacto→Reproducción→Corrección→Test→Resultado) que exige
> FASE 18 — esta síntesis es documental, no un cierre de auditoría.

## Regla crítica (permanente, ver `CLAUDE.md`)
No registrar passwords, tokens, API keys completas, client secrets de
PayPal/Integration, ni contraseñas de base de datos — en código, en
Git, en logs, ni en auditoría. `apps.core.utils.mask_secret` es el
único mecanismo de enmascarado reutilizado en todo el proyecto (IMEI/
serie, API Key, prefijos de credenciales).

## Autenticación, sesiones y cookies
**Construido**: login/logout por correo (`apps.accounts`, FASE 4),
recuperación/cambio de contraseña vía los flujos estándar de Django,
`SESSION_COOKIE_HTTPONLY=True`, `CSRF_COOKIE_HTTPONLY=False`
(deliberado: Django expone el token a JS para el header
`X-CSRFToken`), `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE=True`
cuando `DEBUG=False`, `SECURE_CONTENT_TYPE_NOSNIFF=True`,
`X_FRAME_OPTIONS="DENY"` (`config/settings.py`). Ningún login fallido
guarda la contraseña (`apps.audit`, señal `user_login_failed`).
**Pendiente en FASE 18**: HSTS, redirección forzada a HTTPS, CSP,
`Referrer-Policy`/`Permissions-Policy`, límite de intentos de login/
recuperación de contraseña (no existe today ninguna protección de
fuerza bruta — ni `django-axes` ni throttling propio en
`apps.accounts`) — deliberadamente diferido desde FASE 3 ("Endurecimiento
completo... corresponde a FASE 18", comentario ya presente en
`config/settings.py`).

## Autorización, roles y privilege escalation
**Construido**: autorización binaria OWNER/MEMBER desde FASE 3
(`apps.tenants.permissions.require_tenant`/`require_role`, nunca
retirada); catálogo granular de ~87 permisos código-definidos desde
FASE 15 (`apps.permissions.services.has_permission`, jerarquía usuario
→ rol → tenant → negar, igual que `apps.approvals`); el tenant SIEMPRE
se resuelve desde la sesión/membresía real, nunca de un parámetro
enviado por el cliente (`TenantMiddleware`). `SUPER_ADMIN` = `User.
is_superuser` (concepto de plataforma, no de tenant).
**Pendiente en FASE 18**: batería formal de pruebas negativas de
escalación de privilegios (bypass por URL/POST manual/IDs manipulados/
método HTTP/control UI-only) sobre las superficies de mayor riesgo
enumeradas en `docs/phases/PHASE-18-security-hardening.md`.

## Aislamiento Multi-Tenant
**Construido**: todo modelo de negocio hereda `TenantScopedModel`
(`objects` tenant-scoped vía `ContextVar`, `all_objects` como vía de
escape consciente); verificado con tests dedicados de aislamiento en
prácticamente cada fase (IDs manipulados, URLs cruzadas, exports).
**Gotcha ya documentado y corregido repetidas veces** (`KNOWN_ISSUES.md`
#90/#95/#97/#108): una relación inversa sobre un modelo
`TenantScopedModel` accedida fuera de una request real (test, comando
de administración, receptor de señal) resuelve con el manager
tenant-scoped por defecto y devuelve vacío — nunca datos de otro
tenant, pero sí un fallo silencioso de la propia funcionalidad; la
disciplina establecida es `all_objects` explícito en todo servicio/
vista de plataforma.
**Pendiente en FASE 18**: revisión sistemática de CADA manager
tenant-scoped usado en exportaciones/reportes/media/Inventory API/
Catalog API/Billing según la lista de la sección "Multi-Tenant" del
checklist de fase.

## Super Admin / Platform Isolation
**Construido**: recursos de plataforma (PayPal — FASE 16, Billing SaaS
— FASE 17) exigen `request.user.is_superuser`
(`apps.tenants.permissions.require_superuser`/`SuperuserRequiredMixin`)
— deliberadamente NO el catálogo tenant-scoped de `apps.permissions`.
`Tenant.billing_status` nunca es editable desde un formulario directo,
solo por `apps.billing.services.tenants`. Verificado con tests: un
tenant normal recibe 403 en toda vista de plataforma.
**Pendiente en FASE 18**: pruebas negativas explícitas de que un
tenant no pueda aprobar sus propias transferencias, administrar
`BankAccount`/`Integration` globales, ni alterar su propio
`billing_status` por ningún camino no documentado.

## Inventory API (`/api/v1/`, FASE 15)
**Construido**: `ApiKey` (hash SHA-256, nunca texto plano, una activa
por tenant, rotar reescribe la misma fila), scopes cerrados sin acceso
financiero, `ApiKeyRateThrottle`, paginación con tope, sobre de
respuesta consistente, solo lectura (sin POST/PUT/DELETE en ningún
endpoint) — verificado con tests.
**Pendiente en FASE 18**: revisión negativa de manipulación de scope/
paginación/filtros y rate limit bajo concurrencia real.

## Catalog API (`/api/v1/catalog/`, ampliación final de FASE 15)
**Construido**: whitelist server-side estricta en los serializers,
verificada con tests que comprueban la AUSENCIA de IMEI/serial/costo/
margen/proveedor/datos de otro dominio (no solo la presencia de los
permitidos); imágenes servidas por `public_id` (UUID no adivinable).
**Pendiente en FASE 18**: intentos activos de manipulación de campos
en requests reales (no solo ausencia en la respuesta serializada).

## Integration / App Secret (ampliación final de FASE 15)
**Construido**: mismo mecanismo de hash que `ApiKey`
(`apps.api.crypto`), secreto mostrado una única vez, `app_key` público
nunca usado para autenticar, `status`(terminal)/`is_enabled`
(reversible) como conceptos separados.
**Pendiente en FASE 18**: revisión de rotación/revocación bajo
concurrencia, y de que ningún log/error exponga el secreto completo.

## PayPal / Webhooks (FASE 16)
**Construido**: verificación oficial de firma
(`/v1/notifications/verify-webhook-signature`) antes de procesar
cualquier evento; idempotencia real (`UniqueConstraint` en
`PayPalWebhookEvent.event_id`); tolerancia a duplicados y eventos fuera
de orden (probado con hilos reales); access token nunca persistido,
client secret nunca auditado; webhook nunca activa una suscripción
solo por parámetros del navegador (la confirmación real es
`capture_checkout`/webhook verificado). Rate limit básico por IP en el
endpoint público.
**Pendiente en FASE 18**: SSRF cuando aplique (URLs de `cert_url`
manejadas por PayPal, no por nosotros — confirmar que nunca se siga
una URL arbitraria), límites de tamaño de payload/timeouts explícitos
más allá del timeout HTTP ya fijado en `apps.billing.providers.paypal`.

## Billing SaaS (FASE 17)
**Construido**: `SaaSInvoice.UniqueConstraint(subscription,
period_start)` impide activar/duplicar facturas por reintento; ningún
camino marca una factura pagada sin una `SaaSPaymentAllocation`/
`CreditNoteApplication` real (`get_invoice_balance_due` siempre deriva
del ledger); `PaymentProof` nunca activa el tenant por sí solo, solo
`approve_payment_proof` (Super Admin) lo hace; separación estricta
Portal (`billing.saas.*`) vs. Super Admin (`is_superuser`).
**Pendiente en FASE 18**: batería negativa explícita — intentar activar
un tenant sin pago, marcar factura pagada sin allocation, crear crédito
arbitrario, alterar un histórico, aplicar cross-tenant, autoaprobar un
comprobante propio.

## Transferencias y comprobantes
**Construido**: `PaymentProof.file` en `media-private/` (MEDIA_ROOT no
servido públicamente en ningún punto de `config/urls.py`), nombre de
archivo generado (nunca el original), referencia única por
`UniqueConstraint(tenant, reference)`, validación de archivo
(extensión + firma binaria) vía `apps.customers.file_validation`.
**Pendiente en FASE 18**: prueba explícita de descarga cross-tenant,
reemplazo/duplicación de comprobante, path traversal en el nombre
declarado.

## Uploads y media
**Construido**: `apps.customers.file_validation` (lista negra de
extensiones peligrosas, lista blanca de formatos, firma binaria real
contra archivos disfrazados, límite de 10 MB) reutilizado por
`PaymentProof` (FASE 17); `ProductImage`/Catalog API es la ÚNICA
excepción deliberada de media pública (imágenes de catálogo,
físicamente separada de `media-private/`, servida por UUID).
**Pendiente en FASE 18**: doble extensión, caracteres especiales en el
nombre declarado, archivos enormes cerca del límite exacto.

## XSS / CSRF / Injection / mass assignment
**Construido**: CSRF vía `CsrfViewMiddleware` (activo en todas las
vistas con formulario); Django ORM parametrizado en todo el proyecto
(sin SQL crudo); plantillas con autoescape de Django por defecto (sin
`|safe` extendido sobre datos de usuario, no auditado exhaustivamente
todavía); formularios/serializers explícitos con campos declarados
(nunca `fields = "__all__"` sin revisar) en los módulos financieros.
**Pendiente en FASE 18**: revisión sistemática de mass assignment en
cada formulario/serializer, XSS almacenado en campos de texto libre
(nombres, notas, referencias, motivos), y una pasada dedicada de
template injection.

## HTTP Security (headers, CORS)
**Construido**: `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`.
**Pendiente en FASE 18** (documentado desde FASE 3 como diferido):
HSTS, redirección SSL, CSP, `Referrer-Policy`, `Permissions-Policy`;
el proyecto no expone API pública consumida desde otro origen salvo
`/api/v1/` (autenticado por credencial, no por cookie) y el webhook de
PayPal (POST server-to-server) — sin necesidad de CORS de navegador
hasta ahora, a confirmarse en FASE 18.

## Secrets, logging y errores
**Construido**: `.env` fuera de Git (`.gitignore`), `DJANGO_SECRET_KEY`
obligatorio sin default inseguro, credenciales de PayPal/DB por
variable de entorno; ningún secreto se audita (`apps.audit`,
`apps.billing.services._saas_audit`); `apps.audit` redacta
explícitamente cualquier clave que contenga "pass"/"secret"/"token"/
"clave".
**Pendiente en FASE 18**: revisión de `DEBUG`/`ALLOWED_HOSTS` en un
despliegue real, y de que ningún traceback en producción exponga
información de otro tenant.

## Rate limiting / abuse
**Construido**: `ApiKeyRateThrottle`/`CatalogRateThrottle` (DRF,
120/min configurable), throttle básico por IP en el webhook de PayPal.
**Pendiente en FASE 18**: login, recuperación de contraseña y demás
endpoints sensibles fuera de `/api/v1/` no tienen límite de tasa
todavía — gap real, priorizado explícitamente en la cobertura de FASE 18.

## Reports / Exports
**Construido**: `apps.reports`/`apps.billing.services.reports` nunca
introducen un modelo propio (agregan sobre servicios existentes);
información sensible de RRHH/Nómina se filtra en el servidor
(`can_view_sensitive_employee_data`), nunca solo oculta en la UI;
exportaciones PDF/XLSX (`apps.reports.exports`, `reportlab`/`openpyxl`)
tenant-scoped.
**Pendiente en FASE 18**: CSV injection (fórmulas en celdas exportadas),
nombres de archivo generados a partir de datos de usuario.

## Audit Log
**Construido**: `apps.audit.AuditLog` (dominio transversal) + 7
`*ActivityLog` por dominio + dominios `"billing_paypal"`/`"billing_saas"`
— todos con actor/tenant (nullable cuando corresponde)/timestamps;
inmutable (sin update/delete); nunca registra secretos.
**Pendiente en FASE 18**: verificación exhaustiva de que TODOS los
eventos críticos listados en el checklist de fase quedan auditados.

## Concurrencia
**Construido**: `TransactionTestCase` + hilos reales en cada dominio
con dinero/inventario (pagos, allocations, aprobaciones, activaciones,
webhooks, generación de factura) desde FASE 8 — exactamente una
operación gana cuando el negocio exige exclusividad.
**Pendiente en FASE 18**: cobertura sistemática de rotación de
credenciales (`ApiKey`/`Integration`) bajo concurrencia, no probada
explícitamente todavía.

## Dependencias
Sin herramienta de escaneo de vulnerabilidades ejecutada todavía sobre
`requirements.txt` (Django, psycopg, djangorestframework,
python-dotenv, gunicorn, reportlab, openpyxl, Pillow) — pendiente en
FASE 18.

## Qué NO se construye con este documento
Ningún cambio de código, configuración de seguridad activa nueva
(HSTS/CSP/rate limiting de login/etc.), ni corrección de las brechas
"Pendiente en FASE 18" listadas arriba — esta síntesis es
exclusivamente documental. Ver `docs/phases/PHASE-18-security-hardening.md`
para el checklist completo de la fase.
