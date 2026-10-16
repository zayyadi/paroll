import importlib
from django.apps import AppConfig


class ApprovalsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "approvals"

    def ready(self):
        for module in (
            "payroll.approval_actions",
            "accounting.approval_actions",
            "inventory.approval_actions",
        ):
            try:
                importlib.import_module(module)
            except ModuleNotFoundError as exc:
                if exc.name != module:
                    raise
        from .guards import install_history_guards
        install_history_guards()
