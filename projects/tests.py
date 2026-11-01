from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from company.models import Company
from payroll.models import Payroll, PayrollEntry, PayrollRun, PayrollRunEntry
from payroll.services.hr_surfaces import save_timesheet
from payroll.services.timesheet_service import get_or_create_timesheet, submit_timesheet
from projects import services
from projects.models import Project, ProjectCostAllocation, Task
from tests.approval_helpers import approve_request

User = get_user_model()


class ProjectFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Projects Co")
        self.other_company = Company.objects.create(name="Elsewhere Co")
        self.user = self._user("worker@projects.test", self.company)
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.employee_pay = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("300000.00")
        )
        self.employee.save(update_fields=["company", "employee_pay"])
        self.alpha = Project.objects.create(company=self.company, code="ALPHA", name="Alpha")
        self.beta = Project.objects.create(company=self.company, code="BETA", name="Beta")

    def _user(self, email, company):
        return User.objects.create_user(
            email=email, password="x", company=company, active_company=company
        )

    def grant(self, user, *codenames):
        user.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="projects", codename__in=codenames)
        )

    def sheet(self, week_start, hours="40"):
        sheet = get_or_create_timesheet(employee=self.employee, week_start=week_start)
        return save_timesheet(actor=self.user, pk=sheet.pk, total_hours=Decimal(hours))

    def approve(self, sheet):
        approve_request(submit_timesheet(timesheet=sheet, actor=self.user))
        sheet.refresh_from_db()
        return sheet


class TimeBookingTests(ProjectFixture):
    def test_employee_books_time_on_a_draft(self):
        sheet = self.sheet(date(2026, 6, 1))
        services.add_time_entry(actor=self.user, timesheet=sheet, project=self.alpha, hours=Decimal("30"))
        self.assertEqual(services.booked_hours(sheet), Decimal("30"))

    def test_bookings_cannot_exceed_the_timesheet_total(self):
        sheet = self.sheet(date(2026, 6, 1))
        services.add_time_entry(actor=self.user, timesheet=sheet, project=self.alpha, hours=Decimal("30"))
        with self.assertRaisesMessage(ValidationError, "cannot exceed"):
            services.add_time_entry(actor=self.user, timesheet=sheet, project=self.beta, hours=Decimal("11"))

    def test_rejects_other_company_closed_project_and_foreign_task(self):
        sheet = self.sheet(date(2026, 6, 1))
        foreign = Project.objects.create(company=self.other_company, code="X", name="X")
        with self.assertRaisesMessage(ValidationError, "your company"):
            services.add_time_entry(actor=self.user, timesheet=sheet, project=foreign, hours=Decimal("1"))
        self.beta.status = Project.Status.COMPLETED
        self.beta.save()
        with self.assertRaisesMessage(ValidationError, "completed"):
            services.add_time_entry(actor=self.user, timesheet=sheet, project=self.beta, hours=Decimal("1"))
        beta_task = Task.objects.create(project=self.beta, title="Beta work")
        with self.assertRaises(ValidationError):
            services.add_time_entry(
                actor=self.user, timesheet=sheet, project=self.alpha, task=beta_task, hours=Decimal("1")
            )

    def test_only_the_owner_books_and_only_while_editable(self):
        sheet = self.sheet(date(2026, 6, 1))
        colleague = self._user("colleague@projects.test", self.company)
        with self.assertRaises(PermissionDenied):
            services.add_time_entry(actor=colleague, timesheet=sheet, project=self.alpha, hours=Decimal("1"))
        entry = services.add_time_entry(actor=self.user, timesheet=sheet, project=self.alpha, hours=Decimal("8"))
        submit_timesheet(timesheet=sheet, actor=self.user)
        with self.assertRaisesMessage(ValidationError, "draft or rejected"):
            services.add_time_entry(actor=self.user, timesheet=sheet, project=self.alpha, hours=Decimal("1"))
        with self.assertRaisesMessage(ValidationError, "draft or rejected"):
            services.remove_time_entry(actor=self.user, entry=entry)

    def test_submit_is_blocked_when_bookings_exceed_a_reduced_total(self):
        sheet = self.sheet(date(2026, 6, 1))
        services.add_time_entry(actor=self.user, timesheet=sheet, project=self.alpha, hours=Decimal("30"))
        sheet = save_timesheet(actor=self.user, pk=sheet.pk, total_hours=Decimal("20"))
        with self.assertRaisesMessage(ValidationError, "exceeds its total hours"):
            submit_timesheet(timesheet=sheet, actor=self.user)


class CostAllocationTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        entry = PayrollEntry.objects.create(company=self.company, pays=self.employee, status="active")
        self.run = PayrollRun.objects.create(
            company=self.company, name="June", paydays=date(2026, 6, 1), is_active=True
        )
        PayrollRunEntry.objects.create(payroll_run=self.run, payroll_entry=entry)
        self.entry = PayrollEntry.objects.get(pk=entry.pk)

    def test_cost_is_split_by_approved_project_hours_in_the_month(self):
        week1 = self.sheet(date(2026, 6, 1))
        services.add_time_entry(actor=self.user, timesheet=week1, project=self.alpha, hours=Decimal("30"))
        services.add_time_entry(actor=self.user, timesheet=week1, project=self.beta, hours=Decimal("10"))
        self.approve(week1)
        self.approve(self.sheet(date(2026, 6, 8)))  # 40 general hours, no projects
        unapproved = self.sheet(date(2026, 6, 15))
        services.add_time_entry(actor=self.user, timesheet=unapproved, project=self.beta, hours=Decimal("40"))
        may = self.sheet(date(2026, 5, 25))
        services.add_time_entry(actor=self.user, timesheet=may, project=self.beta, hours=Decimal("40"))
        self.approve(may)  # week starts in May: belongs to May's run

        rows = {row.project.code: row for row in services.allocate_run_costs(self.run)}

        cost = services.employee_run_cost(self.entry)
        self.assertGreater(cost, 0)
        self.assertEqual(set(rows), {"ALPHA", "BETA"})
        self.assertEqual(rows["ALPHA"].employee_hours, Decimal("80"))
        self.assertEqual(rows["ALPHA"].amount, (cost * 30 / 80).quantize(Decimal("0.01")))
        self.assertEqual(rows["BETA"].hours, Decimal("10"))
        self.assertEqual(rows["BETA"].amount, (cost * 10 / 80).quantize(Decimal("0.01")))
        summary = services.run_cost_summary(self.run)
        self.assertEqual(summary["total_cost"], cost)
        self.assertEqual(summary["unallocated"], cost - rows["ALPHA"].amount - rows["BETA"].amount)

    def test_recalculating_replaces_previous_rows(self):
        week1 = self.sheet(date(2026, 6, 1))
        services.add_time_entry(actor=self.user, timesheet=week1, project=self.alpha, hours=Decimal("40"))
        self.approve(week1)
        services.allocate_run_costs(self.run)
        services.allocate_run_costs(self.run)
        self.assertEqual(ProjectCostAllocation.objects.filter(payroll_run=self.run).count(), 1)
        self.assertEqual(
            ProjectCostAllocation.objects.get().amount, services.employee_run_cost(self.entry)
        )

    def test_no_approved_time_means_no_allocation(self):
        self.sheet(date(2026, 6, 1))
        self.assertEqual(services.allocate_run_costs(self.run), [])

    def test_project_summary_reports_cost_against_budget(self):
        self.alpha.budget = Decimal("1000000.00")
        self.alpha.save()
        week1 = self.sheet(date(2026, 6, 1))
        services.add_time_entry(actor=self.user, timesheet=week1, project=self.alpha, hours=Decimal("40"))
        self.approve(week1)
        services.allocate_run_costs(self.run)
        summary = services.project_summary(self.alpha)
        cost = services.employee_run_cost(self.entry)
        self.assertEqual(summary["approved_hours"], Decimal("40"))
        self.assertEqual(summary["cost"], cost)
        self.assertEqual(summary["budget_remaining"], Decimal("1000000.00") - cost)


class ProjectViewTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.manager = self._user("manager@projects.test", self.company)
        self.grant(
            self.manager,
            "view_project", "add_project", "change_project", "add_task", "change_task",
            "view_projectcostallocation", "add_projectcostallocation",
        )

    def test_list_needs_permission_and_is_company_scoped(self):
        Project.objects.create(company=self.other_company, code="HIDDEN", name="Hidden")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("projects:list")).status_code, 403)
        self.client.force_login(self.manager)
        response = self.client.get(reverse("projects:list"))
        self.assertContains(response, "ALPHA")
        self.assertNotContains(response, "HIDDEN")

    def test_other_company_project_is_not_found(self):
        foreign = Project.objects.create(company=self.other_company, code="X", name="X")
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("projects:detail", args=[foreign.pk])).status_code, 404)

    def test_create_project_rejects_duplicate_code(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("projects:create"), {"code": "GAMMA", "name": "Gamma", "status": "active"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Project.objects.filter(company=self.company, code="GAMMA").exists())
        response = self.client.post(reverse("projects:create"), {"code": "alpha", "name": "Again", "status": "active"})
        self.assertContains(response, "uses this code")

    def test_add_task_and_change_status(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("projects:detail", args=[self.alpha.pk]), {"title": "Design", "status": "todo"})
        task = Task.objects.get(project=self.alpha)
        self.client.post(reverse("projects:task_status", args=[task.pk]), {"status": "done"})
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DONE)

    def test_employee_books_time_through_the_page_but_not_on_others_sheets(self):
        sheet = self.sheet(date(2026, 6, 1))
        self.client.force_login(self.user)
        url = reverse("projects:timesheet_time", args=[sheet.pk])
        self.client.post(url, {"project": self.alpha.pk, "hours": "6"})
        self.assertEqual(services.booked_hours(sheet), Decimal("6"))
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_cost_page_recalculates_only_with_permission(self):
        run = PayrollRun.objects.create(company=self.company, name="June", paydays=date(2026, 6, 1))
        viewer = self._user("viewer@projects.test", self.company)
        self.grant(viewer, "view_projectcostallocation")
        self.client.force_login(viewer)
        url = reverse("projects:costs")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"run": run.pk}).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(url, {"run": run.pk}).status_code, 302)

    def test_pages_render(self):
        task = Task.objects.create(project=self.alpha, title="Build", assignee=self.employee)
        self.alpha.budget = Decimal("500000")
        self.alpha.save()
        self.client.force_login(self.manager)
        for url in (
            reverse("projects:detail", args=[self.alpha.pk]),
            reverse("projects:edit", args=[self.alpha.pk]),
            reverse("projects:create"),
            reverse("projects:task_edit", args=[task.pk]),
            reverse("projects:costs"),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        sheet = self.sheet(date(2026, 6, 1))
        services.add_time_entry(actor=self.user, timesheet=sheet, project=self.alpha, task=task, hours=Decimal("5"))
        self.client.force_login(self.user)
        response = self.client.get(reverse("projects:timesheet_time", args=[sheet.pk]))
        self.assertContains(response, "ALPHA")
        self.assertContains(response, "Book time")
        self.assertContains(self.client.get(reverse("payroll:timesheets")), reverse("projects:timesheet_time", args=[sheet.pk]))
