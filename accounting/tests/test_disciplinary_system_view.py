from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class DisciplinarySystemViewTests(TestCase):
    def setUp(self):
        self.url = reverse("payroll:disciplinary_system")
        self.case_list_url = reverse("payroll:discipline_case_list")

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_forbidden_for_non_accounting_user(self):
        user = User.objects.create_user(
            username="regular_user",
            email="regular@example.com",
            password="testpass123",
        )
        self.client.force_login(user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_renders_for_hr_permission_user(self):
        user = User.objects.create_user(
            username="hr_user",
            email="hr@example.com",
            password="testpass123",
        )
        view_employee_perm = Permission.objects.get(codename="view_employeeprofile")
        user.user_permissions.add(view_employee_perm)
        self.client.force_login(user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System Overview")

        case_list_response = self.client.get(self.case_list_url)
        self.assertEqual(case_list_response.status_code, 200)
        self.assertContains(case_list_response, "Disciplinary Cases")

    def test_renders_for_accountant_user(self):
        user = User.objects.create_user(
            username="accountant_user",
            email="accountant@example.com",
            password="testpass123",
        )
        accountant_group, _ = Group.objects.get_or_create(name="Accountant")
        user.groups.add(accountant_group)
        self.client.force_login(user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System Overview")
        self.assertContains(response, "Sanction Matrix (Table)")
        self.assertContains(response, "Implementation Checklist")
