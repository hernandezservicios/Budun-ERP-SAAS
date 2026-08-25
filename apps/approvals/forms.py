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
    can_approve = forms.BooleanField(label="Puede resolver solicitudes de autorización", required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)
