from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from company.models import Company
from payroll.models import EmployeeProfile


User = get_user_model()


class EmployeeCRUDFeatureTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="CRUD Co")
        self.user = User.objects.create_user(
            email="employee-crud@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.first_name = "Ada"
        self.employee.last_name = "Worker"
        self.employee.save()

    def _grant(self, codename):
        permission = Permission.objects.get(
            content_type__app_label="payroll",
            codename=codename,
        )
        self.user.user_permissions.add(permission)

    def test_read_and_search_employee_list(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("payroll:employee_list"), {"q": "Ada"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada")

    def test_update_employee_profile_model_contract(self):
        self.employee.job_title = "Payroll Analyst"
        self.employee.save(update_fields=["job_title"])

        self.assertEqual(
            EmployeeProfile.objects.get(pk=self.employee.pk).job_title,
            "Payroll Analyst",
        )

    def test_profile_and_update_views_render_for_authorized_employee(self):
        self._grant("change_employeeprofile")
        self.client.force_login(self.user)

        profile_response = self.client.get(
            reverse("payroll:profile", args=[self.user.pk])
        )
        update_response = self.client.get(
            reverse("payroll:update_employee", args=[self.employee.pk])
        )

        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(update_response.status_code, 200)
        self.assertContains(profile_response, "Ada")

    def test_delete_employee_route_exists(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("payroll:delete_employee", args=[self.employee.pk]))

        self.assertIn(response.status_code, {200, 302, 403})
