# CLAUDE.md — ERP SaaS Multi-Tenant

## Mandato
Construir desde cero un SaaS ERP Multi-Tenant profesional con Django + PostgreSQL + pgAdmin 4, sin Docker, sin MySQL y sin WAMP como dependencia del proyecto.

## Arquitectura oficial
- Desarrollo: Windows + Python + virtualenv + Django + PostgreSQL + pgAdmin 4 + Git.
- Producción: Hostinger VPS + Linux + PostgreSQL + Django + Gunicorn + Nginx (o servidor web equivalente si la infraestructura real lo recomienda) + SSL.
- Redis solo si una fase posterior demuestra necesidad real.
- PayPal y PayPal MCP según documentación oficial vigente.

## Prohibiciones
- No crear Dockerfile.
- No crear docker-compose.*.
- No utilizar Docker Desktop/Engine.
- No utilizar MySQL/MariaDB.
- No usar Django Admin como UI principal.
- No exponer secretos.

## Idioma y UX
Toda la UI visible debe estar en español. Diseño moderno, profesional, limpio, sobrio y muy legible. La dirección visual la decide el agente técnico, priorizando UX y claridad. Azul y verde forman la identidad, sin colores raros, neón, arcoíris ni efectos excesivos.

## Multi-tenancy
Toda entidad empresarial es tenant-scoped. Una API Key pertenece a un único tenant. Tenant A nunca puede leer o modificar datos de Tenant B. El backend determina el tenant; no se confía en IDs enviados por el frontend.

## API de Inventario
Existe una sección Configuración → API de Inventario. Debe incluir Base URL /api/v1/, generación/rotación/revocación de API Key, visibilidad segura de la clave, prueba real de conexión, estado, última prueba, último error y auditoría. La API es READ-ONLY por defecto y está preparada para agentes CRM IA.

Endpoints iniciales previstos: GET /api/v1/health/, /products/, /products/{id}/, /categories/, /inventory/, /inventory/low-stock/, /inventory/movements/.

## Inventario: por cantidad y serializado
Todo producto tiene un tipo de seguimiento de inventario: QUANTITY (por cantidad) o SERIALIZED (IMEI/número de serie), incorporado oficialmente a partir de FASE 8. Cada tipo tiene una única fuente de verdad, nunca dos a la vez para el mismo producto:
- QUANTITY → `StockMovement` (libro mayor append-only). Stock actual = `stock_after` del movimiento más reciente.
- SERIALIZED → `InventoryUnit` (una fila por unidad física real). Disponibilidad = conteo de unidades en estado EN_STOCK.

Prohibido introducir un campo de stock desnormalizado o una segunda fuente de verdad para cualquiera de los dos tipos. Un producto no puede cambiar de tipo de seguimiento una vez que ya tiene movimientos o unidades registradas.

Unicidad de identificadores de `InventoryUnit` (serial, IMEI 1, IMEI 2): únicos **por tenant**, nunca global, y solo entre valores no vacíos (varias unidades pueden no tener alguno de los tres). IMEI 1 nunca puede ser igual a IMEI 2. Toda unidad debe tener al menos un identificador no vacío. Ver `docs/inventory.md` para el detalle completo (estados, máquina de estados, búsqueda unificada, reglas de venta).

## Fases
Exactamente 25 fases: 0–24. No saltar, fusionar ni crear nuevas fases sin justificación documentada.

## Ciclo de fase
Analizar → planificar → implementar → ejecutar → probar → corregir → volver a probar → documentar → commit → cerrar.

## Criterio de PASS
Una fase solo pasa si está implementada, ejecutada y verificada con evidencia.

## Seguridad
CSRF, XSS, SQL injection protection, auth/authz, secure cookies, rate limiting, tenant isolation, webhook verification, secrets fuera de Git, logs sin secretos, auditoría.

## Datos y dinero
PostgreSQL con constraints, índices y transacciones apropiadas. Usar Decimal para dinero. Operaciones de venta/pago/inventario deben ser atómicas.

## Git
Commit por fase. No hacer commits gigantes. No commitear .env, API keys, passwords, tokens, dumps ni claves privadas.

## Regla de parada
Al terminar una fase, generar un reporte y detenerse hasta recibir autorización para la siguiente fase, salvo que el usuario haya indicado expresamente que se pueden ejecutar las siguientes fases en la misma instrucción.

## Fuente de verdad
Este archivo, docs/MASTER-PROMPT.md y docs/phases/PHASES.md son la fuente de verdad del proyecto. Si hay conflicto, prevalecen en ese orden.


## Construcción incremental
Claude NO debe crear toda la estructura del ERP en la FASE 1. Debe crear únicamente los archivos, apps, modelos, servicios, templates, pruebas y documentación necesarios para la fase activa y sus dependencias inmediatas. Puede preparar interfaces de extensión, pero no debe implementar funcionalidades futuras anticipadamente. Cada fase amplía el proyecto de manera incremental.

## PostgreSQL + pgAdmin 4
Antes de configurar la base local, leer `docs/setup/windows-postgresql-pgadmin-step-by-step.md`. Claude debe detectar instalación, servicio, puerto y versión de PostgreSQL. Si puede crear DB/usuario por CLI de forma segura, puede hacerlo; pgAdmin 4 se usa para administrar y verificar. Si se necesita una contraseña o confirmación que solo el usuario puede suministrar, detenerse y dar instrucciones paso a paso.

## Integraciones
Para PayPal, PayPal MCP, GitHub y Hostinger, Claude debe consultar documentación oficial vigente cuando la implementación llegue a esa fase. Nunca inventar endpoints, herramientas MCP, argumentos o configuraciones.
