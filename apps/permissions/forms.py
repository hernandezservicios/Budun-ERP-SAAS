from django import forms

from .catalog import PERMISSION_CATALOG


class RolePermissionsForm(forms.Form):
    """Un `BooleanField` por permiso del catálogo — se instancia con
    los valores EFECTIVOS actuales de un rol (default de fábrica +
    personalización del tenant) como `initial`."""

    def __init__(self, *args, **kwargs):
        efectivos = kwargs.pop("efectivos", set())
        super().__init__(*args, **kwargs)
        for code, label, _domain in PERMISSION_CATALOG:
            self.fields[code] = forms.BooleanField(
                label=label, required=False, initial=code in efectivos,
            )


class UserOverrideForm(forms.Form):
    permission_code = forms.ChoiceField(label="Permiso", choices=[(c, l) for c, l, _d in PERMISSION_CATALOG])
    decision = forms.ChoiceField(label="Decisión", choices=[("grant", "Conceder"), ("deny", "Denegar"), ("clear", "Quitar override (usar el rol)")])
    reason = forms.CharField(label="Motivo", required=False, max_length=255)
