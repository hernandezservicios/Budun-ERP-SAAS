from django import forms
from django.contrib.auth import get_user_model

from apps.tenants.models import Membership

from .services import SOURCE_CHOICES

User = get_user_model()


class AuditSearchForm(forms.Form):
    source = forms.ChoiceField(label="Origen", choices=[("", "Todos")] + SOURCE_CHOICES, required=False)
    domain = forms.CharField(label="Dominio", required=False, max_length=30)
    action = forms.CharField(label="Acción", required=False, max_length=30)
    user = forms.ModelChoiceField(label="Usuario", queryset=User.objects.none(), required=False)
    date_from = forms.DateField(label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label="Hasta", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    ip_address = forms.CharField(label="Dirección IP", required=False, max_length=45)
    q = forms.CharField(label="Buscar", required=False, max_length=255)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["user"].queryset = User.objects.filter(
                memberships__tenant=tenant, memberships__is_active=True,
            ).distinct().order_by("email")
