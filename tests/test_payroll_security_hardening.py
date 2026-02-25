from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from company.models import Company
from payroll.models import EmployeeProfile, Payroll, PayrollEntry, PayrollRun, PayrollRunEntry


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
