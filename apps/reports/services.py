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

from apps.customers.models import Customer, Supplier
from apps.expenses.models import Expense
from apps.hr.models import Employee, Leave
from apps.inventory import services as inv_services
from apps.payroll.models import Payroll, PayrollPeriod
from apps.pos.models import CashMovement, CashSession
from apps.purchases import services as purchases_services
from apps.purchases.models import PurchaseOrder
from apps.sales import services as sales_services
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
    return {
        "summary": {
            "count": agregado["cantidad"] or 0, "total": agregado["total"] or Decimal("0"),
            "subtotal": agregado["subtotal"] or Decimal("0"), "discounts": agregado["descuentos"] or Decimal("0"),
            "taxes": agregado["impuestos"] or Decimal("0"), "by_status": por_estado, "by_payment_status": por_metodo_pago,
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
    return {
        "summary": {
            "total_products": len(productos), "low_stock_count": len(bajo_stock), "out_of_stock_count": len(agotados),
        },
        "rows": productos,
        "low_stock": bajo_stock,
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
    return {
        "summary": {"total_pending": total_pendiente, "aging": aging, "total_advances": total_anticipos},
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
    for fila in por_cliente:
        cliente = clientes_por_id.get(fila["customer_id"])
        fila["display_name"] = cliente.display_name if cliente else "—"
        fila["pending"] = sales_services.get_sale_balance_due_bulk(
            sales_services.get_customer_pending_sales(cliente)
        ) if cliente else {}
        fila["pending_total"] = sum(fila["pending"].values(), Decimal("0"))
    return {"summary": {"customer_count": len(por_cliente)}, "rows": por_cliente}


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
    return {"summary": {"supplier_count": len(por_proveedor)}, "rows": por_proveedor}


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
