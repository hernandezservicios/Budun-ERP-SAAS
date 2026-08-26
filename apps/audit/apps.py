from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    verbose_name = "Auditoría"

    def ready(self):
        # Conecta las señales de autenticación de Django (login/logout/
        # login fallido) al log transversal — import diferido aquí (no a
        # nivel de módulo en signals.py) porque `ready()` es el punto
        # oficial de Django para efectos secundarios de registro de señales.
        from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed

        from . import signals

        user_logged_in.connect(signals.on_user_logged_in, dispatch_uid="apps.audit.on_user_logged_in")
        user_logged_out.connect(signals.on_user_logged_out, dispatch_uid="apps.audit.on_user_logged_out")
        user_login_failed.connect(signals.on_user_login_failed, dispatch_uid="apps.audit.on_user_login_failed")
