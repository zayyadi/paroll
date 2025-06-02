from django.apps import AppConfig

class CustomAdminConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'custom_admin'

    def ready(self):
        # Import models here to avoid AppRegistryNotReady errors
        from payroll.models.employee_profile import EmployeeProfile
        from payroll.models.payroll import Payroll, PayVar
        # ^ Assuming 'Payroll' is the correct class name from payroll.models.payroll

        from .admin_config import register_model

        register_model(EmployeeProfile)
        register_model(Payroll)
        register_model(PayVar)
        # Ensure other apps that might register models are loaded, or handle imports carefully
        # For now, this explicit registration is fine for Phase 1 models.
