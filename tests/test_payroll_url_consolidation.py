from django.test import SimpleTestCase
from django.urls import resolve, reverse

from payroll import views as payroll_view


class PayrollUrlConsolidationTests(SimpleTestCase):
    def test_legacy_pay_period_create_url_uses_enhanced_create_view(self):
        match = resolve(reverse("payroll:payday"))

        self.assertIs(match.func, payroll_view.payday_create_new)
