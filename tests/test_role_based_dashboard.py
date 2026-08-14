"""
Tests for role-based dashboard routing (root URL "/") and the role flags
exposed by the user_roles context processor.
"""

from datetime import date as date_cls
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from company.models import Company
from payroll.models import (
    CompanyPayrollSetting,
    EmployeeProfile,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
    RemittanceRecord,
)
from payroll.permissions import setup_groups_and_permissions
from payroll.services import compliance


User = get_user_model()


class RoleBasedDashboardRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()

        cls.company = Company.objects.create(name="Role Dashboard Co")

        # Super admin
        cls.superuser = User.objects.create_superuser(
            email="super@example.com", password="password123"
        )

        # HR user (HR group)
        cls.hr_user = User.objects.create_user(
            email="hr@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        cls.hr_user.groups.add(Group.objects.get(name="HR"))

        # Finance user (Finance group)
        cls.finance_user = User.objects.create_user(
            email="finance@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        cls.finance_user.groups.add(Group.objects.get_or_create(name="Finance")[0])

        # Regular employee with an EmployeeProfile (auto-created via signal)
        cls.employee_user = User.objects.create_user(
            email="employee@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        # emp_objects (used by the index view) only returns active profiles
        cls.employee_user.employee_user.status = "active"
        cls.employee_user.employee_user.save()

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_superuser_renders_operations_dashboard(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("root"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "index.html")

    def test_hr_user_redirects_to_hr_dashboard(self):
        self.client.force_login(self.hr_user)
        response = self.client.get(reverse("root"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("payroll:hr_dashboard"))

    def test_finance_user_redirects_to_accounting_dashboard(self):
        self.client.force_login(self.finance_user)
        response = self.client.get(reverse("root"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounting:dashboard"))

    def test_employee_renders_personal_dashboard(self):
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("root"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "employee_home.html")

    def test_employee_group_user_renders_personal_dashboard(self):
        # The Employee group must NOT be treated as HR: its users keep the
        # personal dashboard instead of being misrouted to hr_dashboard.
        group_user = User.objects.create_user(
            email="group-employee@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        group_user.groups.add(Group.objects.get(name="Employee"))
        # emp_objects (used by the index view) only returns active profiles
        group_user.employee_user.status = "active"
        group_user.employee_user.save()
        self.client.force_login(group_user)
        response = self.client.get(reverse("root"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "employee_home.html")


class UserRolesContextProcessorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Context Co")

    def _make_user(self, email, **kwargs):
        return User.objects.create_user(
            email=email,
            password="password123",
            company=self.company,
            active_company=self.company,
            **kwargs,
        )

    def _role_flags_for(self, user):
        """Call the user_roles context processor directly for a request."""
        from django.test import RequestFactory

        from core.context_processors import user_roles

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        return user_roles(request)

    def test_context_processor_flags_superuser(self):
        user = self._make_user("super@example.com", is_superuser=True)
        flags = self._role_flags_for(user)
        self.assertTrue(flags["is_super_admin_user"])
        self.assertFalse(flags["is_employee_user"])

    def test_context_processor_flags_hr_user(self):
        user = self._make_user("hr@example.com")
        user.groups.add(Group.objects.get(name="HR"))
        flags = self._role_flags_for(user)
        self.assertTrue(flags["is_hr_user"])
        self.assertFalse(flags["is_finance_user"])

    def test_context_processor_flags_finance_user(self):
        user = self._make_user("finance@example.com")
        user.groups.add(Group.objects.get_or_create(name="Finance")[0])
        flags = self._role_flags_for(user)
        self.assertTrue(flags["is_finance_user"])
        self.assertFalse(flags["is_hr_user"])

    def test_context_processor_flags_payroll_processor(self):
        user = self._make_user("payroll@example.com")
        user.groups.add(Group.objects.get_or_create(name="Payroll Processor")[0])
        flags = self._role_flags_for(user)
        self.assertTrue(flags["is_payroll_processor_user"])
        self.assertFalse(flags["is_employee_user"])
        self.assertFalse(flags["is_finance_user"])
        self.assertFalse(flags["is_hr_user"])

    def test_context_processor_flags_employee_user(self):
        user = self._make_user("employee@example.com")
        flags = self._role_flags_for(user)
        self.assertTrue(flags["is_employee_user"])
        self.assertFalse(flags["is_finance_user"])
        self.assertFalse(flags["is_hr_user"])

    def test_anonymous_has_no_role_flags(self):
        from django.contrib.auth.models import AnonymousUser

        from django.test import RequestFactory

        from core.context_processors import user_roles

        factory = RequestFactory()
        request = factory.get("/")
        request.user = AnonymousUser()
        flags = user_roles(request)
        self.assertFalse(flags["is_super_admin_user"])
        self.assertFalse(flags["is_finance_user"])
        self.assertFalse(flags["is_hr_user"])
        self.assertFalse(flags["is_employee_user"])


class RoleBasedSidebarTests(TestCase):
    """Verify the sidebar nav partial renders role-specific menu items."""

    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Sidebar Co")

        cls.superuser = User.objects.create_superuser(
            email="super@example.com", password="password123"
        )
        cls.hr_user = User.objects.create_user(
            email="hr@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        cls.hr_user.groups.add(Group.objects.get(name="HR"))
        cls.finance_user = User.objects.create_user(
            email="finance@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        cls.finance_user.groups.add(Group.objects.get_or_create(name="Finance")[0])
        cls.employee_user = User.objects.create_user(
            email="employee@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )

    def test_finance_sidebar_contains_accounting_and_excludes_employees(self):
        self.client.force_login(self.finance_user)
        response = self.client.get(reverse("accounting:dashboard"))
        content = response.content.decode()
        # Finance sees accounting menu items
        self.assertIn("Accounting Dashboard", content)
        self.assertIn("Chart of Accounts", content)
        # Finance does not see the HR/People menu
        self.assertNotIn("Employees", content)

    def test_hr_sidebar_contains_people_and_excludes_accounting(self):
        self.client.force_login(self.hr_user)
        response = self.client.get(reverse("payroll:hr_dashboard"))
        content = response.content.decode()
        self.assertIn("Employees", content)
        # HR nav has no Accounting section
        self.assertNotIn("Accounting Dashboard", content)

    def test_superuser_sidebar_contains_admin_and_operations_sections(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("root"))
        content = response.content.decode()
        self.assertIn("Employees", content)
        self.assertIn("Accounting Dashboard", content)
        self.assertIn("Inventory Dashboard", content)
        self.assertIn("Payroll Settings", content)

    def test_employee_sidebar_excludes_admin_sections(self):
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("root"))
        content = response.content.decode()
        self.assertIn("My Payslips", content)
        self.assertNotIn("Employees", content)
        self.assertNotIn("Accounting Dashboard", content)


class PayrollProcessorRoleTests(TestCase):
    """Payroll Processor users get their own nav + payroll dashboard landing."""

    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        from accounting.permissions import setup_accounting_groups_and_permissions

        setup_accounting_groups_and_permissions()
        cls.company = Company.objects.create(name="Payroll Processor Co")
        cls.pp_user = User.objects.create_user(
            email="payroll-ops@example.com",
            password="password123",
            company=cls.company,
            active_company=cls.company,
        )
        cls.pp_user.groups.add(Group.objects.get(name="Payroll Processor"))

    def setUp(self):
        self.client.force_login(self.pp_user)

    def test_payroll_processor_redirects_to_payroll_dashboard(self):
        response = self.client.get(reverse("root"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("payroll:dashboard"))

    def test_payroll_processor_sidebar_shows_payroll_ops(self):
        response = self.client.get(reverse("payroll:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Payroll operations menu
        self.assertIn("Pay Periods", content)
        self.assertIn("Payroll Summary", content)
        self.assertIn("Salary Config", content)
        self.assertIn("Bank Payments", content)
        self.assertIn("PAYE Report", content)
        # Not the generic employee nav
        self.assertNotIn("My Payslips", content)
        self.assertNotIn("My Leave", content)
        # Not the HR/People or Finance/Accounting navs
        # ("Employees" is avoided because the dashboard body itself says
        # "Employee records" / "View all employees")
        self.assertNotIn("Transfers", content)
        self.assertNotIn("Hiring", content)
        self.assertNotIn("Accounting Dashboard", content)

    def test_payroll_processor_can_open_pay_periods(self):
        response = self.client.get(reverse("payroll:pay_period_list"))
        self.assertEqual(response.status_code, 200)

    def test_payroll_processor_group_has_payroll_ops_permissions(self):
        codenames = set(
            Group.objects.get(name="Payroll Processor").permissions.values_list(
                "codename", flat=True
            )
        )
        for perm in (
            "view_payrollrun",
            "add_payrollrun",
            "change_payrollrun",
            "view_payroll",
            "add_payroll",
            "change_payroll",
            "add_allowance",
            "add_deduction",
        ):
            self.assertIn(perm, codenames)
        # Payroll/PayrollRun delete stays withheld (audit-sensitive)
        self.assertNotIn("delete_payrollrun", codenames)


class DashboardMetricsTests(TestCase):
    """Dashboards must show real computed aggregates, not hardcoded figures."""

    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Metrics Co")
        cls.superuser = User.objects.create_superuser(
            email="metrics-super@example.com", password="password123"
        )
        cls.superuser.company = cls.company
        cls.superuser.save(update_fields=["company"])

        # Employee with full payroll setup (salary config + bank details)
        cls.ready_user = User.objects.create_user(
            email="ready@example.com",
            password="password123",
            first_name="Ready",
            last_name="Profile",
            company=cls.company,
            active_company=cls.company,
        )
        cls.ready_profile = cls.ready_user.employee_user
        cls.ready_profile.company = cls.company
        cls.ready_profile.bank_account_number = "0123456789"
        from payroll.models import Payroll

        cls.ready_profile.employee_pay = Payroll.objects.create(
            company=cls.company, basic_salary=1200000
        )
        cls.ready_profile.save()

        # Employee with no payroll setup
        cls.incomplete_user = User.objects.create_user(
            email="incomplete@example.com",
            password="password123",
            first_name="Incomplete",
            last_name="Profile",
            company=cls.company,
            active_company=cls.company,
        )
        cls.incomplete_profile = cls.incomplete_user.employee_user
        cls.incomplete_profile.company = cls.company
        cls.incomplete_profile.save()

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_payroll_dashboard_shows_real_readiness(self):
        # payroll:dashboard renders the payroll admin dashboard (pay/dashboard_new.html)
        response = self.client.get(reverse("payroll:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("50%", content)  # 1 of 2 ready
        self.assertIn("Ready", content)
        self.assertIn("Incomplete", content)
        # No fabricated numbers from the original redesign
        self.assertNotIn("92%", content)
        self.assertNotIn("Verified", content)

    def test_hr_dashboard_shows_real_aggregates(self):
        response = self.client.get(reverse("payroll:hr_dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("New hires by month", content)
        self.assertIn("50%", content)  # profile completion 1 of 2
        self.assertNotIn("84.2", content)

    def test_admin_dashboard_shows_real_aggregates(self):
        # dashboard_admin_new.html is rendered by employee_dashboard.dashboard,
        # which is shadowed in the URL namespace by payroll_dashboard.dashboard,
        # so call it directly (as payroll.test_views does).
        from django.test import RequestFactory

        from payroll.views.employee_dashboard import dashboard as admin_dashboard_view

        request = RequestFactory().get("/dashboard/")
        request.user = self.superuser
        response = admin_dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Active users", content)
        self.assertIn("Pending approvals", content)
        self.assertNotIn("99.9%", content)
        self.assertNotIn("Critical vulnerabilities", content)

    def test_user_dashboard_shows_real_aggregates(self):
        # dashboard_user_new.html is likewise only reachable via the direct view.
        from django.test import RequestFactory

        from payroll.views.employee_dashboard import dashboard as user_dashboard_view

        request = RequestFactory().get("/dashboard/")
        request.user = self.incomplete_user
        response = user_dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Real leave balance + entitlement, no fabricated defaults
        self.assertIn("Annual leave balance", content)
        self.assertNotIn("25 days", content)
        self.assertNotIn("+12.4%", content)

    def test_discipline_case_board_shows_real_aggregates(self):
        from accounting.models import DisciplinaryCase

        DisciplinaryCase.objects.create(
            company=self.company,
            allegation_summary="Documented case",
            finding=DisciplinaryCase.Finding.SUBSTANTIATED,
            status=DisciplinaryCase.Status.DECIDED,
        )
        response = self.client.get(reverse("payroll:discipline_case_list"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # 1 active, 0 resolved, 1/1 documented -> 100%
        self.assertIn("Documentation rate", content)
        self.assertIn("100%", content)
        self.assertNotIn("98%", content)
        self.assertNotIn("AA", content)


class PayrollDashboardCostSummaryTests(TestCase):
    """The payroll dashboard surfaces real per-company cost-of-employment totals."""

    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Cost Summary Co")
        cls.user = get_user_model().objects.create_user(
            email="cost-summary@example.com",
            password="password123",
            first_name="Cost",
            last_name="Summary",
            company=cls.company,
            active_company=cls.company,
            is_staff=True,
            is_superuser=True,
        )
        cls.employee = EmployeeProfile.objects.get(user=cls.user)
        cls.employee.company = cls.company
        cls.employee.status = "active"
        cls.employee.save(update_fields=["company", "status"])
        cls.employee.employee_pay = Payroll.objects.create(
            company=cls.company,
            basic_salary=Decimal("120000.00"),
        )
        cls.employee.save(update_fields=["employee_pay"])

    def setUp(self):
        self.client.force_login(self.user)

    def test_dashboard_shows_employer_cost_vs_net_pay(self):
        # One employee at 120,000 basic: monthly gross 72,000, net pay 55,640
        # (PAYE 6,560 + employee pension 9,600 + water 200), employer cost
        # 85,200 (gross + employer pension 12,000 + NSITF 1,200).
        response = self.client.get(reverse("payroll:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Cost of employment", content)
        self.assertIn("₦85,200", content)
        self.assertIn("₦55,640", content)
        self.assertIn("Pension (ER)", content)
        self.assertIn("₦12,000", content)
        self.assertIn("NSITF", content)
        self.assertIn("₦1,200", content)

    def test_dashboard_includes_itf_split_when_applicable(self):
        CompanyPayrollSetting.objects.create(
            company=self.company, itf_applicable=True
        )
        # Re-save the pay config so the stored ITF levy (1% of annual gross)
        # is recomputed now that the flag is on.
        self.employee.employee_pay.save()
        response = self.client.get(reverse("payroll:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # ITF = 1% of 864,000 annual gross / 12 = 720 per month; employer
        # cost rises from 85,200 to 85,920.
        self.assertIn("₦720", content)
        self.assertIn("₦85,920", content)


class PayrollDashboardComplianceSummaryTests(TestCase):
    """The payroll dashboard surfaces statutory exposure from the compliance calendar."""

    @classmethod
    def setUpTestData(cls):
        setup_groups_and_permissions()
        cls.company = Company.objects.create(name="Compliance Dashboard Co")
        cls.user = get_user_model().objects.create_user(
            email="compliance-dash@example.com",
            password="password123",
            first_name="Compliance",
            last_name="Dash",
            company=cls.company,
            active_company=cls.company,
            is_staff=True,
            is_superuser=True,
        )
        cls.employee = EmployeeProfile.objects.get(user=cls.user)
        cls.employee.company = cls.company
        cls.employee.status = "active"
        cls.employee.save(update_fields=["company", "status"])
        cls.employee.employee_pay = Payroll.objects.create(
            company=cls.company,
            basic_salary=Decimal("120000.00"),
        )
        cls.employee.save(update_fields=["employee_pay"])

    def setUp(self):
        self.client.force_login(self.user)

    def _add_run(self, paydays):
        payroll_entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee, status="active"
        )
        run = PayrollRun.objects.create(
            company=self.company, name="Run", paydays=paydays, is_active=True
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=payroll_entry)
        return run

    def test_dashboard_surfaces_overdue_count_and_exposure(self):
        self._add_run(date_cls(2020, 6, 1))
        response = self.client.get(reverse("payroll:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Statutory compliance", content)
        # PAYE + pension + NSITF + the annual return are overdue. The exposed
        # amount is PAYE 6,560 + pension 21,600 + NSITF 1,200 = 29,360.
        self.assertIn("4 remittances · ₦29,360 exposed", content)
        self.assertIn("All remaining items are overdue.", content)

    def test_dashboard_shows_next_due(self):
        today = date_cls.today()
        period = date_cls(today.year, today.month, 1)
        self._add_run(period)
        # Mark pension and NSITF remitted so the next open deadline is
        # deterministic: PAYE, due the 10th of the following month.
        RemittanceRecord.objects.create(
            company=self.company,
            obligation="pension",
            period=period,
            remitted_on=today,
        )
        RemittanceRecord.objects.create(
            company=self.company,
            obligation="nsitf",
            period=period,
            remitted_on=today,
        )
        response = self.client.get(reverse("payroll:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Next due", content)
        self.assertIn("PAYE", content)
        expected = compliance.paye_due_date(period)
        self.assertIn(expected.strftime("%d %b %Y"), content)

    def test_dashboard_shows_all_clear_with_no_exposure(self):
        response = self.client.get(reverse("payroll:dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Nothing overdue.", content)
        self.assertIn("No open obligations.", content)
