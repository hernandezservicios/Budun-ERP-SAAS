from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom User Model del proyecto (FASE 3).

    Se introduce en FASE 3 (y no más tarde) porque Django exige definir
    AUTH_USER_MODEL antes de la primera migración: cambiarlo después de que
    existan tablas basadas en el modelo por defecto requiere una migración
    manual compleja. Los flujos de autenticación reales (registro, login,
    logout, recuperación de contraseña, perfil) son alcance de FASE 4 —
    Authentication; aquí solo se establece el modelo base para que ese
    trabajo futuro no requiera romper la base de datos.

    Se añade `email` único porque el inicio de sesión de un SaaS
    normalmente se hace por correo; el resto de campos de `AbstractUser`
    (username, first_name, last_name, password, is_active, etc.) se
    conservan tal cual para no anticipar decisiones de FASE 4.
    """

    email = models.EmailField("correo electrónico", unique=True)

    def __str__(self):
        return self.email or self.username
