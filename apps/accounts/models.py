from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserManager(BaseUserManager):
    """Manager personalizado porque el login es por email, no por
    username (ver `User.USERNAME_FIELD`). Basado en el patrón oficial de
    Django para modelos de usuario sin username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("El correo electrónico es obligatorio.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("El superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("El superusuario debe tener is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom User Model del proyecto (introducido en FASE 3).

    FASE 4 decide la mecánica concreta de login: por correo electrónico
    (convención habitual en un SaaS), no por username. Se verificó que no
    existía ningún usuario real en la base antes de este cambio (0 filas),
    por lo que no hay ninguna migración de datos que hacer.
    """

    username = None
    email = models.EmailField("correo electrónico", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email
