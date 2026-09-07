# ADENDUM — FASE 8 Products + Inventory
## Importación y exportación masiva de productos mediante Excel

### Objetivo
Agregar al módulo Productos una capacidad profesional de carga masiva mediante archivos Excel `.xlsx`.

No usar CSV como formato principal de importación/exportación de productos.

### Ubicación funcional
```text
Inventario
└── Productos
    ├── Nuevo
    ├── Editar
    ├── Importar Excel
    ├── Exportar Excel
    └── Descargar plantilla
```

### Formato
Formato principal: `Microsoft Excel Open XML — .xlsx`.
El archivo debe presentar columnas normales de Excel, con encabezados, formatos y validaciones cuando sea posible.

### Plantilla de productos
Debe existir `Descargar plantilla`.
Evaluar únicamente columnas soportadas por el modelo real: SKU, barcode, nombre, descripción, marca, modelo, categoría, tracking, precio, moneda, impuesto, stock mínimo, unidad de medida, estado y atributos de variante.
No inventar columnas que el modelo no soporte.

### Crear vs actualizar
`CREATE` para SKU inexistente; `UPDATE` para SKU existente.
El criterio principal de matching es SKU, respetando unicidad por tenant. Barcode solo como criterio secundario si la arquitectura real lo permite. Nunca usar nombre como identificador de actualización.

### Prevalidación obligatoria
No guardar al subir. Flujo:
`Subir Excel → validar → detectar CREATE/UPDATE → preview → corregir → confirmar → guardar`.
Mostrar total, nuevos, actualizaciones, advertencias y errores.

### Modo estricto
Predeterminado `STRICT`: un error bloquea la confirmación completa. Un modo tolerante puede quedar para futuro, no por defecto.

### Validaciones
Encabezados requeridos, columnas desconocidas, SKU vacío/duplicado, barcode duplicado, categorías inexistentes, precios/monedas/impuestos/tracking inválidos, tipos incorrectos, longitudes y filas vacías. Usar las mismas reglas del dominio Product.

### Resultado
Ejemplo:
`Importación #IMP-000123 — Total 5,000 — Creados 4,100 — Actualizados 820 — Errores 80`.
Generar reporte de errores descargable en Excel. Auditar usuario, fecha, tenant, archivo y resultado.

### Actualización segura
La importación de catálogo NO modifica silenciosamente stock, StockMovement, InventoryUnit, IMEI, Serial, costos históricos, COGS, movimientos, saldos ni contabilidad.
La carga de stock inicial debe usar flujo separado y `apps.inventory.services`.

### Productos SERIALIZED
La plantilla general administra catálogo, no unidades serializadas existentes. Si se requiere carga masiva de unidades, diseñar `Unidades-Serializadas.xlsx` separada, usando los servicios oficiales de inventario y validando unicidad/formato/estado.

### Variantes
Respetar `variant_attributes` y campos reales. Soportar color, capacidad, almacenamiento, talla, presentación y otros atributos sin crear columnas infinitas.

### Exportación
Debe existir `Exportar productos.xlsx`, respetando tenant y permisos y sin campos sensibles.

### Seguridad
Autorización server-side, tenant isolation, validación del archivo, límites de tamaño/filas, almacenamiento temporal seguro, eliminación de temporales, no macros, sanitización de exportaciones y no confianza ciega en valores del cliente.

### Performance
Para catálogos grandes, evaluar chunks/batches, bulk operations seguras y evitar N+1. Límite configurable de filas/archivo.

### Idempotencia
Registrar referencia de importación y evitar duplicados ante reintentos.

### Precios
Cambios de precio deben usar reglas del dominio y preservar historial/snapshots cuando corresponda. No alterar facturas históricas.

### Integración con catálogo
La carga actualiza los mismos `Product` consumidos por ventas, POS, compras, reportes, Catalog API y futura integración WACRM. No crear catálogo paralelo.

### Criterios de aceptación
- [ ] plantilla `.xlsx`
- [ ] columnas normales de Excel
- [ ] descargar plantilla
- [ ] subir `.xlsx`
- [ ] preview
- [ ] CREATE
- [ ] UPDATE
- [ ] matching por SKU
- [ ] validación completa
- [ ] modo estricto
- [ ] reporte de errores
- [ ] auditoría
- [ ] tenant isolation
- [ ] exportación `.xlsx`
- [ ] performance para catálogos grandes
- [ ] no modifica stock
- [ ] SERIALIZED separado
- [ ] tests
- [ ] smoke
- [ ] documentación

### Dependencias
Reutilizar `apps.inventory`, `Product`, categorías, impuestos, permisos, auditoría, validación de archivos y exportaciones existentes. No crear segundo motor de productos.

### Relación con FASE 14
Los reportes pueden exportar inventario/catálogo según sus capacidades. La importación/exportación operativa de maestros de productos pertenece a Productos/Inventario.

### Relación con FASE 19
Debe respetar optimizaciones de performance: batch/bulk seguro, evitar N+1, query counts cuando aporten y transactions razonables.

### Relación con FASE 22
FASE 22 puede reutilizar esta capacidad para migraciones iniciales, pero la migración completa mantiene su propio procedimiento de reconciliación e integridad.
