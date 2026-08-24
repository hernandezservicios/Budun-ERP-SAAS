# Seguridad de Agentes IA

El agente CRM IA debe usar HTTPS y la API v1. Nunca acceder directamente a PostgreSQL. Las API Keys son tenant-scoped, read-only por defecto y con rate limiting y auditoría. Mantener la key fuera del frontend y del prompt público.
