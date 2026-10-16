from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from company.models import Company
from payroll import models
from payroll.forms.leave_forms import LeaveRequestForm
from payroll.services.leave_type_service import available_leave_balances
from payroll.services.timesheet_service import get_or_create_timesheet, submit_timesheet
from tests.approval_helpers import approve_request


class HRSurfaceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Product HR")
        self.other = Company.objects.create(name="Other HR")
        self.user = get_user_model().objects.create_user(email="product@example.com", password="x", company=self.company, active_company=self.company)
        self.employee = models.EmployeeProfile.objects.get(user=self.user)
        self.client.force_login(self.user)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def grant(self, *codes):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="payroll", codename__in=codes))
        for attr in ("_perm_cache", "_user_perm_cache"):
            self.user.__dict__.pop(attr, None)

    def test_custom_leave_type_form_balance_and_approval(self):
        models.LeaveType.objects.create(company=self.company, code="STUDY", name="Study leave", default_days=Decimal("3.50"), allows_half_day=True)
        models.LeaveType.objects.create(company=self.other, code="PRIVATE", name="Private", default_days=5)
        data = {"leave_type": "STUDY", "start_date": "2026-06-01", "end_date": "2026-06-01", "reason": "Study", "is_half_day": True}
        form = LeaveRequestForm(data, employee=self.employee)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("PRIVATE", dict(form.fields["leave_type"].choices))
        leave = form.save(commit=False)
        leave.requested_by = self.user
        leave.save()
        from payroll.services.hr_workflow import submit_hr_request
        approve_request(submit_hr_request(leave, self.user))
        self.assertEqual(available_leave_balances(self.employee, 2026)["STUDY"], Decimal("3.00"))
        self.assertEqual(available_leave_balances(self.employee, 2026)["STUDY"], Decimal("3.00"))

    def test_custom_types_render_in_leave_ui(self):
        models.LeaveType.objects.create(company=self.company, code="STUDY", name="Study leave", default_days=3)
        response = self.client.get(reverse("payroll:apply_leave"))
        self.assertContains(response, "Study leave")
        self.assertContains(self.client.get(reverse("payroll:leave_requests")), "Study leave")

    def test_analytics_requires_salary_and_people_access(self):
        url = reverse("api:v1:people-analytics")
        self.assertEqual(self.api.get(url).status_code, 403)
        self.grant("view_employeeprofile", "view_payrollentry")
        response = self.api.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["company_id"], self.company.pk)
        self.assertEqual(self.api.get(url, {"start": "bad"}).status_code, 400)
        self.assertEqual(self.api.get(url, {"start": "2026-07-01", "end": "2026-06-01"}).status_code, 400)
        self.assertEqual(self.api.get(url, {"metrics": "secrets"}).status_code, 400)
        self.assertEqual(self.client.get(reverse("payroll:people_analytics")).status_code, 200)

    def test_timesheet_api_ownership_and_workflow(self):
        url = reverse("api:v1:timesheet-list")
        response = self.api.post(url, {"week_start": "2026-06-01", "total_hours": "8.00"})
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        response = self.api.post(reverse("api:v1:timesheet-submit", args=[pk]))
        self.assertEqual(response.status_code, 200, response.data)
        response = self.api.patch(reverse("api:v1:timesheet-detail", args=[pk]), {"total_hours": "12.00"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.api.post(reverse("api:v1:timesheet-decide", args=[pk]), {"decision": "APPROVE"}).status_code, 403)
        self.assertEqual(self.api.post(reverse("api:v1:timesheet-withdraw", args=[pk])).status_code, 200)
        self.assertEqual(self.api.post(reverse("api:v1:timesheet-submit", args=[pk])).status_code, 200)
        sheet = models.Timesheet.objects.get(pk=pk)
        approve_request(sheet.approval_request)
        sheet.refresh_from_db()
        self.assertTrue(sheet.is_payable)
        self.assertEqual(self.client.get(reverse("payroll:timesheets")).status_code, 200)
        self.assertEqual(self.client.get(reverse("payroll:timesheet_action", args=[pk])).status_code, 405)

    def test_independent_reviewer_can_use_timesheet_api(self):
        from tests.approval_helpers import approval_user
        sheet = get_or_create_timesheet(employee=self.employee, week_start=date(2026, 6, 1))
        sheet.total_hours = 8
        sheet.save()
        submit_timesheet(timesheet=sheet, actor=self.user)
        checker = approval_user(self.company, ["payroll.change_timesheet"])
        self.api.force_authenticate(checker)
        response = self.api.post(reverse("api:v1:timesheet-decide", args=[sheet.pk]), {"decision": "APPROVE"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["is_payable"])

    def test_admin_and_api_hide_other_company_salary_bands(self):
        from django.test import RequestFactory
        models.SalaryBand.objects.create(company=self.other, position_title="Private role", min_salary=1, mid_salary=2, max_salary=3)
        self.grant("view_salaryband")
        response = self.api.get(reverse("api:v1:salary-bands-list"))
        self.assertEqual(response.status_code, 200)
        rows = response.data.get("results", []) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 0)
        request = RequestFactory().get("/")
        request.user = self.user
        self.assertEqual(admin.site._registry[models.SalaryBand].get_queryset(request).count(), 0)

    def test_duplicate_leave_code_and_inactive_choices(self):
        self.grant("view_leavetype", "add_leavetype", "change_leavetype")
        url = reverse("api:v1:leave-type-list")
        payload = {"code": "STUDY", "name": "Study", "default_days": "3.5"}
        response = self.api.post(url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.api.post(url, payload, format="json").status_code, 400)
        self.api.patch(reverse("api:v1:leave-type-detail", args=[response.data["id"]]), {"is_active": False}, format="json")
        self.assertNotIn("STUDY", dict(LeaveRequestForm(employee=self.employee).fields["leave_type"].choices))

    def test_admin_reports_duplicate_company_band_as_form_error(self):
        from django.test import RequestFactory
        self.grant("add_salaryband", "view_salaryband")
        models.SalaryBand.objects.create(company=self.company, position_title="Engineer", min_salary=1, mid_salary=2, max_salary=3)
        request = RequestFactory().get("/")
        request.user = self.user
        form_class = admin.site._registry[models.SalaryBand].get_form(request)
        form = form_class(data={"position_title": "Engineer", "min_salary": 1, "mid_salary": 2, "max_salary": 3, "currency": "NGN", "is_active": True})
        self.assertFalse(form.is_valid())
        self.assertIn("already exists", str(form.errors))

    def test_default_hr_role_can_reach_new_surfaces(self):
        from django.contrib.auth.models import Group
        from payroll.permissions import setup_groups_and_permissions
        setup_groups_and_permissions()
        self.user.groups.add(Group.objects.get(name="HR"))
        self.assertEqual(self.client.get(reverse("payroll:leave_types")).status_code, 200)
        self.assertEqual(self.client.get(reverse("payroll:people_analytics")).status_code, 200)
        employee_group = Group.objects.get(name="Employee")
        self.assertFalse(employee_group.permissions.filter(codename="view_timesheet").exists())
        self.assertFalse(employee_group.permissions.filter(codename="view_compreview").exists())

    def test_cross_company_timesheet_hidden(self):
        outsider = get_user_model().objects.create_user(email="other@example.com", password="x", company=self.other)
        sheet = get_or_create_timesheet(employee=models.EmployeeProfile.objects.get(user=outsider), week_start=date(2026, 6, 1))
        self.grant("view_timesheet", "change_timesheet")
        self.assertEqual(self.api.get(reverse("api:v1:timesheet-detail", args=[sheet.pk])).status_code, 404)

    def test_leave_type_api_scoped_and_validated(self):
        url = reverse("api:v1:leave-type-list")
        self.assertEqual(self.api.get(url).status_code, 403)
        self.grant("view_leavetype", "add_leavetype", "change_leavetype")
        response = self.api.post(url, {"code": "STUDY", "name": "Study", "default_days": "3.5"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        response = self.api.patch(reverse("api:v1:leave-type-detail", args=[pk]), {"default_days": "-1"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(reverse("payroll:leave_types")).status_code, 200)
        self.assertEqual(self.api.get(reverse("api:v1:leave-balances")).status_code, 200)

    def test_record_apis_and_pages_require_permissions_and_scope(self):
        from payroll.services.hr_surfaces import RESOURCES
        for resource, (model, scope) in RESOURCES.items():
            url = reverse(f"api:v1:{resource}-list")
            self.assertEqual(self.api.get(url).status_code, 403, resource)
            self.grant(f"view_{model._meta.model_name}")
            self.assertEqual(self.api.get(url).status_code, 200, resource)
            self.assertEqual(self.client.get(reverse("payroll:hr_records", args=[resource])).status_code, 200)
            self.assertIn(model, admin.site._registry)


from payroll.tests_attendance_payroll import AttendancePayrollFixture


class TimesheetCalculationTests(AttendancePayrollFixture):
    def test_payroll_overtime_excludes_unapproved_weeks_when_required(self):
        from payroll.services.overtime_service import get_overtime_allowance
        self._approve_overtime(date(2026, 6, 1))
        self._approve_overtime(date(2026, 6, 8))
        start, end = date(2026, 6, 1), date(2026, 6, 30)
        ungated = get_overtime_allowance(self.employee, start, end)
        self.assertGreater(ungated, 0)
        setting, _ = models.CompanyPayrollSetting.objects.get_or_create(company=self.company)
        setting.require_timesheet_approval = True
        setting.save()
        self.assertEqual(get_overtime_allowance(self.employee, start, end), 0)
        sheet = get_or_create_timesheet(employee=self.employee, week_start=start)
        sheet.total_hours = 10
        sheet.save()
        approval = submit_timesheet(timesheet=sheet, actor=self.employee.user)
        approve_request(approval)
        self.assertEqual(get_overtime_allowance(self.employee, start, end), ungated / 2)
        self.assertEqual(self.entry._get_auto_overtime_allowance(start, end), ungated / 2)
        setting.require_timesheet_approval = False
        setting.save()
        self.assertEqual(get_overtime_allowance(self.employee, start, end), ungated)
