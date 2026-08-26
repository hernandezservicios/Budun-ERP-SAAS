from django import forms

from .scopes import SCOPE_CHOICES


class ApiKeyScopesForm(forms.Form):
    scopes = forms.MultipleChoiceField(
        label="Scopes", choices=SCOPE_CHOICES, widget=forms.CheckboxSelectMultiple, required=True,
    )
