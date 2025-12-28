from django.apps import AppConfig


class PayrollConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payroll"

    def ready(self):
        """
        Initialize payroll application and register all signal handlers.

        This method is called when Django starts and ensures all signal
        handlers are properly registered for the notification system.
        """
        # Import and register core signals
        import payroll.signals
        import payroll.audit_signal

        # Import and register notification signals
        import payroll.notification_signals

        # Import and register notification event handlers
        import payroll.events.notification_events

        # Import notification tasks (ensures Celery tasks are registered)
        import payroll.tasks.notification_tasks

        # Import notification services (ensures services are initialized)
        import payroll.services.notification_service
