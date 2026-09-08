# FASE 20 — Backups + Disaster Recovery Profesional

## 0. Objetivo
Implementar y verificar una estrategia profesional de respaldo y recuperación para el ERP SaaS.

Debe cubrir PostgreSQL backup, restore real, verification, integridad, retención, scheduling, almacenamiento seguro, copia off-site, cifrado cuando corresponda, archivos/media, configuración, monitoreo, RPO/RTO y restore drill.

No basta con demostrar que `pg_dump` genera un archivo.

## 1. Regla incremental
Implementar únicamente lo necesario para esta fase y sus dependencias inmediatas.

No iniciar FASE 21. No implementar despliegue completo de Hostinger ni migración definitiva de producción.

## 2. Auditoría previa
Leer CLAUDE.md, docs/MASTER-PROMPT.md, ARCHITECTURE.md, FASES 0–19 y estado del proyecto. Revisar PostgreSQL, inventario/media, uploads, Billing y archivos privados. Inspeccionar configuración y código reales antes de modificar.

## 3. Estrategia de backup
Definir y documentar:

```text
Database Backup
+
Application Files/Media Backup
+
Configuration Recovery
```

No asumir que PostgreSQL recupera archivos.

## 4. PostgreSQL
Implementar y verificar backup real con `pg_dump`. Evaluar formato, compresión y compatibilidad. Registrar fecha/hora, base, versión, tamaño, duración, resultado, checksum y ubicación. No incluir credenciales.

## 5. Restore real
Obligatorio: backup real → base temporal/aislada → restore → conexión → verificación. Nunca destruir la base principal de desarrollo para probar restore.

## 6. Restore verification
Verificar conexión, tablas, migraciones, conteos críticos, relaciones y constraints. Comprobar datos representativos de tenants, productos, inventario, seriales, ventas, pagos, compras, gastos, RRHH/nómina, contabilidad, Billing y auditoría.

## 7. Integridad y checksum
Detectar backup incompleto, truncado, corrupto o con checksum incorrecto. Usar checksum criptográfico estándar y comprobar que alteraciones sean detectadas antes de restaurar.

## 8. Retention
Definir política para diarios, semanales y mensuales. Nunca borrar automáticamente el último backup válido. Probar la política.

## 9. Scheduling
Definir ejecución programada. Preferir cron/systemd u otra herramienta adecuada del VPS antes que implementar un scheduler Django sin necesidad. No depender de runserver.

## 10. Local + Off-site
No confiar solo en el VPS. Preparar arquitectura local + copia externa/off-site. Nunca exponer backups vía HTTP.

## 11. Cifrado
Evaluar cifrado, especialmente para copias off-site. No inventar criptografía. No guardar la clave junto al backup.

## 12. Media y archivos
Incluir en la estrategia los documentos privados, PaymentProof, ProductImage y demás uploads. Definir y probar backup/restauración de DB + archivos.

## 13. Configuración y recuperación
Documentar variables de entorno, PostgreSQL, storage, dominio/hosts cuando corresponda, secretos, PayPal e integraciones necesarios para reconstruir el sistema. Nunca incluir secretos reales sin protección.

## 14. Secrets
Separar datos del sistema de secretos de infraestructura. Los secretos de recuperación deben seguir una política de custodia segura y separada.

## 15. RPO / RTO
Definir y documentar RPO y RTO. Si el negocio aún no fija valores definitivos, proponer valores iniciales razonables y marcarlos como propuesta, no como decisión empresarial definitiva.

## 16. Disaster Recovery Runbook
Crear procedimiento reproducible: identificar incidente, proteger evidencia, provisionar entorno, instalar PostgreSQL, restaurar DB, restaurar media, configurar environment, ejecutar migrations/check, verificar integridad, smoke y habilitar servicio.

## 17. Restore Drill
Ejecutar al menos un restore completo real con datos de prueba representativos y dejar evidencia de backup, checksum, duración, restauración y verificación.

## 18. Failure Testing
Probar backup fallido, credenciales inválidas, storage no disponible, archivo corrupto, checksum incorrecto, restore incompleto y espacio insuficiente cuando sea simulable. Nunca marcar como válido un backup fallido.

## 19. Monitoring / Notifications
Documentar detección de backup fallido, verification fallida, almacenamiento lleno, backup demasiado antiguo y off-site no disponible. Puede quedar preparado para monitorización futura sin inventar infraestructura.

## 20. Seguridad
Revisar permisos de archivos, ubicación fuera de web root, ownership, acceso administrativo, descarga pública, logs, secretos, cifrado y retención. Un backup nunca debe quedar públicamente accesible.

## 21. Multi-Tenant
Los backups completos contienen todos los tenants. El acceso debe ser de plataforma/infraestructura; ningún usuario tenant puede descargar un backup global.

## 22. Performance
Medir duración, tamaño, compresión y duración del restore. Evitar impacto innecesario sobre operaciones comerciales.

## 23. Automatización
Si existe script, debe ser idempotente, manejar errores, usar exit codes correctos, producir logs seguros, verificar espacio, checksum y resultado, aplicar retention y proteger el último backup válido.

## 24. Naming
Usar esquema consistente, por ejemplo `erp_YYYYMMDD_HHMMSS.dump` y su checksum. No incluir secretos.

## 25. Tests
Crear tests para checksum, retention, invalid backup, restore verification, failure handling, access control y secret leakage. Combinar tests automatizados con restore/smoke real.

## 26. Smoke Test Real
Demostrar: crear datos de prueba → backup real → checksum → restore a base aislada → check → migrations check → verificar datos → verificar media → smoke funcional.

## 27. Restore Version Compatibility
Registrar versión de PostgreSQL y formato de backup. Documentar compatibilidad esperada. No asumir compatibilidad universal entre versiones futuras.

## 28. No inventar infraestructura
No agregar cloud storage, Redis, S3, cron externo u otro componente solo para completar la fase. Cuando una pieza requiera infraestructura aún no disponible, documentar y probar el equivalente local/aislado.

## 29. Criterios de aceptación
- [ ] backup PostgreSQL real
- [ ] restore PostgreSQL real
- [ ] restore verification real
- [ ] checksum y detección de corrupción
- [ ] retention
- [ ] scheduling/documentación
- [ ] off-site preparado/documentado
- [ ] cifrado evaluado/implementado cuando corresponda
- [ ] media/files recovery
- [ ] configuration recovery
- [ ] RPO/RTO documentados
- [ ] disaster recovery runbook
- [ ] restore drill
- [ ] failure testing
- [ ] monitoring/documentación
- [ ] security review
- [ ] Multi-Tenant/platform isolation
- [ ] performance measurements
- [ ] tests
- [ ] smoke
- [ ] documentación
- [ ] Git commit
- [ ] working tree limpio

## 30. Reporte final obligatorio
Entregar: estrategia de backup, formato, compresión, tamaño, duración, entorno y duración del restore, verification, retention, scheduling, off-site, encryption, RPO/RTO, runbook, restore drill, security, tests, smoke, regression, documentación, Git y pendientes. No inventar resultados.

## 31. Regla de parada
FASE 20 termina aquí. No iniciar FASE 21. Entregar reporte y DETENERSE.
