"""Records from one company cannot be read or attached from another (IDOR)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import Permission
from django.test import RequestFactory, override_settings
from django.urls import reverse

from accounting.models import Account, Journal
from accounting.utils import get_or_create_fiscal_year, get_or_create_period
from payroll.forms import AllowanceForm, DeductionForm
from tests.test_tenant_isolation import TenantIsolationBase


@override_settings(SECURE_SSL_REDIRECT=False)
class CrossCompanyAccessTests(TenantIsolationBase):
    def _journal(self, company):
        fiscal_year = get_or_create_fiscal_year(2026, company=company)
        period = get_or_create_period(fiscal_year, 1, company=company)
        return Journal.objects.create(
            company=company,
            date=date(2026, 1, 15),
            period=period,
            description="Other company journal",
            status=Journal.JournalStatus.DRAFT,
        )

    def test_journal_detail_hides_other_company_journal(self):
        journal_b = self._journal(self.company_b)
        self.client.force_login(self.admin_a)

        for name in ("accounting:journal_detail", "accounting:journal_reversal_history"):
            response = self.client.get(reverse(name, args=[journal_b.pk]))
            self.assertEqual(response.status_code, 404, name)

    def test_allowance_form_rejects_other_company_employee(self):
        form = AllowanceForm(company=self.company_a)

        employees = form.fields["employee"].queryset
        self.assertIn(self.emp_a, employees)
        self.assertNotIn(self.emp_b, employees)

    def test_deduction_form_rejects_other_company_employee(self):
        form = DeductionForm(
            data={"employee": self.emp_b.pk, "amount": "100", "deduction_type": "MISC"},
            company=self.company_a,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("employee", form.errors)

    def test_leave_allowance_slip_needs_same_company_hr(self):
        from payroll.views.payroll_leave import _can_view_leave_allowance_slip

        hr_a = self._make_user("hr-a@example.com", "Hr", "A", self.company_a)
        hr_a.user_permissions.add(
            Permission.objects.get(content_type__app_label="payroll", codename="view_allowance")
        )
        hr_a = type(hr_a).objects.get(pk=hr_a.pk)

        self.assertTrue(_can_view_leave_allowance_slip(hr_a, SimpleNamespace(employee=self.emp_a)))
        self.assertFalse(_can_view_leave_allowance_slip(hr_a, SimpleNamespace(employee=self.emp_b)))

    def test_journal_entry_api_rejects_other_company_journal(self):
        from api.v1.serializers import JournalEntrySerializer

        journal_b = self._journal(self.company_b)
        account_a = Account.objects.create(
            company=self.company_a, name="Cash A", account_number="9100", type="ASSET"
        )
        request = RequestFactory().post("/")
        request.user = self.admin_a

        serializer = JournalEntrySerializer(
            data={"journal": journal_b.pk, "account": account_a.pk, "entry_type": "DEBIT", "amount": "10"},
            context={"request": request},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("journal", serializer.errors)
