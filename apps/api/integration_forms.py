from django import forms

from .models import Integration
from .scopes import CATALOG_SCOPE_CHOICES


class IntegrationCreateForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=100)
    provider = forms.ChoiceField(label="Provider", choices=Integration.Provider.choices, initial=Integration.Provider.BUDUN)
    scopes = forms.MultipleChoiceField(
        label="Scopes", choices=CATALOG_SCOPE_CHOICES, widget=forms.CheckboxSelectMultiple, required=True,
    )


class IntegrationScopesForm(forms.Form):
    scopes = forms.MultipleChoiceField(
        label="Scopes", choices=CATALOG_SCOPE_CHOICES, widget=forms.CheckboxSelectMultiple, required=True,
    )
