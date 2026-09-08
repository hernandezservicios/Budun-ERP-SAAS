# Seguridad

> **Estado: FASE 18 — Security Hardening ejecutada.** Este documento
> reúne los controles de seguridad de todo el proyecto (FASE 0–17) más
> los hallazgos reales auditados, reproducidos y corregidos en FASE 18
> (checklist completo y reporte de cierre en
> `docs/phases/PHASE-18-security-hardening.md`). Cada sección marca
> **Construido** (verificado, con test que lo demuestra) y, cuando
> aplica, **Pendiente / diferido deliberadamente** (con la razón
> explícita — nunca una brecha oculta). Los hallazgos reales de esta
> fase están además documentados uno por uno, con el formato Hallazgo/
> Severidad/Impacto/Reproducción/Corrección/Test/Resultado, en el
> reporte de cierre de fase — este documento resume el estado final,
> no repite ese detalle punto por punto.

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
**Hallazgo real corregido en FASE 18**: ni el login ni la recuperación
de contraseña tenían ningún límite de intentos — fuerza bruta/
credential stuffing sin fricción y bombardeo de correos de reset sin
límite. Corregido con throttling propio basado en caché
(`apps.accounts.rate_limit`, `LocMemCache` — mismo backend que
`apps.api.throttling`, sin dependencia nueva): eje por email Y eje por
IP para login (`EmailAuthenticationForm.clean`, 5 intentos/15 min por
email, 20/15 min por IP; el contador se limpia tras un login exitoso;
el bloqueo se verifica ANTES de `authenticate()` y nunca se distingue,
en el mensaje mostrado, de una contraseña incorrecta) y para
recuperación de contraseña (`AccountPasswordResetView.form_valid`, 5/
hora por email, 10/hora por IP — la respuesta sigue siendo la misma
página de "listo" esté o no bloqueado, igual que Django ya hace para
no revelar si el email existe). Cada bloqueo se audita
(`AuditLog.Action.LOGIN_THROTTLED`/`PASSWORD_RESET_THROTTLED`).
Verificado con pruebas negativas reales (`apps/accounts/tests.py`,
`LoginThrottlingTests`/`PasswordResetThrottlingTests`): agotar el
límite bloquea incluso una contraseña CORRECTA, un login exitoso
resetea el contador, y el bloqueo por IP afecta a cualquier cuenta
desde ese origen.
**Diferido deliberadamente**: `django-axes` u otra dependencia de
terceros para esto (no hacía falta — el throttling propio basado en
caché ya cierra el hallazgo real sin una dependencia nueva); CSP (ver
sección "HTTP Security" — requiere una auditoría de plantillas que no
es segura hacer sin una pasada dedicada); `SECURE_SSL_REDIRECT` (ver
misma sección — depende del proxy real de FASE 21).

## Autorización, roles y privilege escalation
**Construido**: autorización binaria OWNER/MEMBER desde FASE 3
(`apps.tenants.permissions.require_tenant`/`require_role`, nunca
retirada); catálogo granular de ~87 permisos código-definidos desde
FASE 15 (`apps.permissions.services.has_permission`, jerarquía usuario
→ rol → tenant → negar, igual que `apps.approvals`); el tenant SIEMPRE
se resuelve desde la sesión/membresía real, nunca de un parámetro
enviado por el cliente (`TenantMiddleware`). `SUPER_ADMIN` = `User.
is_superuser` (concepto de plataforma, no de tenant).
**Verificado en FASE 18**: no existe ninguna vista de "invitar
miembro"/"cambiar rol de un compañero" en el proyecto todavía (los
únicos dos lugares que crean un `Membership` son el onboarding —
siempre `OWNER`, el propio usuario — y la venta manual de tenant del
Super Admin, exclusiva de `is_superuser`) — no hay, por ahora,
superficie de escalación de rol vía formulario porque esa
funcionalidad de equipo/invitaciones simplemente no está construida.
`RolesIndexView`/`RolePermissionsView`/`UserOverridesView`
(`apps.permissions`) exigen `settings.manage`, permiso ausente del
catálogo de fábrica de todo rol salvo `OWNER`; `has_permission`
retorna `True` incondicionalmente para `OWNER` antes de mirar
cualquier override, así que ni un `RolePermission`/
`UserPermissionOverride` manipulado directo puede degradar ni elevar
al propietario.
**Pendiente / fuera de alcance de esta pasada**: batería exhaustiva de
pruebas negativas de escalación de privilegios sobre CADA una de las
~100 vistas del proyecto — se auditó el motor de resolución
(`has_permission`) y las superficies de mayor riesgo, no cada vista
CRUD individual.

