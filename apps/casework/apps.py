from django.apps import AppConfig


class CaseworkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.casework"

    def ready(self) -> None:
        from . import signals  # noqa: F401
