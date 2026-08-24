from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Registro mínimo en Django Admin, solo como herramienta interna de
    staff (nunca la UI principal del producto, ver CLAUDE.md)."""
