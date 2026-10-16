"""Tests: weekly timesheet approval gate (P2-14).

Gap #14 of docs/world_class_employee_management_research_2026-10-14.md:
separate approved hours from raw clock data — a weekly timesheet the employee
submits and a manager approves, through the shared approval policy machinery,
before hours become payable (``is_payable``), enforced as a pre-flight blocker
when the company switches the gate on.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from company.models import Company
from payroll.models import (
    AttendanceRecord,
    CompanyPayrollSetting,
    EmployeeProfile,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
    Timesheet,
)
from payroll.services import timesheet_service
from payroll.services.preflight import run_preflight
from tests.approval_helpers import approve_request, reject_request

User = get_user_model()


class TimesheetFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Timesheet Co")
        user = User.objects.create_user(
            email="ts@example.com",
            password="password123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save()
        self.actor = user

    def _record(self, work_date, hours, status="present"):
        return AttendanceRecord.objects.create(
            company=self.company,
            employee=self.employee,
            work_date=work_date,
            status=status,
            hours_worked=Decimal(hours),
        )


class WeekAnchoringTests(TimesheetFixture):
    def test_week_start_for_is_monday(self):
        self.assertEqual(
            timesheet_service.week_start_for(date(2026, 6, 3)),  # a Wednesday
            date(2026, 6, 1),
        )
        self.assertEqual(
            timesheet_service.week_start_for(date(2026, 6, 7)),  # the Sunday
            date(2026, 6, 1),
        )

    def test_non_monday_week_start_rejected(self):
        sheet = Timesheet(
            company=self.company,
            employee=self.employee,
            week_start=date(2026, 6, 3),
            total_hours=Decimal("8"),
        )
        with self.assertRaises(ValidationError):
            sheet.full_clean()

    def test_week_end_is_sunday(self):
        sheet = timesheet_service.seed_timesheet_from_attendance(
            employee=self.employee, week_start=date(2026, 6, 3)  # normalised
        )
        self.assertEqual(sheet.week_start, date(2026, 6, 1))
        self.assertEqual(sheet.week_end, date(2026, 6, 7))


class SeedingTests(TimesheetFixture):
    def test_seeds_from_attendance_sum(self):
        self._record(date(2026, 6, 1), "8")
        self._record(date(2026, 6, 2), "4.5")
        sheet = timesheet_service.seed_timesheet_from_attendance(
            employee=self.employee, week_start=date(2026, 6, 1)
        )
        self.assertEqual(sheet.total_hours, Decimal("12.50"))
        self.assertEqual(sheet.status, Timesheet.Status.DRAFT)
        self.assertFalse(sheet.is_payable)

    def test_leave_hours_are_not_certified_work(self):
        # Leave hours are paid through the leave ledger; counting them here
        # would double-count them as worked time.
        self._record(date(2026, 6, 1), "8", status="present")
        self._record(date(2026, 6, 2), "8", status="leave")
        sheet = timesheet_service.seed_timesheet_from_attendance(
            employee=self.employee, week_start=date(2026, 6, 1)
        )
        self.assertEqual(sheet.total_hours, Decimal("8.00"))

    def test_explicit_hours_override_for_missed_clock_out(self):
        self._record(date(2026, 6, 1), "0")
        sheet = timesheet_service.seed_timesheet_from_attendance(
            employee=self.employee,
            week_start=date(2026, 6, 1),
            total_hours=Decimal("7.5"),
        )
        self.assertEqual(sheet.total_hours, Decimal("7.5"))

    def test_get_or_create_is_idempotent_and_never_reseeds(self):
        first = timesheet_service.get_or_create_timesheet(
            employee=self.employee, week_start=date(2026, 6, 2)
        )
        self.assertEqual(first.week_start, date(2026, 6, 1))  # normalised
        self._record(date(2026, 6, 1), "8")  # late attendance
        second = timesheet_service.get_or_create_timesheet(
            employee=self.employee, week_start=date(2026, 6, 1)
        )
        self.assertEqual(first.pk, second.pk)
        # Existing sheet is returned as-is: new attendance did not re-seed it.
        self.assertEqual(second.total_hours, Decimal("0"))

    def test_weekly_hours_are_unique_per_employee(self):
        timesheet_service.get_or_create_timesheet(
            employee=self.employee, week_start=date(2026, 6, 1)
        )
        with self.assertRaises(ValidationError):
            Timesheet(
                company=self.company,
                employee=self.employee,
                week_start=date(2026, 6, 1),
                total_hours=Decimal("1"),
            ).full_clean()


class SubmissionTests(TimesheetFixture):
    def _sheet(self, hours="40"):
        return timesheet_service.seed_timesheet_from_attendance(
            employee=self.employee,
            week_start=date(2026, 6, 1),
            total_hours=Decimal(hours),
        )

    def test_submit_creates_approval_request(self):
        sheet = self._sheet()
        request = timesheet_service.submit_timesheet(
            timesheet=sheet, actor=self.actor
        )
        sheet.refresh_from_db()
        self.assertEqual(sheet.status, Timesheet.Status.SUBMITTED)
        self.assertEqual(sheet.approval_request_id, request.pk)
        self.assertIsNotNone(sheet.submitted_at)
        self.assertFalse(sheet.is_payable)

    def test_submit_requires_hours(self):
        sheet = self._sheet(hours="0")
        with self.assertRaises(ValidationError):
            timesheet_service.submit_timesheet(timesheet=sheet, actor=self.actor)

    def test_cannot_submit_twice(self):
        sheet = self._sheet()
        timesheet_service.submit_timesheet(timesheet=sheet, actor=self.actor)
        with self.assertRaises(ValidationError):
            timesheet_service.submit_timesheet(timesheet=sheet, actor=self.actor)

    def test_cancel_returns_to_draft(self):
        sheet = self._sheet()
        timesheet_service.submit_timesheet(timesheet=sheet, actor=self.actor)
        timesheet_service.cancel_timesheet(timesheet=sheet, actor=self.actor)
        sheet.refresh_from_db()
        self.assertEqual(sheet.status, Timesheet.Status.DRAFT)

    def test_cannot_cancel_a_draft(self):
        sheet = self._sheet()
        with self.assertRaises(ValidationError):
            timesheet_service.cancel_timesheet(timesheet=sheet, actor=self.actor)


class ApprovalWorkflowTests(TimesheetFixture):
    def _submitted(self, hours="40"):
        sheet = timesheet_service.seed_timesheet_from_attendance(
            employee=self.employee,
            week_start=date(2026, 6, 1),
            total_hours=Decimal(hours),
        )
        timesheet_service.submit_timesheet(timesheet=sheet, actor=self.actor)
        return sheet

    def test_approval_makes_hours_payable(self):
        sheet = self._submitted()
        approve_request(sheet.approval_request)
        sheet.refresh_from_db()
        self.assertEqual(sheet.status, Timesheet.Status.APPROVED)
        self.assertTrue(sheet.is_payable)
        self.assertIsNotNone(sheet.approved_at)

    def test_rejection_keeps_hours_unpayable(self):
        sheet = self._submitted()
        reject_request(sheet.approval_request)
        sheet.refresh_from_db()
        self.assertEqual(sheet.status, Timesheet.Status.REJECTED)
        self.assertFalse(sheet.is_payable)

    def test_rejected_sheet_can_be_resubmitted(self):
        sheet = self._submitted()
        reject_request(sheet.approval_request)
        sheet.refresh_from_db()
        request = timesheet_service.submit_timesheet(
            timesheet=sheet, actor=self.actor
        )
        sheet.refresh_from_db()
        self.assertEqual(sheet.status, Timesheet.Status.SUBMITTED)
        self.assertIsNotNone(request.pk)


class UnapprovedHoursTests(TimesheetFixture):
    def test_clocked_hours_without_timesheet_are_unapproved(self):
        self._record(date(2026, 6, 1), "8")
        self._record(date(2026, 6, 2), "6")
        hours = timesheet_service.unapproved_hours_in_period(
            employee=self.employee,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        self.assertEqual(hours, Decimal("14"))

    def test_approved_timesheet_clears_the_week(self):
        self._record(date(2026, 6, 1), "8")
        sheet = timesheet_service.get_or_create_timesheet(
            employee=self.employee, week_start=date(2026, 6, 1)
        )
        timesheet_service.submit_timesheet(timesheet=sheet, actor=self.actor)
        approve_request(sheet.approval_request)

        hours = timesheet_service.unapproved_hours_in_period(
            employee=self.employee,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        self.assertEqual(hours, Decimal("0"))

    def test_submitted_but_unapproved_week_still_counts(self):
        self._record(date(2026, 6, 1), "8")
        sheet = timesheet_service.get_or_create_timesheet(
            employee=self.employee, week_start=date(2026, 6, 1)
        )
        timesheet_service.submit_timesheet(timesheet=sheet, actor=self.actor)
        hours = timesheet_service.unapproved_hours_in_period(
            employee=self.employee,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        self.assertEqual(hours, Decimal("8"))

    def test_clocked_hours_outside_the_period_do_not_count(self):
        self._record(date(2026, 5, 30), "8")  # previous month
        hours = timesheet_service.unapproved_hours_in_period(
            employee=self.employee,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        self.assertEqual(hours, Decimal("0"))


class PreflightGateTests(TimesheetFixture):
    """The gate surfaces as a typed, resolvable pre-flight blocker."""

    def setUp(self):
        super().setUp()
        self.setting = CompanyPayrollSetting.objects.create(
            company=self.company, require_timesheet_approval=True
        )
        self.entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee, netpay=Decimal("0")
        )
        self.run = PayrollRun.objects.create(
            company=self.company, name="June 2026", paydays=date(2026, 6, 1)
        )
        PayrollRunEntry.objects.create(
            payroll_run=self.run, payroll_entry=self.entry
        )
        self._record(date(2026, 6, 1), "8")

    def test_unapproved_hours_block_the_run(self):
        report = run_preflight(self.run)
        self.assertIn("unapproved_timesheets", report.codes())
        blocker = next(
            b for b in report.blockers if b.code == "unapproved_timesheets"
        )
        self.assertEqual(blocker.employee_id, self.employee.pk)
        self.assertIn("timesheet", blocker.resolution.lower())

    def test_approving_the_timesheet_clears_the_blocker(self):
        sheet = timesheet_service.get_or_create_timesheet(
            employee=self.employee, week_start=date(2026, 6, 1)
        )
        timesheet_service.submit_timesheet(timesheet=sheet, actor=self.actor)
        approve_request(sheet.approval_request)
        report = run_preflight(self.run)
        self.assertNotIn("unapproved_timesheets", report.codes())

    def test_gate_off_never_blocks(self):
        self.setting.require_timesheet_approval = False
        self.setting.save(update_fields=["require_timesheet_approval"])
        report = run_preflight(self.run)
        self.assertNotIn("unapproved_timesheets", report.codes())

    def test_attendance_in_a_later_week_of_the_period_blocks(self):
        # A second week, also inside the period, with no timesheet at all.
        self._record(date(2026, 6, 15), "8")
        report = run_preflight(self.run)
        blockers = [
            b
            for b in report.blockers
            if b.code == "unapproved_timesheets"
        ]
        self.assertEqual(len(blockers), 1)  # one blocker per employee
        self.assertEqual(blockers[0].employee_id, self.employee.pk)
