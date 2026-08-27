# INSTRUCCIÓN — SINCRONIZAR FASE 16 + FASE 17

## IMPORTANTE

Esto es SOLO sincronización documental.

NO implementar FASE 16.
NO implementar FASE 17.
NO crear modelos, migraciones, servicios, endpoints ni código funcional.

## PASO 1

Leer:

`docs/phases/PHASE-16-paypal-sandbox.md`

`docs/phases/PHASE-17-billing-saas.md`

y este paquete maestro si fue copiado:

`FASES_16_17_DEFINITIVAS.md`

## PASO 2

Comparar contra las fuentes de verdad actuales:

- `CLAUDE.md`
- `docs/MASTER-PROMPT.md`
- `ARCHITECTURE.md`
- `docs/paypal.md`
- `docs/billing.md`
- `docs/accounts-receivable.md`
- `docs/currency.md`
- `docs/approvals.md`
- `docs/reports.md`
- `FASES_OFICIALES_0_24_ACTUALIZADAS.md`
- `docs/project-status/CURRENT_PHASE.md`
- `docs/project-status/PHASE_HISTORY.md`
- `docs/project-status/DECISIONS.md`
- `docs/project-status/KNOWN_ISSUES.md`

## PASO 3

Actualizar las fuentes existentes sin crear duplicados.

IMPORTANTE:

Si el repositorio ya usa:

`docs/phases/PHASE-16-paypal-sandbox.md`

y:

`docs/phases/PHASE-17-billing-saas.md`

mantener exactamente esos nombres.

No crear otra FASE 17 paralela.

## PASO 4

Integrar en la documentación las decisiones definitivas:

- PayPal como provider, no como segundo Billing.
- Billing SaaS separado del ERP de cada tenant.
- Transferencias bancarias.
- Comprobantes.
- Verificación manual.
- OCR como extensión futura.
- Pagos a una o varias facturas.
- Anticipo separado de saldo a favor.
- Sobrepagos.
- Notas de crédito.
- Refunds.
- Renovaciones.
- Upgrade/downgrade.
- Prorrateo.
- Multi-moneda.
- Cuentas bancarias de la plataforma.
- Venta manual por Super Admin.
- Creación manual de tenants.
- Suspensión/reactivación.
- Auditoría.
- Reportes.
- Idempotencia y concurrencia.

## PASO 5

Corregir cualquier documentación residual que:

- mezcle CxC del tenant con Billing SaaS;
- describa `CustomerCreditLedger` como fuente de verdad vigente si contradice la decisión actual;
- diga que funcionalidades ya decididas son "no especificadas";
- cree una segunda fuente de Billing;
- indique que PayPal se conectará directamente a `apps.sales.Payment`.

## PASO 6

Verificación:

- `python manage.py check`
- comprobar que `makemigrations --check --dry-run` no detecte cambios;
- ejecutar la suite completa si el tiempo/entorno lo permite;
- revisar `git diff`.

El diff funcional debe quedar vacío.

## REPORTE

Informar:

- archivos modificados;
- contradicciones encontradas;
- decisiones aplicadas;
- confirmación de que no hubo cambios funcionales;
- checks/tests;
- commit.

## REGLA DE PARADA

DETENTE.

No iniciar FASE 16.
No iniciar FASE 17.
No integrar WACRM.
