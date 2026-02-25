from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.core.management import call_command
from io import StringIO

from company.middleware import ActiveCompanyMiddleware
from company.models import Company, CompanyMembership
from company.tenancy import scoped_queryset
from payroll.models import Department


User = get_user_model()


class TenancyHelpersTestCase(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Acme Ltd")
        self.company_b = Company.objects.create(name="Beta Ltd")
        self.user = User.objects.create_user(
            email="owner@acme.test",
            password="pass1234",
            first_name="Acme",
            last_name="Owner",
            company=self.company_a,
            active_company=self.company_a,
        )
        CompanyMembership.objects.create(
            user=self.user,
            company=self.company_a,
            role=CompanyMembership.ROLE_OWNER,
            is_default=True,
        )

    def test_scoped_queryset_filters_to_current_company(self):
        Department.objects.create(name="HR", company=self.company_a)
        Department.objects.create(name="Finance", company=self.company_b)
        queryset = scoped_queryset(Department.objects, self.user)
        self.assertEqual(list(queryset.values_list("name", flat=True)), ["HR"])


class ActiveCompanyMiddlewareTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ActiveCompanyMiddleware(lambda request: HttpResponse("ok"))

    @override_settings(
        MULTI_COMPANY_MEMBERSHIP_ENABLED=True,
        SAAS_ENFORCE_ACTIVE_COMPANY=True,
    )
    def test_blocks_authenticated_user_without_company(self):
        user = User.objects.create_user(
            email="nocompany@test.com",
            password="pass1234",
            first_name="No",
            last_name="Company",
        )
        request = self.factory.get("/payroll/dashboard")
        request.user = user
        response = self.middleware(request)
        self.assertEqual(response.status_code, 403)

    @override_settings(
        MULTI_COMPANY_MEMBERSHIP_ENABLED=True,
        SAAS_ENFORCE_ACTIVE_COMPANY=True,
    )
    def test_allows_authenticated_user_with_company(self):
        company = Company.objects.create(name="Delta Inc")
        user = User.objects.create_user(
            email="user@delta.test",
            password="pass1234",
            first_name="Delta",
            last_name="User",
            company=company,
            active_company=company,
        )
        CompanyMembership.objects.create(
            user=user,
            company=company,
            role=CompanyMembership.ROLE_MEMBER,
            is_default=True,
        )
        request = self.factory.get("/payroll/dashboard")
        request.user = user
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)


class CreateTenantCommandTestCase(TestCase):
    def test_create_tenant_command_creates_workspace_and_owner_membership(self):
        out = StringIO()
        call_command(
            "create_tenant",
            "Gamma Corp",
            "owner@gamma.test",
            "--owner-password",
            "StrongPass123!",
            stdout=out,
        )

        company = Company.objects.get(name="Gamma Corp")
        user = User.objects.get(email="owner@gamma.test")
        membership = CompanyMembership.objects.get(user=user, company=company)

        self.assertEqual(membership.role, CompanyMembership.ROLE_OWNER)
        self.assertEqual(user.active_company_id, company.id)
