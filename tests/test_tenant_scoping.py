"""
Fail-closed tenant scoping layer.

``CompanyOwnedModel`` (company.tenancy) gives tenant-owned models a
``CompanyScopedManager`` that scopes every read to the current company
context (contextvars). When ``TENANT_SCOPING_ENFORCED`` is enabled, querying
without any context raises ``CompanyContextRequired`` instead of returning
unscoped results. ``get_user_company`` establishes the context, and
``ActiveCompanyMiddleware`` sets it per request and clears it afterwards.

Adopted models: RemittanceRecord, PublicHoliday.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from company.models import Company
from company.tenancy import (
    CompanyContextRequired,
    company_context,
    get_current_company,
    set_current_company,
    tenant_cache_key,
)
from company.utils import get_user_company
from payroll.models import PublicHoliday, RemittanceRecord

User = get_user_model()


class CompanyScopingBase(TestCase):
    """Two companies, each with a superuser admin and one row per adopted model."""

    def setUp(self):
        self.company_a = Company.objects.create(name="Tenant A")
        self.company_b = Company.objects.create(name="Tenant B")
        self.admin_a = self._make_user("admin-a@example.com", self.company_a)
        self.admin_b = self._make_user("admin-b@example.com", self.company_b)

        with company_context(self.company_a):
            RemittanceRecord.objects.create(
                company=self.company_a, obligation="paye", period=date(2026, 6, 1)
            )
            PublicHoliday.objects.create(
                company=self.company_a, name="A Day", date=date(2026, 6, 8)
            )
        with company_context(self.company_b):
            RemittanceRecord.objects.create(
                company=self.company_b, obligation="paye", period=date(2026, 6, 1)
            )
            PublicHoliday.objects.create(
                company=self.company_b, name="B Day", date=date(2026, 6, 8)
            )

    def tearDown(self):
        # ContextVars persist on the thread across tests; never leak one.
        set_current_company(None)

    def _make_user(self, email, company):
        return User.objects.create_user(
            email=email,
            password="testpass123",
            first_name="Tenant",
            last_name="Admin",
            company=company,
            active_company=company,
            is_staff=True,
            is_superuser=True,
        )


class CompanyContextTests(CompanyScopingBase):
    """The contextvars primitives themselves."""

    def test_company_context_sets_and_restores(self):
        self.assertIsNone(get_current_company())
        with company_context(self.company_a):
            self.assertEqual(get_current_company(), self.company_a)
        self.assertIsNone(get_current_company())

    def test_nested_company_contexts_stack(self):
        with company_context(self.company_a):
            with company_context(self.company_b):
                self.assertEqual(get_current_company(), self.company_b)
            self.assertEqual(get_current_company(), self.company_a)
        self.assertIsNone(get_current_company())

    def test_get_user_company_establishes_context(self):
        company = get_user_company(self.admin_a)
        self.assertEqual(company, self.company_a)
        self.assertEqual(get_current_company(), self.company_a)

    def test_get_user_company_switches_context(self):
        get_user_company(self.admin_a)
        self.assertEqual(get_current_company(), self.company_a)
        get_user_company(self.admin_b)
        self.assertEqual(get_current_company(), self.company_b)


@override_settings(TENANT_SCOPING_ENFORCED=True)
class EnforcedScopingTests(CompanyScopingBase):
    """Fail-closed behaviour: raise without context, scope with it."""

    def test_no_context_raises_for_adopted_models(self):
        with self.assertRaises(CompanyContextRequired):
            RemittanceRecord.objects.count()
        with self.assertRaises(CompanyContextRequired):
            PublicHoliday.objects.all()

    def test_queries_scope_to_current_company(self):
        with company_context(self.company_a):
            self.assertEqual(RemittanceRecord.objects.count(), 1)
            self.assertEqual(
                RemittanceRecord.objects.get().company, self.company_a
            )
            self.assertEqual(PublicHoliday.objects.count(), 1)
            self.assertEqual(PublicHoliday.objects.get().name, "A Day")

        with company_context(self.company_b):
            self.assertEqual(RemittanceRecord.objects.count(), 1)
            self.assertEqual(RemittanceRecord.objects.get().company, self.company_b)
            self.assertEqual(PublicHoliday.objects.get().name, "B Day")

    def test_explicit_other_company_filter_under_context_is_empty(self):
        with company_context(self.company_a):
            self.assertFalse(
                RemittanceRecord.objects.filter(company=self.company_b).exists()
            )
            self.assertFalse(
                PublicHoliday.objects.filter(company=self.company_b).exists()
            )

    def test_all_objects_escape_hatch_is_unscoped(self):
        with company_context(self.company_a):
            self.assertEqual(RemittanceRecord.objects.count(), 1)
            self.assertEqual(RemittanceRecord.all_objects.count(), 2)
            self.assertEqual(PublicHoliday.all_objects.count(), 2)

    def test_get_user_company_provides_context_for_queries(self):
        # A task/command can resolve the user's company and query immediately.
        get_user_company(self.admin_b)
        self.assertEqual(RemittanceRecord.objects.get().company, self.company_b)


class UnenforcedScopingTests(CompanyScopingBase):
    """Legacy behaviour with the flag off: unscoped when no context is set."""

    def test_no_context_returns_unscoped_queryset(self):
        self.assertEqual(RemittanceRecord.objects.count(), 2)
        self.assertEqual(PublicHoliday.objects.count(), 2)


class TenantCacheKeyTests(TestCase):
    """OWASP multi-tenant caching: every tenant-data cache key carries the
    company dimension, so one tenant's cached value can never be served to
    another."""

    def setUp(self):
        self.company_a = Company.objects.create(name="Cache A")
        self.company_b = Company.objects.create(name="Cache B")
        self.emp_a = self._make_employee(self.company_a, "cache-a@example.com")
        self.emp_b = self._make_employee(self.company_b, "cache-b@example.com")

    def tearDown(self):
        set_current_company(None)

    def _make_employee(self, company, email):
        user = User.objects.create_user(
            email=email,
            password="testpass123",
            first_name="Same",
            last_name="Name",
            company=company,
            active_company=company,
        )
        employee = user.employee_user
        employee.company = company
        employee.save(update_fields=["company"])
        return employee

    def test_model_part_uses_pk_and_company(self):
        # No context needed: the model part carries its own company.
        key_a = tenant_cache_key("notifications", self.emp_a, "unread_count")
        self.assertEqual(
            key_a,
            f"tenant:{self.company_a.pk}:notifications:{self.emp_a.pk}:unread_count",
        )

    def test_same_named_employees_in_different_companies_get_distinct_keys(self):
        self.assertEqual(self.emp_a.first_name, self.emp_b.first_name)  # both "Same"
        key_a = tenant_cache_key("notifications", self.emp_a, "unread_count")
        key_b = tenant_cache_key("notifications", self.emp_b, "unread_count")
        self.assertNotEqual(key_a, key_b)

    def test_context_supplies_company_for_string_parts(self):
        with company_context(self.company_a):
            self.assertEqual(
                tenant_cache_key("hr-dashboard", "42"),
                f"tenant:{self.company_a.pk}:hr-dashboard:42",
            )

    def test_unprefixed_without_any_company(self):
        self.assertEqual(tenant_cache_key("login_lockout", "x"), "login_lockout:x")


class MiddlewareContextTests(CompanyScopingBase):
    """The request lifecycle wires context through ActiveCompanyMiddleware."""

    def test_request_sets_context_for_view_and_clears_after(self):
        self.client.login(email="admin-a@example.com", password="testpass123")
        with override_settings(TENANT_SCOPING_ENFORCED=True):
            # The calendar view queries RemittanceRecord/PublicHoliday (adopted
            # models); without middleware context this would raise a 500.
            response = self.client.get(reverse("payroll:compliance_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Statutory Compliance")
        # Context must not leak past the request.
        self.assertIsNone(get_current_company())

    def test_context_does_not_leak_between_users_requests(self):
        self.client.login(email="admin-a@example.com", password="testpass123")
        self.client.get(reverse("payroll:compliance_calendar"))
        self.assertIsNone(get_current_company())

        self.client.login(email="admin-b@example.com", password="testpass123")
        self.client.get(reverse("payroll:compliance_calendar"))
        self.assertIsNone(get_current_company())