## Aislamiento Multi-Tenant
**Construido**: todo modelo de negocio hereda `TenantScopedModel`
(`objects` tenant-scoped vía `ContextVar`, `all_objects` como vía de
escape consciente); verificado con tests dedicados de aislamiento en
prácticamente cada fase (IDs manipulados, URLs cruzadas, exports).
**Verificado explícitamente en FASE 18**: `TenantQuerySet.
for_current_tenant()` fail-closed por diseño — sin tenant activo en el
contexto devuelve SIEMPRE queryset vacío, nunca "todos los tenants"
(`apps/tenants/managers.py`); esto confirma que el gotcha de abajo es,
en el peor caso, un fallo funcional (404/vacío indebido), nunca una
fuga de datos entre tenants. Auditados los `get_object_or_404` de
`apps.billing.admin_views`/`platform_views` (Super Admin): todos los
modelos tenant-scoped usan `all_objects` explícito, ninguna regresión.
Se agregó cobertura de aislamiento que no existía (`apps.billing.
tests.test_portal_views.PortalMultiTenantIsolationTests`): el Portal
de Facturación (`transferencia/<id>/`, `cobrar/<id>/paypal/*`) no
tenía ningún test negativo de IDOR — se confirmó (ya se comportaba
correctamente: filtro explícito `tenant=request.tenant` en cada vista)
que el tenant B recibe 404 al intentar ver/operar la factura del
tenant A por ID manipulado.
**Gotcha ya documentado y corregido repetidas veces** (`KNOWN_ISSUES.md`
#90/#95/#97/#108): una relación inversa sobre un modelo
`TenantScopedModel` accedida fuera de una request real (test, comando
de administración, receptor de señal) resuelve con el manager
tenant-scoped por defecto y devuelve vacío — nunca datos de otro
tenant, pero sí un fallo silencioso de la propia funcionalidad; la
disciplina establecida es `all_objects` explícito en todo servicio/
vista de plataforma.
**Pendiente / fuera de alcance de esta pasada**: auditoría campo-por-
campo de cada exportación/reporte restante (decenas de vistas) — se
auditó una muestra representativa de las superficies de mayor riesgo
(Billing/Reportes), no las ~100 vistas del proyecto una por una.

## Super Admin / Platform Isolation
**Construido**: recursos de plataforma (PayPal — FASE 16, Billing SaaS
— FASE 17) exigen `request.user.is_superuser`
(`apps.tenants.permissions.require_superuser`/`SuperuserRequiredMixin`)
— deliberadamente NO el catálogo tenant-scoped de `apps.permissions`.
`Tenant.billing_status` nunca es editable desde un formulario directo,
solo por `apps.billing.services.tenants`. Verificado con tests: un
tenant normal recibe 403 en toda vista de plataforma.
**Verificado en FASE 18**: se auditaron TODAS las clases de
`apps.billing.admin_views`/`platform_views` (22 + 5 vistas) — todas
exigen `LoginRequiredMixin` + `SuperuserRequiredMixin` sin excepción,
ninguna vía sin gate encontrada.
**Pendiente / fuera de alcance de esta pasada**: pruebas negativas
explícitas adicionales de que un tenant no pueda aprobar sus propias
transferencias ni alterar su `billing_status` por un camino no
documentado — la ausencia de gate ya se descartó por auditoría
exhaustiva del código; una batería de pruebas negativas dedicada
punto por punto queda para una pasada futura si se prioriza.

## Inventory API (`/api/v1/`, FASE 15)
**Construido**: `ApiKey` (hash SHA-256, nunca texto plano, una activa
por tenant, rotar reescribe la misma fila), scopes cerrados sin acceso
financiero, `ApiKeyRateThrottle`, paginación con tope, sobre de
respuesta consistente, solo lectura (sin POST/PUT/DELETE en ningún
endpoint) — verificado con tests.
**Verificado en FASE 18**: cobertura ya existente confirmada por
inspección directa de `apps/api/tests/` — clave expirada, clave
revocada, scope insuficiente y prueba de conexión fallida ya estaban
cubiertos (`test_services.py`, `test_views.py`) antes de esta fase;
no se encontró ningún caso de estos sin test.
**Pendiente / fuera de alcance de esta pasada**: rate limit bajo
concurrencia real (varias requests simultáneas contra el mismo
contador de `LocMemCache`) no se probó explícitamente en esta fase.

## Catalog API (`/api/v1/catalog/`, ampliación final de FASE 15)
**Construido**: whitelist server-side estricta en los serializers,
verificada con tests que comprueban la AUSENCIA de IMEI/serial/costo/
margen/proveedor/datos de otro dominio (no solo la presencia de los
permitidos); imágenes servidas por `public_id` (UUID no adivinable).
**Pendiente / fuera de alcance de esta pasada**: intentos activos de manipulación de campos
en requests reales (no solo ausencia en la respuesta serializada).

## Integration / App Secret (ampliación final de FASE 15)
**Construido**: mismo mecanismo de hash que `ApiKey`
(`apps.api.crypto`), secreto mostrado una única vez, `app_key` público
nunca usado para autenticar, `status`(terminal)/`is_enabled`
(reversible) como conceptos separados.
**Verificado en FASE 18**: ningún log/auditoría/mensaje de error
expone el secreto completo (`apps.audit` redacta cualquier clave que
contenga "secret"/"token"/"clave"; `apps.api.crypto` nunca persiste el
valor en texto plano).
**Pendiente / fuera de alcance de esta pasada**: rotación de
`Integration` bajo concurrencia no se probó explícitamente en esta
fase (sí se probó la de `ApiKey`, ver sección "Concurrencia" — mismo
patrón estructural, mismo `rotate_*` sin `select_for_update()` sobre
la misma fila, mismo riesgo bajo, pero no es evidencia intercambiable:
queda documentado como pendiente en vez de asumido).

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
**Verificado explícitamente en FASE 18**: hasta esta fase, ningún test
ejercitaba la vista HTTP real del webhook (`PayPalWebhookView`) — todos
llamaban directo a la capa de servicio. Se agregó
`apps.billing.tests.test_webhook_view_http` (nuevo archivo): confirma
que faltar TODAS las cabeceras de PayPal se rechaza igual que una
firma inválida (400, nunca 200 ni 500), que la vista es `csrf_exempt`
a propósito (POST sin token CSRF no falla por eso), y que el rate
limit por IP responde 429 al superarse.
**Pendiente / diferido**: SSRF cuando aplique (URLs de `cert_url`
manejadas por PayPal, no por nosotros — confirmado que nuestro código
nunca sigue esa URL, la verificación es una llamada nuestra a la API
oficial de PayPal, nunca al `cert_url` recibido), límites de tamaño de
payload explícitos más allá del `DATA_UPLOAD_MAX_MEMORY_SIZE` global.

## Billing SaaS (FASE 17)
**Construido**: `SaaSInvoice.UniqueConstraint(subscription,
period_start)` impide activar/duplicar facturas por reintento; ningún
camino marca una factura pagada sin una `SaaSPaymentAllocation`/
`CreditNoteApplication` real (`get_invoice_balance_due` siempre deriva
del ledger); `PaymentProof` nunca activa el tenant por sí solo, solo
`approve_payment_proof` (Super Admin) lo hace; separación estricta
Portal (`billing.saas.*`) vs. Super Admin (`is_superuser`).
**Pendiente / fuera de alcance de esta pasada**: batería negativa explícita — intentar activar
un tenant sin pago, marcar factura pagada sin allocation, crear crédito
arbitrario, alterar un histórico, aplicar cross-tenant, autoaprobar un
comprobante propio.

## Transferencias y comprobantes
**Construido**: `PaymentProof.file` en `media-private/` (MEDIA_ROOT no
servido públicamente en ningún punto de `config/urls.py`), nombre de
archivo generado (nunca el original), referencia única por
`UniqueConstraint(tenant, reference)`, validación de archivo
(extensión + firma binaria) vía `apps.customers.file_validation`.
**Pendiente / fuera de alcance de esta pasada**: prueba explícita de descarga cross-tenant,
reemplazo/duplicación de comprobante, path traversal en el nombre
declarado.

## Uploads y media
**Construido**: `apps.customers.file_validation` (lista negra de
extensiones peligrosas, lista blanca de formatos, firma binaria real
contra archivos disfrazados, límite de 10 MB) reutilizado por
`PaymentProof` (FASE 17); `ProductImage`/Catalog API es la ÚNICA
excepción deliberada de media pública (imágenes de catálogo,
físicamente separada de `media-private/`, servida por UUID).
**Verificado en FASE 18**: se investigó específicamente si
`apps.billing.portal_forms.UploadProofForm` (el formulario del Portal
de comprobantes de pago) validaba el archivo — el propio `FileField`
del formulario NO tiene validador, pero la capa de SERVICIO
(`apps.billing.services.transfers.submit_payment_proof`) sí llama a
`validar_archivo_adjunto`/`nombre_original_seguro` de
`apps.customers.file_validation` antes de guardar nada — mismo
validador compartido, nunca uno paralelo. Confirmado con el test ya
existente `test_archivo_disfrazado_es_rechazado`. Sin hallazgo: es el
patrón correcto del proyecto (vistas/formularios delgados, validación
real en el servicio), no una omisión.
**Pendiente / fuera de alcance de esta pasada**: doble extensión,
caracteres especiales en el nombre declarado, archivos enormes cerca
del límite exacto — no se construyeron pruebas negativas nuevas para
estos tres casos puntuales en esta pasada.
**Relación con FASE 20**: `media-private/`/`catalog-media/` (además de
la base de datos) son el segundo componente obligatorio de la
estrategia de backup — ver `docs/backup-recovery.md` sección 10, sin
backup real todavía.

## XSS / CSRF / Injection / mass assignment
**Construido**: CSRF vía `CsrfViewMiddleware` (activo en todas las
vistas con formulario); Django ORM parametrizado en todo el proyecto
(sin SQL crudo); plantillas con autoescape de Django por defecto (sin
`|safe` extendido sobre datos de usuario, no auditado exhaustivamente
todavía); formularios/serializers explícitos con campos declarados
(nunca `fields = "__all__"` sin revisar) en los módulos financieros.
**Verificado en FASE 18**: búsqueda exhaustiva (`grep`) de
`fields = "__all__"` en todo `apps/` — cero resultados; todo
formulario/serializer del proyecto declara sus campos explícitamente,
no solo los financieros.
**Verificado en FASE 18**: búsqueda exhaustiva del filtro `|safe` en
TODAS las plantillas del proyecto (`apps/**/templates`, `templates/`)
— cero resultados; ninguna plantilla desactiva el autoescape de Django
sobre datos de usuario.
También cero resultados para `{% autoescape off %}`, `format_html` y
`mark_safe` en todo el proyecto — ningún punto desactiva el autoescape
de Django en ninguna plantilla ni vista.
**Pendiente / fuera de alcance de esta pasada**: revisión manual de
cada campo de texto libre RENDERIZADO (no solo búsqueda de patrones
que lo desactivarían) para confirmar que ninguno depende de un
autoescape que en el futuro alguien podría desactivar sin darse
cuenta del riesgo.

## HTTP Security (headers, CORS)
**Construido**: `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`.
**Corrección de documentación en FASE 18**: `Referrer-Policy` y
`Cross-Origin-Opener-Policy` ya estaban activos desde siempre —
Django 3.0/4.0 los aplica por defecto (`same-origin`) sin necesitar
ningún setting explícito en `config/settings.py`; la versión anterior
de este documento los listaba incorrectamente como "pendiente". Se
verificó con una request real (`apps.core.tests.
HttpSecurityHeadersTests`) y quedan bloqueados por regresión.
**Construido en FASE 18**: HSTS (`SECURE_HSTS_SECONDS`/
`_INCLUDE_SUBDOMAINS`/`_PRELOAD`, solo con `DEBUG=False`, arranque
conservador de 1 día — ver el razonamiento completo en
`config/settings.py`, sube progresivamente una vez confirmado el
despliegue HTTPS real en FASE 21) y `Permissions-Policy`
(`apps.core.security_headers.PermissionsPolicyMiddleware`, middleware
propio de una sola cabecera en vez de una dependencia nueva —
deshabilita cámara/micrófono/geolocalización/USB/pago del navegador,
capacidades que esta aplicación nunca usa). Ambos verificados con test
(`HttpSecurityHeadersTests`).
**Diferido deliberadamente, con razón explícita** (no un descuido):
`SECURE_SSL_REDIRECT` — depende de que el proxy real de producción
(Nginx, FASE 21) reenvíe `X-Forwarded-Proto` de forma confiable;
activarlo sin esa verificación real arriesga un bucle de redirección
que deje el sitio inaccesible. Una Content-Security-Policy real —
exigiría antes una auditoría de TODAS las plantillas para separar
estilo/script inline existente (o migrar a nonce); introducirla a
ciegas en esta fase habría arriesgado justo lo que la fase pide evitar
("no introducir una CSP incompatible con la aplicación sin probarla").
El proyecto sigue sin exponer una API pública consumida desde otro
origen salvo `/api/v1/` (autenticada por credencial, no por cookie) y
el webhook de PayPal (POST server-to-server) — sin necesidad de CORS
de navegador, confirmado en esta fase.

## Secrets, logging y errores
**Construido**: `.env` fuera de Git (`.gitignore`), `DJANGO_SECRET_KEY`
obligatorio sin default inseguro, credenciales de PayPal/DB por
variable de entorno; ningún secreto se audita (`apps.audit`,
`apps.billing.services._saas_audit`); `apps.audit` redacta
explícitamente cualquier clave que contenga "pass"/"secret"/"token"/
"clave".
**Pendiente / fuera de alcance de esta pasada**: revisión de `DEBUG`/`ALLOWED_HOSTS` en un
despliegue real, y de que ningún traceback en producción exponga
información de otro tenant.

## Rate limiting / abuse
**Construido**: `ApiKeyRateThrottle`/`CatalogRateThrottle` (DRF,
120/min configurable), throttle básico por IP en el webhook de PayPal.
**Construido en FASE 18**: login y recuperación de contraseña (ver
sección "Autenticación" arriba) — `apps.accounts.rate_limit`, mismo
backend de caché, sin Redis (no se justifica: un solo proceso).
**Diferido deliberadamente**: límite de tasa dedicado en cada endpoint
sensible restante fuera de `/api/v1/` (ej. formularios de creación
dentro del ERP operativo) — no priorizado porque, a diferencia de
login/reset, esas vistas ya exigen sesión autenticada + tenant activo
(`TenantRequiredMixin`), reduciendo el riesgo de abuso anónimo; queda
como hardening futuro si el uso real lo justifica. Redis sigue sin
justificación real de necesidad (`LocMemCache` de un solo proceso
sigue siendo suficiente).

## Reports / Exports
**Construido**: `apps.reports`/`apps.billing.services.reports` nunca
introducen un modelo propio (agregan sobre servicios existentes);
información sensible de RRHH/Nómina se filtra en el servidor
(`can_view_sensitive_employee_data`), nunca solo oculta en la UI;
exportaciones PDF/XLSX (`apps.reports.exports`, `reportlab`/`openpyxl`)
tenant-scoped.
**Hallazgo real corregido en FASE 18**: ni la exportación CSV
(`apps.reports.views._csv_response`) ni la XLSX (`apps.reports.
exports.xlsx_response`) neutralizaban CSV/XLSX Formula Injection — un
cliente/proveedor/producto con un nombre que empezara con
`=`/`+`/`-`/`@` (ej. `=cmd|'/c calc'!A1`) se escribía crudo en la
celda, y Excel/Sheets lo interpretaría como fórmula al abrir el
reporte exportado. Corregido con un único helper compartido
(`apps.core.utils.sanitize_cell_value`, antepone un apóstrofe a
cualquier `str` que empiece con esos caracteres — nunca toca números/
`Decimal`/fechas reales), reutilizado por ambos exportadores — nunca
una sanitización distinta por formato. La exportación PDF
(`reportlab`) no estaba expuesta a este riesgo (nunca interpreta
fórmulas). Verificado con pruebas negativas reales
(`apps.reports.tests.test_views`, un cliente con nombre-fórmula real,
tanto para CSV como XLSX — se abre el XLSX resultante con `openpyxl`
para confirmar la celda neutralizada).
**Verificado, sin hallazgo**: nombres de archivo de exportación
revisados uno por uno — son siempre un literal fijo en el código
(`ventas.csv`, `inventario.csv`, ...) o un prefijo fijo + el ID
numérico (`pk`) del registro (`estado_cuenta_{cliente.pk}.csv`), nunca
un campo de texto libre del usuario (nombre, referencia, nota); no hay
vector de path traversal/inyección de nombre de archivo en esta
superficie.

## Audit Log
**Construido**: `apps.audit.AuditLog` (dominio transversal) + 7
`*ActivityLog` por dominio + dominios `"billing_paypal"`/`"billing_saas"`
— todos con actor/tenant (nullable cuando corresponde)/timestamps;
inmutable (sin update/delete); nunca registra secretos.
**Pendiente / fuera de alcance de esta pasada**: verificación exhaustiva de que TODOS los
eventos críticos listados en el checklist de fase quedan auditados.

## Concurrencia
**Construido**: `TransactionTestCase` + hilos reales en cada dominio
con dinero/inventario (pagos, allocations, aprobaciones, activaciones,
webhooks, generación de factura) desde FASE 8 — exactamente una
operación gana cuando el negocio exige exclusividad.
**Verificado en FASE 18**: rotación de `ApiKey` bajo concurrencia
(`apps.api.tests.test_concurrency`, nuevo archivo, mismo patrón
`TransactionTestCase` + hilos + `threading.Barrier`). `rotate_api_key`
no usa `select_for_update()` porque no lo necesita para su única
garantía real (nunca dos claves activas — siempre reescribe la misma
fila, nunca inserta una segunda); bajo dos rotaciones simultáneas gana
la que guarda último (last-write-wins), documentado y aceptado como
ambigüedad de UX menor — nunca una fila duplicada, un tenant sin
ninguna clave activa, ni una excepción no controlada. Verificado con
evidencia real, no solo argumentado.

## Dependencias
**Escaneado en FASE 18** con `pip-audit` (herramienta oficial de PyPA,
instalada localmente solo para el escaneo, no agregada a
`requirements.txt`) contra el entorno realmente instalado: **sin
vulnerabilidades conocidas** en Django 5.2.17, psycopg 3.3.4,
djangorestframework 3.18.0, python-dotenv 1.2.3, gunicorn 23.0.0,
reportlab 4.5.1, openpyxl 3.1.5, Pillow 12.3.0.
**Hallazgo real corregido**: `requirements.txt` fijaba
`Pillow>=10.4,<12.0` — ese rango permite instalar Pillow 11.3.0 en un
despliegue nuevo (ej. FASE 21, Hostinger), versión con 25
vulnerabilidades conocidas ya corregidas en 12.1.1+ (la propia
instalación local ya tenía 12.3.0, por eso el entorno actual no estaba
afectado, pero el RANGO del archivo sí lo habría permitido en una
instalación limpia). Corregido a `Pillow>=12.3,<13.0` — cambio mínimo
y dirigido a la única dependencia con hallazgo real, nunca una
actualización masiva de las demás.

## Qué se construyó en FASE 18 (resumen)
Throttling real de login/recuperación de contraseña; cabeceras HTTP
HSTS/`Permissions-Policy` (más la corrección de que `Referrer-Policy`/
`Cross-Origin-Opener-Policy` ya estaban activas por defecto);
neutralización de CSV/XLSX Formula Injection en las exportaciones de
`apps.reports`; cobertura de aislamiento Multi-Tenant que faltaba en
el Portal de Facturación; cobertura HTTP real del webhook de PayPal
que faltaba; cobertura de concurrencia en rotación de `ApiKey`;
corrección del rango de Pillow en `requirements.txt`. El detalle
completo, hallazgo por hallazgo con severidad/reproducción/corrección/
test/resultado, y lo explícitamente diferido (CSP, SSL redirect
forzado, rate limit por endpoint fuera de auth), vive en el reporte de
cierre de `docs/phases/PHASE-18-security-hardening.md`.
