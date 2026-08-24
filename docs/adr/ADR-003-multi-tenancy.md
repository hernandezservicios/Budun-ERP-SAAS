# ADR-003 — Multi-Tenancy con aislamiento por tenant

## Decisión
Single database PostgreSQL con relaciones tenant-aware y aislamiento estricto en backend.

## Requisito
Ningún tenant puede consultar o modificar datos de otro tenant.
