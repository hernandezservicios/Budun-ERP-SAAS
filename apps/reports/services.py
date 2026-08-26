"""
Plataforma de Reportes (FASE 14, ver `docs/reports.md`). Regla
permanente: un reporte NUNCA recalcula una cifra financiera de forma
independiente cuando esa información ya vive en otro módulo — cada
función de aquí agrega/filtra sobre los servicios/consultas YA
existentes de `apps.sales`/`apps.purchases`/`apps.inventory`/
`apps.pos`/`apps.expenses`/`apps.hr`/`apps.payroll`/`apps.customers`,
nunca reimplementa esa lógica.

Cada reporte devuelve `{"summary": {...}, "rows": [...]}` — el
"resumen" y el "análisis" de la especificación de esta fase se
combinan en `summary` (agregaciones/agrupaciones), y "detalle" es
`rows` (drill-down real: cada fila enlaza al documento origen ya
existente — Sale/PurchaseOrder/Expense/Employee/etc. — nunca una
copia de esos datos)."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.accounting import services as acct_services
from apps.customers.models import Customer, Supplier
from apps.expenses.models import Expense
from apps.hr.models import Employee, Leave
from apps.inventory import services as inv_services
from apps.payroll.models import Payroll, PayrollPeriod
from apps.pos.models import CashMovement, CashSession
from apps.purchases import services as purchases_services
from apps.purchases.models import PurchaseOrder, SupplierInvoice, SupplierPayment, SupplierReturn
from apps.sales import services as sales_services
from apps.sales.models import CreditNote, Payment, Refund, Return, SaleItem
from apps.sales.models import Sale


# ------------------------------------------------------------------
# Ventas
# ------------------------------------------------------------------


def get_sales_report(tenant, *, date_from=None, date_to=None, customer=None, status=None):
    queryset = Sale.all_objects.filter(tenant=tenant).select_related("customer", "salesperson")
    if date_from:
        queryset = queryset.filter(issue_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(issue_date__lte=date_to)
    if customer:
        queryset = queryset.filter(customer=customer)
    if status:
        queryset = queryset.filter(status=status)

    agregado = queryset.aggregate(
        total=Sum("total"), subtotal=Sum("subtotal"), descuentos=Sum("discount_total"), impuestos=Sum("tax_total"),
        cantidad=Count("id"),
    )
    por_estado = list(queryset.values("status").annotate(cantidad=Count("id"), total=Sum("total")).order_by("status"))
    por_metodo_pago = list(
        queryset.filter(status=Sale.Status.CONFIRMED)
        .values("payment_status").annotate(cantidad=Count("id"), total=Sum("total")).order_by("payment_status")
    )

    # Margen bruto (ampliación de cierre de FASE 14): SUM(subtotal-descuento)
    # menos SUM(SaleItem.cost_amount) — una sola consulta agregada, nunca
    # un recálculo por venta (evita N+1).
    costo_total = SaleItem.all_objects.filter(tenant=tenant, sale__in=queryset).aggregate(t=Sum("cost_amount"))["t"] or Decimal("0")
    margen = (agregado["subtotal"] or Decimal("0")) - (agregado["descuentos"] or Decimal("0")) - costo_total

    # Conteos de devoluciones/refunds/notas de crédito del mismo rango de
    # fechas (resumen aproximado por período — no filtrado por
    # cliente/estado como la venta, para no requerir un join costoso).
    devoluciones_qs = Return.all_objects.filter(tenant=tenant)
    refunds_qs = Refund.all_objects.filter(tenant=tenant)
    notas_credito_qs = CreditNote.all_objects.filter(tenant=tenant)
    if date_from:
        devoluciones_qs = devoluciones_qs.filter(created_at__date__gte=date_from)
        refunds_qs = refunds_qs.filter(created_at__date__gte=date_from)
        notas_credito_qs = notas_credito_qs.filter(issue_date__gte=date_from)
    if date_to:
        devoluciones_qs = devoluciones_qs.filter(created_at__date__lte=date_to)
        refunds_qs = refunds_qs.filter(created_at__date__lte=date_to)
        notas_credito_qs = notas_credito_qs.filter(issue_date__lte=date_to)

    return {
        "summary": {
            "count": agregado["cantidad"] or 0, "total": agregado["total"] or Decimal("0"),
            "subtotal": agregado["subtotal"] or Decimal("0"), "discounts": agregado["descuentos"] or Decimal("0"),
            "taxes": agregado["impuestos"] or Decimal("0"), "by_status": por_estado, "by_payment_status": por_metodo_pago,
            "cost_total": costo_total, "margin": margen,
            "returns_count": devoluciones_qs.count(), "refunds_count": refunds_qs.count(),
            "credit_notes_count": notas_credito_qs.count(),
        },
        "rows": queryset.order_by("-issue_date", "-id")[:500],
    }


# ------------------------------------------------------------------
# Inventario (reutiliza literalmente apps.inventory.services)
# ------------------------------------------------------------------


def get_inventory_report(tenant):
    productos = inv_services.list_products_with_stock(tenant)
    bajo_stock = list(inv_services.get_low_stock_products(tenant))
    agotados = [p for p in productos if getattr(p, "current_stock", None) == 0]
    # Valorización (ampliación de cierre de FASE 14): reutiliza
    # literalmente apps.inventory.services.get_inventory_valuation,
    # nunca un cálculo paralelo. La reconciliación contra el saldo real
    # de la cuenta Inventario del Libro Mayor es `None` si el tenant
    # todavía no configuró ese mapeo (nada que reconciliar todavía).
    valorizacion = inv_services.get_inventory_valuation(tenant)
    reconciliacion = acct_services.get_inventory_gl_reconciliation(tenant)
    return {
        "summary": {
            "total_products": len(productos), "low_stock_count": len(bajo_stock), "out_of_stock_count": len(agotados),
            "inventory_value": valorizacion["total_value"], "gl_reconciliation": reconciliacion,
        },
        "rows": productos,
        "low_stock": bajo_stock,
        "valuation_rows": valorizacion["rows"],
    }


# ------------------------------------------------------------------
# Caja (reutiliza literalmente apps.pos — nunca duplica el efectivo)
# ------------------------------------------------------------------


def get_cash_report(tenant, *, date_from=None, date_to=None, register=None):
    queryset = CashSession.all_objects.filter(tenant=tenant).select_related("cash_register", "user")
    if date_from:
        queryset = queryset.filter(opened_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(opened_at__date__lte=date_to)
    if register:
        queryset = queryset.filter(cash_register=register)

    filas = []
    total_diferencia = Decimal("0")
    for sesion in queryset.order_by("-opened_at"):
        filas.append({
            "session": sesion, "expected": sesion.expected_cash, "counted": sesion.counted_cash,
            "difference": sesion.difference if sesion.difference is not None else None,
        })
        if sesion.difference is not None:
            total_diferencia += sesion.difference

    movimientos_por_tipo = list(
        CashMovement.all_objects.filter(tenant=tenant, cash_session__in=queryset)
        .values("movement_type").annotate(cantidad=Count("id"), total=Sum("amount")).order_by("movement_type")
    )
    return {
        "summary": {"count": queryset.count(), "total_difference": total_diferencia, "by_movement_type": movimientos_por_tipo},
        "rows": filas,
    }


# ------------------------------------------------------------------
# Cuentas por Cobrar (reutiliza literalmente apps.sales — nunca
# recalcula el saldo de una factura ni el saldo a favor de un cliente)
# ------------------------------------------------------------------


def get_accounts_receivable_report(tenant):
    clientes = list(Customer.all_objects.filter(tenant=tenant, is_active=True))
    hoy = timezone.localdate()
    filas = []
    total_pendiente = Decimal("0")
    aging = {"d0_30": Decimal("0"), "d31_60": Decimal("0"), "d61_90": Decimal("0"), "d90_plus": Decimal("0")}

    for cliente in clientes:
        pendientes = sales_services.get_customer_pending_sales(cliente)
        if not pendientes:
            continue
        saldos = sales_services.get_sale_balance_due_bulk(pendientes)
        for venta in pendientes:
            saldo = saldos.get(venta.pk, Decimal("0"))
            if saldo <= 0:
                continue
            vencimiento_estimado = venta.issue_date + timedelta(days=cliente.credit_days)
            dias_vencido = (hoy - vencimiento_estimado).days
            bucket = "d0_30" if dias_vencido <= 30 else "d31_60" if dias_vencido <= 60 else "d61_90" if dias_vencido <= 90 else "d90_plus"
            aging[bucket] += saldo
            total_pendiente += saldo
            filas.append({
                "customer": cliente, "sale": venta, "balance_due": saldo,
                "estimated_due_date": vencimiento_estimado, "days_overdue": max(dias_vencido, 0),
            })

    saldo_a_favor_total = sum((sales_services.get_customer_credit_balance(c) for c in clientes), Decimal("0"))
    return {
        "summary": {"total_pending": total_pendiente, "aging": aging, "total_credit_balance": saldo_a_favor_total},
        "rows": sorted(filas, key=lambda f: f["days_overdue"], reverse=True),
    }


# ------------------------------------------------------------------
# Cuentas por Pagar (reutiliza literalmente apps.purchases)
# ------------------------------------------------------------------


def get_accounts_payable_report(tenant):
    proveedores = list(Supplier.all_objects.filter(tenant=tenant, is_active=True))
    hoy = timezone.localdate()
    filas = []
    total_pendiente = Decimal("0")
    aging = {"d0_30": Decimal("0"), "d31_60": Decimal("0"), "d61_90": Decimal("0"), "d90_plus": Decimal("0")}

    for proveedor in proveedores:
        facturas = purchases_services.get_supplier_pending_invoices(proveedor)
        if not facturas:
            continue
        saldos = purchases_services.get_invoice_balance_due_bulk(facturas)
        for factura in facturas:
            saldo = saldos.get(factura.pk, Decimal("0"))
            if saldo <= 0:
                continue
            fecha_venc = factura.due_date or factura.issue_date
            dias_vencido = (hoy - fecha_venc).days
            bucket = "d0_30" if dias_vencido <= 30 else "d31_60" if dias_vencido <= 60 else "d61_90" if dias_vencido <= 90 else "d90_plus"
            aging[bucket] += saldo
            total_pendiente += saldo
            filas.append({"supplier": proveedor, "invoice": factura, "balance_due": saldo, "days_overdue": max(dias_vencido, 0)})

    total_anticipos = sum((purchases_services.get_supplier_advance_balance(p) for p in proveedores), Decimal("0"))
    devoluciones_count = SupplierReturn.all_objects.filter(tenant=tenant).count()
    return {
        "summary": {
            "total_pending": total_pendiente, "aging": aging, "total_advances": total_anticipos,
            "returns_count": devoluciones_count,
        },
        "rows": sorted(filas, key=lambda f: f["days_overdue"], reverse=True),
    }


# ------------------------------------------------------------------
# Compras
# ------------------------------------------------------------------


def get_purchases_report(tenant, *, date_from=None, date_to=None, supplier=None):
    queryset = PurchaseOrder.all_objects.filter(tenant=tenant).select_related("supplier")
    if date_from:
        queryset = queryset.filter(issue_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(issue_date__lte=date_to)
    if supplier:
        queryset = queryset.filter(supplier=supplier)
    agregado = queryset.aggregate(total=Sum("total"), cantidad=Count("id"))
    por_estado = list(queryset.values("status").annotate(cantidad=Count("id"), total=Sum("total")).order_by("status"))
    return {
        "summary": {"count": agregado["cantidad"] or 0, "total": agregado["total"] or Decimal("0"), "by_status": por_estado},
        "rows": queryset.order_by("-issue_date", "-id")[:500],
    }


# ------------------------------------------------------------------
# Gastos
# ------------------------------------------------------------------


def get_expenses_report(tenant, *, date_from=None, date_to=None, category=None):
    queryset = Expense.all_objects.filter(tenant=tenant).select_related("category", "supplier")
    if date_from:
        queryset = queryset.filter(expense_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(expense_date__lte=date_to)
    if category:
        queryset = queryset.filter(category=category)
    agregado = queryset.aggregate(total=Sum("total"), cantidad=Count("id"))
    por_categoria = list(queryset.values("category__name").annotate(cantidad=Count("id"), total=Sum("total")).order_by("-total"))
    por_estado = list(queryset.values("status").annotate(cantidad=Count("id"), total=Sum("total")).order_by("status"))
    return {
        "summary": {
            "count": agregado["cantidad"] or 0, "total": agregado["total"] or Decimal("0"),
            "by_category": por_categoria, "by_status": por_estado,
        },
        "rows": queryset.order_by("-expense_date", "-id")[:500],
    }


# ------------------------------------------------------------------
# RRHH — nunca expone salario/datos bancarios (ver
# apps.hr.services.can_view_sensitive_employee_data)
# ------------------------------------------------------------------


def get_hr_report(tenant):
    empleados = Employee.all_objects.filter(tenant=tenant)
    por_estado = list(empleados.values("status").annotate(cantidad=Count("id")).order_by("status"))
    por_departamento = list(
        empleados.values("department__name").annotate(cantidad=Count("id")).order_by("-cantidad")
    )
    ausencias_pendientes = Leave.all_objects.filter(tenant=tenant, status=Leave.Status.REQUESTED).select_related("employee", "leave_type")
    return {
        "summary": {
            "total_employees": empleados.count(), "by_status": por_estado, "by_department": por_departamento,
            "pending_leaves": ausencias_pendientes.count(),
        },
        "rows": empleados.select_related("department", "position").order_by("first_name", "last_name"),
        "pending_leaves": ausencias_pendientes,
    }


# ------------------------------------------------------------------
# Nómina — bruto/deducciones/neto/costo por período (nunca expone
# salario individual salvo que quien lo vea pueda ver datos sensibles)
# ------------------------------------------------------------------


def get_payroll_report(tenant, *, period=None):
    queryset = Payroll.all_objects.filter(tenant=tenant).select_related("period", "employee")
    if period:
        queryset = queryset.filter(period=period)
    agregado = queryset.aggregate(bruto=Sum("gross_total"), deducciones=Sum("deductions_total"), neto=Sum("net_total"))
    return {
        "summary": {
            "count": queryset.count(), "gross_total": agregado["bruto"] or Decimal("0"),
            "deductions_total": agregado["deducciones"] or Decimal("0"), "net_total": agregado["neto"] or Decimal("0"),
        },
        "rows": queryset.order_by("-period__start_date", "employee_name_snapshot"),
    }


def list_payroll_periods_for_filter(tenant):
    return PayrollPeriod.all_objects.filter(tenant=tenant).order_by("-start_date")


# ------------------------------------------------------------------
# Clientes y Proveedores (top N, facturado/pagado/pendiente)
# ------------------------------------------------------------------


def get_customers_report(tenant, *, date_from=None, date_to=None):
    queryset = Sale.all_objects.filter(tenant=tenant, status=Sale.Status.CONFIRMED, customer__isnull=False)
    if date_from:
        queryset = queryset.filter(issue_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(issue_date__lte=date_to)
    por_cliente = list(
        queryset.values("customer_id", "customer__first_name", "customer__last_name", "customer__company_name")
        .annotate(facturado=Sum("total"), cantidad=Count("id")).order_by("-facturado")
    )
    ids = [fila["customer_id"] for fila in por_cliente]
    clientes_por_id = {c.pk: c for c in Customer.all_objects.filter(pk__in=ids)}
    facturado_total = Decimal("0")
    pendiente_total = Decimal("0")
    saldo_a_favor_total = Decimal("0")
    for fila in por_cliente:
        cliente = clientes_por_id.get(fila["customer_id"])
        fila["display_name"] = cliente.display_name if cliente else "—"
        fila["pending"] = sales_services.get_sale_balance_due_bulk(
            sales_services.get_customer_pending_sales(cliente)
        ) if cliente else {}
        fila["pending_total"] = sum(fila["pending"].values(), Decimal("0"))
        fila["average_ticket"] = (fila["facturado"] / fila["cantidad"]).quantize(Decimal("0.01")) if fila["cantidad"] else Decimal("0")
        facturado_total += fila["facturado"] or Decimal("0")
        pendiente_total += fila["pending_total"]
        if cliente:
            saldo_a_favor_total += sales_services.get_customer_credit_balance(cliente)
    return {
        "summary": {
            "customer_count": len(por_cliente), "total_invoiced": facturado_total,
            "total_pending": pendiente_total, "total_paid": facturado_total - pendiente_total,
            "total_credit_balance": saldo_a_favor_total,
        },
        "rows": por_cliente,
    }


def get_customer_statement(tenant, customer):
    """Estado de cuenta de UN cliente (ampliación de cierre de FASE 14 —
    ver docs/reports.md y docs/accounts-receivable.md sección 6):
    resumen (saldo pendiente actual, facturado histórico, saldo a
    favor) + detalle cronológico de ventas/pagos/notas de crédito —
    nunca una copia de esos datos, siempre agregando sobre
    `apps.sales`/`apps.sales.services` ya existentes."""
    ventas = list(Sale.all_objects.filter(tenant=tenant, customer=customer, status=Sale.Status.CONFIRMED).order_by("issue_date"))
    saldos = sales_services.get_sale_balance_due_bulk(ventas)
    pagos = list(Payment.all_objects.filter(tenant=tenant, customer=customer, status=Payment.Status.CONFIRMED).order_by("created_at"))
    notas_credito = list(CreditNote.all_objects.filter(tenant=tenant, customer=customer).order_by("issue_date"))

    movimientos = []
    for venta in ventas:
        movimientos.append({"date": venta.issue_date, "type": "Venta", "document": venta, "amount": venta.total})
    for pago in pagos:
        movimientos.append({"date": pago.created_at.date(), "type": "Pago", "document": pago, "amount": -pago.amount})
    for nota in notas_credito:
        movimientos.append({"date": nota.issue_date, "type": "Nota de crédito", "document": nota, "amount": -nota.amount})
    movimientos.sort(key=lambda m: m["date"])

    facturado_total = sum((v.total for v in ventas), Decimal("0"))
    pendiente_total = sum(saldos.values(), Decimal("0"))
    return {
        "summary": {
            "customer": customer, "total_invoiced": facturado_total, "total_pending": pendiente_total,
            "total_credit_balance": sales_services.get_customer_credit_balance(customer),
            "sale_count": len(ventas),
        },
        "rows": movimientos,
        "pending_sales": [{"sale": v, "balance_due": saldos.get(v.pk, Decimal("0"))} for v in ventas if saldos.get(v.pk, Decimal("0")) > 0],
    }


def get_suppliers_report(tenant, *, date_from=None, date_to=None):
    queryset = PurchaseOrder.all_objects.filter(tenant=tenant)
    if date_from:
        queryset = queryset.filter(issue_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(issue_date__lte=date_to)
    por_proveedor = list(
        queryset.values("supplier_id", "supplier__legal_name", "supplier__trade_name")
        .annotate(comprado=Sum("total"), cantidad=Count("id")).order_by("-comprado")
    )
    comprado_total = Decimal("0")
    anticipos_total = Decimal("0")
    proveedores_por_id = {s.pk: s for s in Supplier.all_objects.filter(pk__in=[f["supplier_id"] for f in por_proveedor])}
    for fila in por_proveedor:
        fila["average_purchase"] = (fila["comprado"] / fila["cantidad"]).quantize(Decimal("0.01")) if fila["cantidad"] else Decimal("0")
        comprado_total += fila["comprado"] or Decimal("0")
        proveedor = proveedores_por_id.get(fila["supplier_id"])
        if proveedor:
            anticipos_total += purchases_services.get_supplier_advance_balance(proveedor)
    return {
        "summary": {"supplier_count": len(por_proveedor), "total_purchased": comprado_total, "total_advances": anticipos_total},
        "rows": por_proveedor,
    }


def get_supplier_statement(tenant, supplier):
    """Estado de cuenta de UN proveedor — mismo patrón espejo que
    `get_customer_statement`: resumen (pendiente actual, comprado
    histórico, anticipos) + detalle cronológico de facturas/pagos."""
    facturas = list(SupplierInvoice.all_objects.filter(tenant=tenant, supplier=supplier, status=SupplierInvoice.Status.CONFIRMED).order_by("issue_date"))
    saldos = purchases_services.get_invoice_balance_due_bulk(facturas)
    pagos = list(SupplierPayment.all_objects.filter(tenant=tenant, supplier=supplier, status=SupplierPayment.Status.CONFIRMED).order_by("created_at"))

    movimientos = []
    for factura in facturas:
        movimientos.append({"date": factura.issue_date, "type": "Factura", "document": factura, "amount": factura.total})
    for pago in pagos:
        movimientos.append({"date": pago.created_at.date(), "type": "Pago", "document": pago, "amount": -pago.amount})
    movimientos.sort(key=lambda m: m["date"])

    comprado_total = sum((f.total for f in facturas), Decimal("0"))
    pendiente_total = sum(saldos.values(), Decimal("0"))
    return {
        "summary": {
            "supplier": supplier, "total_purchased": comprado_total, "total_pending": pendiente_total,
            "total_advances": purchases_services.get_supplier_advance_balance(supplier), "invoice_count": len(facturas),
        },
        "rows": movimientos,
        "pending_invoices": [{"invoice": f, "balance_due": saldos.get(f.pk, Decimal("0"))} for f in facturas if saldos.get(f.pk, Decimal("0")) > 0],
    }


# ------------------------------------------------------------------
# Panel gerencial — un resumen ejecutivo, agregando lo de arriba
# (nunca recalcula nada nuevo, solo reúne totales ya obtenidos)
# ------------------------------------------------------------------


def get_executive_summary(tenant, *, date_from=None, date_to=None):
    ventas = get_sales_report(tenant, date_from=date_from, date_to=date_to, status=Sale.Status.CONFIRMED)
    gastos = get_expenses_report(tenant, date_from=date_from, date_to=date_to)
    ar = get_accounts_receivable_report(tenant)
    ap = get_accounts_payable_report(tenant)
    inventario = get_inventory_report(tenant)
    return {
        "sales_total": ventas["summary"]["total"], "expenses_total": gastos["summary"]["total"],
        "ar_pending": ar["summary"]["total_pending"], "ap_pending": ap["summary"]["total_pending"],
        "low_stock_count": inventario["summary"]["low_stock_count"],
        "gross_margin_estimate": ventas["summary"]["total"] - gastos["summary"]["total"],
    }
