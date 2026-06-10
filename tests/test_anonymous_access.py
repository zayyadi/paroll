from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from company.models import Company


User = get_user_model()


class AnonymousAccessTests(TestCase):
    def test_root_redirects_anonymous_users_to_login(self):
        response = self.client.get(reverse("root"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/users/login", response["Location"])

    def test_root_dashboard_renders_for_hr_user(self):
        company = Company.objects.create(name="Dashboard Co")
        user = User.objects.create_user(
            email="dashboard-hr@example.com",
            password="password123",
            company=company,
            active_company=company,
        )
        permission = Permission.objects.get(
            content_type__app_label="payroll",
            codename="view_employeeprofile",
        )
        user.user_permissions.add(permission)
        self.client.force_login(user)

        response = self.client.get(reverse("root"))

        self.assertEqual(response.status_code, 200)
