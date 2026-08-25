from decimal import Decimal

from django import forms

from apps.tenants.models import Membership


class ResolveApprovalForm(forms.Form):
    decision = forms.ChoiceField(label="Decisión", choices=[("approve", "Aprobar"), ("reject", "Rechazar")])
    approved_value = forms.DecimalField(
        label="Valor aprobado (si difiere del solicitado)", max_digits=12, decimal_places=2, required=False
    )
    decision_reason = forms.CharField(label="Motivo de la decisión", max_length=255, required=False)


class RolePolicyForm(forms.Form):
    role = forms.ChoiceField(label="Rol", choices=Membership.Role.choices)
    max_discount_percent = forms.DecimalField(
        label="Descuento máximo (%)", max_digits=5, decimal_places=2, min_value=Decimal("0"), initial=Decimal("0")
    )
    max_discount_amount = forms.DecimalField(
        label="Descuento máximo (monto)", max_digits=12, decimal_places=2, min_value=Decimal("0"), initial=Decimal("0")
    )
    max_credit_overage = forms.DecimalField(
        label="Exceso de crédito autorizable", max_digits=12, decimal_places=2, min_value=Decimal("0"), initial=Decimal("0")
    )
    # `required=False` deliberado: agregado en FASE 12 sobre un formulario
    # que ya existía en FASE 11 — una petición que no los incluya (p. ej.
    # una integración anterior) no debe romperse, simplemente no cambia
    # esos dos límites (ver `clean` más abajo, que normaliza el vacío a 0).
    max_purchase_order_amount = forms.DecimalField(
        label="Orden de compra autorizable sin aprobación (monto)", max_digits=12, decimal_places=2,
        min_value=Decimal("0"), initial=Decimal("0"), required=False,
        help_text="FASE 12 (Compras): una orden de compra con total mayor a este límite requiere autorización.",
    )
    max_over_receiving_percent = forms.DecimalField(
        label="Sobre-recepción autorizable sin aprobación (%)", max_digits=5, decimal_places=2,
        min_value=Decimal("0"), initial=Decimal("0"), required=False,
        help_text="FASE 12 (Compras): porcentaje por encima de lo pendiente que puede recibirse sin autorización.",
    )

    def clean_max_purchase_order_amount(self):
        return self.cleaned_data.get("max_purchase_order_amount") or Decimal("0")

    def clean_max_over_receiving_percent(self):
        return self.cleaned_data.get("max_over_receiving_percent") or Decimal("0")
    can_approve = forms.BooleanField(label="Puede resolver solicitudes de autorización", required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)
