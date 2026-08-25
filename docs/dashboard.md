# Dashboard / Panel (FASE 7)

Panel administrativo en `/panel/` (`apps/dashboard`), destino real tras
iniciar sesión u onboardear (antes, en FASE 4, era el perfil). Usa
exclusivamente el shell y los componentes del Design System de FASE 5;
no introduce una identidad visual nueva.

## Arquitectura: capa de servicios como punto de extensión

`apps/dashboard/services.py` concentra toda la obtención de datos en
funciones puras que reciben `tenant` explícitamente:

- `obtener_kpis(tenant)` — KPIs principales.
- `obtener_actividad_reciente(tenant, limite=5)` — actividad reciente.
- `obtener_alertas(tenant)` — alertas derivadas de datos reales.
- `obtener_datos_del_panel(tenant)` — agrega las tres anteriores y
  aísla errores (ver "Estado de error" abajo).

Cuando FASE 8+ agregue ventas, inventario, compras, gastos, clientes o
reportes, cada módulo reemplazará la función de KPI correspondiente
(hoy con `estado="vacio"`) por su consulta real — **sin tocar la vista
ni la plantilla**, que solo iteran sobre lo que la función devuelva. Este
es precisamente el mecanismo que permite "alimentar métricas sin
rehacer el layout", pedido explícitamente para esta fase.

## Jerarquía visual (orden pedido)

1. **Encabezado y contexto**: saludo con el nombre del usuario, nombre de
   la empresa y rol.
2. **KPIs principales** (`.kpi-grid`): tira de estadísticas — deliberadamente
   **no** son `.tarjeta`, para que el panel no se lea como una colección
   de cards. "Miembros del equipo" es un dato real (`tenants_membership`
   filtrado por tenant); Ventas/Inventario/Gastos se muestran con
   `estado="vacio"` porque esos módulos todavía no existen — nunca un
   número inventado.
3. **Tendencias / análisis**: como no hay datos de series de tiempo
   todavía, se muestra una vista previa tipo *skeleton* (barras grises,
   `.tendencia-preview`) con una leyenda explícita ("Vista previa: ...").
   Nunca se dibuja un gráfico con números fabricados.
4. **Alertas importantes**: derivadas de datos reales (p. ej. "todavía
   eres el único miembro del equipo"); si no aplica ninguna, estado
   vacío ("Sin alertas").
5. **Actividad reciente**: eventos reales de alta de miembros del equipo
   (único evento que existe hoy; un log de auditoría completo por
   módulo es FASE 15). Estado vacío si el tenant solo tiene al dueño.
6. **Acciones rápidas**: enlaces reales (Ver mi perfil, Cambiar
   contraseña) + botones **deshabilitados** con badge "Próximamente"
   para acciones de módulos que aún no existen (Agregar producto,
   Registrar venta) — nunca un enlace muerto (`href="#"`).

## Multi-Tenancy y seguridad

- `DashboardView` exige `LoginRequiredMixin`; si el usuario autenticado
  no tiene tenant activo (`request.tenant is None`), se redirige a
  onboarding (no un 403: en el flujo normal, llegar aquí sin tenant
  significa que falta completar el onboarding).
- Todas las consultas de `services.py` reciben `tenant` explícitamente y
  filtran por él (`Membership.objects.filter(tenant=tenant, ...)`) —
  **ninguna consulta global**. `Membership` no hereda de
  `TenantScopedModel` (ver `docs/multi-tenancy.md`), así que el filtro
  por tenant se escribe a mano en cada función, nunca se omite.
- Permisos: cualquier miembro activo del propio tenant (`OWNER` o
  `MEMBER`) puede ver el panel — no hay restricción por rol para la
  sola visualización, verificado con test explícito.
- 8 tests de aislamiento/seguridad en `apps/dashboard/tests.py`
  (`DashboardSecurityTests`, `DashboardIsolationTests`), incluyendo una
  regresión directa de FASE 3: manipular `active_tenant_id` en sesión no
  filtra datos de otro tenant.

## Performance

- `obtener_actividad_reciente` usa `select_related("user")` para evitar
  N+1 al mostrar el nombre/email de cada miembro.
- Los conteos de KPI usan `.count()` (agregación en la base de datos),
  nunca `len(list(...))`.
- Se agregó un índice compuesto a `Membership`
  (`tenant, is_active, created_at` — migración
  `tenants/0002_membership_idx_membership_tenant_activo`), que cubre
  exactamente el patrón de consulta del panel (filtrar por tenant activo,
  ordenar por fecha).
- Verificado con un test que compara el número de queries del panel con
  1 miembro vs. 10 miembros: **debe ser idéntico** (prueba directa de
  ausencia de N+1, no solo una suposición).

## Estados de UX

| Estado | Cómo se ve |
|---|---|
| **Success** | KPI real ("Miembros del equipo: 2+"), actividad reciente con eventos reales, sin alerta de "único miembro". |
| **Empty** | KPIs de módulos inexistentes (`estado="vacio"`), "Aún no hay actividad reciente", alerta "todavía eres el único miembro". |
| **Error** | Si una fuente de datos lanza una excepción, `obtener_datos_del_panel` la captura y registra (`logging`), y la plantilla muestra una alerta de error en vez de un 500. Verificado con un test que fuerza el fallo (`mock.patch`). |
| **Loading** | No hay fetch asíncrono todavía (todo se renderiza en el servidor); el patrón "cargando" se representa con la vista previa tipo skeleton de Tendencias, reutilizando el componente `.skeleton`/`.tendencia-preview` ya existente. Cuando una fase futura agregue actualización en vivo por JavaScript, ese mismo patrón visual servirá de estado de carga real. |

## Responsive y accesibilidad
Hereda el shell responsive de FASE 5 (sidebar colapsable en ≤1024px).
Las cuadrículas de KPIs y acciones rápidas usan `auto-fit`/`minmax` y
`flex-wrap`, adaptándose sin puntos de quiebre adicionales. El diagrama
de tendencias usa `role="img"` con `aria-label` descriptivo (no expone
barras decorativas sin sentido a un lector de pantalla); los botones de
acciones futuras usan `disabled` + `aria-disabled="true"` (nunca un
enlace roto) con `title` explicando cuándo estarán disponibles.

## Qué NO se construyó en esta fase (deliberado)
Productos, inventario funcional, ventas, POS, compras, gastos, API de
Inventario, PayPal, Billing. Los KPIs y acciones rápidas relacionados
con esos módulos se muestran explícitamente como "vacío" o
"Próximamente".
