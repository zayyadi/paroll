from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from company.models import Company, CompanyMembership
from payroll.models import Department, EmployeeProfile, IOU, LeaveRequest


User = get_user_model()


class APIV1TenantTests(APITestCase):
    @staticmethod
    def grant_model_perms(user, model, codenames):
        content_type = ContentType.objects.get_for_model(model)
        perms = Permission.objects.filter(content_type=content_type, codename__in=codenames)
        user.user_permissions.add(*perms)

    def setUp(self):
        self.company_a = Company.objects.create(name="Acme A")
        self.company_b = Company.objects.create(name="Acme B")

        self.user_a = User.objects.create_user(
            email="a@test.com",
            password="password123",
            first_name="A",
            last_name="User",
            company=self.company_a,
            active_company=self.company_a,
        )
        self.user_b = User.objects.create_user(
            email="b@test.com",
            password="password123",
            first_name="B",
            last_name="User",
            company=self.company_b,
            active_company=self.company_b,
        )
        self.limited_user = User.objects.create_user(
            email="limited@test.com",
            password="password123",
            first_name="Limited",
            last_name="User",
            company=self.company_a,
            active_company=self.company_a,
        )

        CompanyMembership.objects.get_or_create(
            user=self.user_a,
            company=self.company_a,
            defaults={
                "role": CompanyMembership.ROLE_OWNER,
                "is_default": True,
            },
        )
        CompanyMembership.objects.get_or_create(
            user=self.user_b,
            company=self.company_b,
            defaults={
                "role": CompanyMembership.ROLE_OWNER,
                "is_default": True,
            },
        )

        CompanyMembership.objects.get_or_create(
            user=self.limited_user,
            company=self.company_a,
            defaults={
                "role": CompanyMembership.ROLE_MEMBER,
                "is_default": False,
            },
        )

        self.grant_model_perms(
            self.user_a,
            Department,
            ["view_department", "add_department", "change_department", "delete_department"],
        )
        self.grant_model_perms(
            self.user_a,
            EmployeeProfile,
            ["view_employeeprofile", "add_employeeprofile", "change_employeeprofile"],
        )
        self.grant_model_perms(
            self.user_a,
            LeaveRequest,
            ["view_leaverequest", "change_leaverequest"],
        )
        self.grant_model_perms(
            self.user_a,
            IOU,
            ["view_iou", "change_iou"],
        )

        self.dept_a = Department.objects.create(name="HR", company=self.company_a)
        self.dept_b = Department.objects.create(name="Finance", company=self.company_b)

        self.employee_a = EmployeeProfile.objects.get(user=self.user_a)
        self.employee_a.company = self.company_a
        self.employee_a.first_name = "Alice"
        self.employee_a.last_name = "A"
        self.employee_a.department = self.dept_a
        self.employee_a.save()

        self.employee_b = EmployeeProfile.objects.get(user=self.user_b)
        self.employee_b.company = self.company_b
        self.employee_b.first_name = "Bob"
        self.employee_b.last_name = "B"
        self.employee_b.department = self.dept_b
        self.employee_b.save()

        self.leave_b = LeaveRequest.objects.create(
            employee=self.employee_b,
            leave_type="ANNUAL",
            start_date="2026-02-10",
            end_date="2026-02-11",
            reason="Tenant boundary test",
        )
        self.leave_a = LeaveRequest.objects.create(
            employee=self.employee_a,
            leave_type="ANNUAL",
            start_date="2026-02-10",
            end_date="2026-02-11",
            reason="Permission boundary test",
        )
        self.iou_b = IOU.objects.create(
            employee_id=self.employee_b,
            amount=1000,
            tenor=1,
            reason="Tenant boundary test",
        )

    def test_jwt_token_obtain(self):
        if not getattr(settings, "SIMPLE_JWT_ENABLED", False):
            self.skipTest("simplejwt is not installed in this environment")
        url = reverse("api:v1:token-obtain-pair")
        response = self.client.post(
            url,
            {"email": "a@test.com", "password": "password123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_employee_list_is_tenant_scoped(self):
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:employee-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [row["first_name"] for row in response.data["results"]]
        self.assertIn("Alice", names)
        self.assertNotIn("Bob", names)

    def test_department_create_attaches_active_company(self):
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:department-list")
        response = self.client.post(url, {"name": "Engineering"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["company"], self.company_a.id)

    def test_department_create_requires_authentication(self):
        url = reverse("api:v1:department-list")
        response = self.client.post(url, {"name": "NoAuth"}, format="json")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_switch_company_endpoint(self):
        CompanyMembership.objects.create(
            user=self.user_a,
            company=self.company_b,
            role=CompanyMembership.ROLE_ADMIN,
            is_default=False,
        )
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:switch-company")
        response = self.client.post(
            url,
            {"company_id": self.company_b.id},
            format="json",
        )
        if getattr(settings, "MULTI_COMPANY_MEMBERSHIP_ENABLED", False):
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        else:
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.user_a.refresh_from_db()
        expected_company_id = (
            self.company_b.id
            if getattr(settings, "MULTI_COMPANY_MEMBERSHIP_ENABLED", False)
            else self.company_a.id
        )
        self.assertEqual(self.user_a.active_company_id, expected_company_id)

    def test_cross_tenant_leave_approve_not_accessible(self):
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:leave-request-approve", args=[self.leave_b.id])
        response = self.client.post(url, {}, format="json")
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

    def test_cross_tenant_iou_approve_not_accessible(self):
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:iou-approve", args=[self.iou_b.id])
        response = self.client.post(url, {}, format="json")
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

    def test_action_denied_without_model_permission(self):
        self.client.force_authenticate(self.limited_user)
        url = reverse("api:v1:leave-request-approve", args=[self.leave_a.id])
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
