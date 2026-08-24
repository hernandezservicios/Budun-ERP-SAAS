# Runbook de integraciones

## PostgreSQL + pgAdmin 4

Seguir `windows-postgresql-pgadmin-step-by-step.md`.

## PayPal

1. Usar Sandbox primero.
2. Obtener credenciales desde el portal oficial de PayPal.
3. Guardar secretos solamente en `.env` o secret management.
4. Implementar en FASE 16.
5. Probar Orders, Payments, Subscriptions y Webhooks según el alcance aprobado.
6. No activar Production hasta FASE 23.

## PayPal MCP

Claude debe consultar documentación oficial vigente antes de configurar MCP. No inventar herramientas, argumentos, paquetes ni endpoints. MCP es una herramienta del agente/desarrollo/operación; el frontend nunca debe depender directamente de él.

## GitHub

1. Crear repositorio privado o con la visibilidad decidida por el propietario.
2. No subir `.env`, credenciales, claves ni dumps.
3. Activar CI de tests.
4. Deployment automatizado solo cuando la FASE 21 esté aprobada.

## Hostinger VPS

1. Crear VPS.
2. Verificar OS y recursos.
3. Configurar SSH.
4. Instalar/configurar Python, PostgreSQL, Gunicorn y Nginx o la alternativa oficial apropiada.
5. Configurar firewall.
6. Configurar dominio y DNS.
7. Configurar SSL.
8. Clonar repositorio.
9. Configurar variables de entorno.
10. Ejecutar migrations.
11. Crear superuser.
12. Arrancar Gunicorn.
13. Configurar Nginx.
14. Probar health endpoint.
15. Ejecutar smoke tests.
