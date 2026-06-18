from datetime import date

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.mfa import get_login_lockout_cache_key
from accounting.models import Account
from company.models import Company
from payroll.models import (
    EmployeeProfile,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
    SensitiveDataAccess,
    log_sensitive_employee_data_access,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class PayrollSecurityHardeningTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.company = Company.objects.create(name="Tenant A")

        self.owner = self.User.objects.create_user(
            email="owner@example.com",
            first_name="Owner",
            last_name="User",
            password="StrongPass123!",
            company=self.company,
            active_company=self.company,
        )
        self.other_user = self.User.objects.create_user(
            email="other@example.com",
            first_name="Other",
            last_name="User",
            password="StrongPass123!",
            company=self.company,
            active_company=self.company,
        )

        self.owner_employee = EmployeeProfile.objects.get(user=self.owner)
        self.owner_employee.company = self.company
        self.owner_employee.slug = "owner-user"
        self.owner_employee.email = self.owner.email
        self.owner_employee.first_name = "Owner"
        self.owner_employee.last_name = "User"
        self.owner_employee.save()

        payroll = Payroll.objects.create(company=self.company, basic_salary=100000)
        self.owner_employee.employee_pay = payroll
        self.owner_employee.save(update_fields=["employee_pay"])

        payroll_entry = PayrollEntry.objects.create(
            pays=self.owner_employee,
            company=self.company,
        )
        payroll_run = PayrollRun.objects.create(
            company=self.company,
            name="Jan 2025",
            paydays=date(2025, 1, 1),
            is_active=True,
        )
        self.run_entry = PayrollRunEntry.objects.create(
            payroll_run=payroll_run,
            payroll_entry=payroll_entry,
        )

    def test_payslip_detail_blocks_non_owner_without_permission(self):
        self.client.login(email=self.other_user.email, password="StrongPass123!")
        response = self.client.get(
            reverse("payroll:payslip", kwargs={"id": self.run_entry.id})
        )
        self.assertEqual(response.status_code, 403)

    def test_request_iou_requires_login(self):
        response = self.client.get(reverse("payroll:request_iou"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

    def test_locked_out_user_cannot_login_with_correct_password(self):
        cache.set(get_login_lockout_cache_key(self.owner.email), True, timeout=300)

        response = self.client.post(
            reverse("users:login"),
            {
                "username": self.owner.email,
                "password": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(ALLOW_DEFAULT_COMPANY_FALLBACK=False)
    def test_user_creation_without_company_does_not_create_default_tenant(self):
        fallback_count = Company.objects.filter(name="Default Company").count()

        with self.assertRaises(ValueError):
            self.User.objects.create_user(
                email="missing-company@example.com",
                password="StrongPass123!",
            )

        self.assertEqual(
            Company.objects.filter(name="Default Company").count(),
            fallback_count,
        )

    @override_settings(ALLOW_DEFAULT_COMPANY_FALLBACK=False)
    def test_account_creation_without_company_does_not_create_default_tenant(self):
        fallback_count = Company.objects.filter(name="Default Company").count()

        with self.assertRaises(ValidationError):
            Account.objects.create(
                name="Unscoped Cash",
                account_number="1000",
                type=Account.AccountType.ASSET,
            )

        self.assertEqual(
            Company.objects.filter(name="Default Company").count(),
            fallback_count,
        )

    def test_employee_profile_view_logs_sensitive_data_access(self):
        self.client.login(email=self.owner.email, password="StrongPass123!")

        response = self.client.get(
            reverse("payroll:profile", kwargs={"user_id": self.owner.id})
        )

        self.assertEqual(response.status_code, 200)
        fields = set(
            SensitiveDataAccess.objects.filter(
                employee=self.owner_employee,
                accessed_by=self.owner,
                purpose="employee_profile_view",
            ).values_list("field_name", flat=True)
        )
        self.assertIn("bank_account_number", fields)
        self.assertIn("tin_no", fields)

    def test_sensitive_data_logger_ignores_non_sensitive_fields(self):
        created = log_sensitive_employee_data_access(
            employee=self.owner_employee,
            accessed_by=self.owner,
            fields=("first_name", "last_name"),
            purpose="unit_test",
        )

        self.assertEqual(created, [])
        self.assertFalse(
            SensitiveDataAccess.objects.filter(purpose="unit_test").exists()
        )
