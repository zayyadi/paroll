from django.test import SimpleTestCase

import core.settings as project_settings


class ProductionHardeningSettingsTests(SimpleTestCase):
    def test_default_settings_are_safe_when_debug_is_false(self):
        self.assertFalse(project_settings.DEBUG)
        self.assertTrue(project_settings.SECURE_SSL_REDIRECT)
        self.assertGreaterEqual(project_settings.SECURE_HSTS_SECONDS, 31536000)
        self.assertEqual(project_settings.X_FRAME_OPTIONS, "DENY")
        self.assertTrue(project_settings.ACCOUNTING_SUPERUSER_ONLY_UNTIL_TENANT_SCOPED)

    def test_celery_queues_are_declared_separately_from_task_routes(self):
        self.assertIn("notifications_normal", project_settings.CELERY_TASK_QUEUES)
        self.assertIn("notifications_low", project_settings.CELERY_TASK_QUEUES)
        self.assertEqual(
            project_settings.CELERY_TASK_ROUTES[
                "payroll.send_payslips_for_payroll_run"
            ]["queue"],
            "notifications_normal",
        )
