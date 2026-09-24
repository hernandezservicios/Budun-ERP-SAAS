# ERP DESIGN LAB (FASE 3)

Exploración visual de las pantallas reales del ERP aplicando Atlas
(`docs/erp-redesign-design-system.md`) — previa a Stitch e implementación.
No es productivo: ningún archivo del ERP real (`templates/`, `static/`,
vistas, forms, modelos, URLs, POS) fue tocado para construirlo.

**Artifact**: [Atlas ERP Lab](https://claude.ai/artifact/XVrBtYd9pgiw77zxJoetqK)
— página interactiva con el shell real de Atlas persistente (sidebar de 21
módulos/8 grupos, topbar), un conmutador de Modo Día/Noche y 16 secciones
navegables desde una barra de control propia del Lab (visualmente distinta
del ERP simulado, para que nunca se confunda herramienta con producto).
Cuatro secciones (Dashboard, List, Detail, Forms) incluyen 3 variantes
comparables con un solo clic, usando siempre la misma información funcional
real — nunca datos ni campos distintos entre variantes.

No se diseñaron las ~140 pantallas una por una: se seleccionaron pantallas
representativas que cubren los patrones principales del ERP, tal como pidió
la instrucción de esta fase.

## Organización (16 secciones)

| # | Sección | Pantalla real usada | Variantes |
|---|---|---|---|
| 01 | Shell | Sidebar + topbar (colapso funcional, responsive) | — |
| 02 | Dashboard | Panel — KPIs, alertas, actividad, accesos rápidos | A Operativo · B Analítico · C Compacto |
| 03 | List | Listado de Ventas (Número/Cliente/Fecha/Estado/Total) | A Estándar · B Compacta · C Jerarquía alta |
| 04 | Detail | Detalle de Venta VEN-00231 (resumen, líneas, pagos) | A Info primero · B Acción primero · C Denso |
| 05 | Forms | Nuevo gasto (6 campos reales) | A Una columna · B Dos columnas · C Secciones |
| 06 | Finance | Cobros de cliente (facturas pendientes, selección múltiple) | — |
| 07 | Inventory | Inventario + movimientos de un producto por cantidad | — |
| 08 | Sales | Lista → Detalle → Acciones como flujo único | — |
| 09 | Purchases | Órdenes de compra (progreso de recepción real) | — |
| 10 | HR | Detalle de empleado (gating real de datos sensibles) | — |
| 11 | Payroll | Líneas de nómina (una tabla, Categoría + Concepto) | — |
| 12 | Reports | Reporte de Ventas (con exportación real) | — |
| 13 | Configuration | Hub de Configuración + API Key (secreto una vez) | — |
| 14 | Approvals | Pendientes de autorización | — |
| 15 | Empty/Error states | Vacío, sin resultados, carga, error (403) | — |
| 16 | POS preliminary | Terminal — búsqueda, carrito, pago | — |

Cada sección cita el módulo/campos/columnas/acciones exactamente como están
documentados en `docs/erp-redesign-map.md` — ningún campo, botón, estado o
pantalla fue inventado. Donde el Lab usa una cifra o nombre concreto (p. ej.
"Ferretería Central S.R.L.", "RD$ 12,450.00"), es ilustrativo, no un dato
real del sistema.

## Cómo revisarlo

El artifact responde directamente a las preguntas de la sección 19 de esta
fase: navega por las 16 secciones con la barra de control, compara variantes
con un clic donde existan, y activa el Modo Noche para evaluar el POS y el
resto del sistema bajo esa condición. El detalle de qué decisión se propone
congelar en cada patrón con variantes está en el documento complementario:
`docs/erp-redesign-design-lab-decision-log.md`.

## Qué sigue

Después de tu revisión del Lab y del Decision Log: **FASE 4 — Stitch Final
Screens**, donde las decisiones que confirmes aquí se congelan en pantallas
finales. Ningún archivo productivo se toca hasta FASE 5. Me detengo aquí.
