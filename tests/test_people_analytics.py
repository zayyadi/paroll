"""Tests for the people-analytics dataset (P2-13).

Gap #13 of docs/world_class_employee_management_research_2026-10-14.md: a
documented, query-shaped dataset surface for headcount, attrition, absence,
overtime and payroll cost, mirroring BambooHR Datasets.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from company.models import Company
from integrations.people_analytics import (
    absence,
    attrition,
    dataset_as_json,
    headcount,
    overtime,
    payroll_cost,
)
from payroll.models import (
    AttendanceRecord,
    Department,
    EmployeeProfile,
    OvertimeEntry,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
)
from payroll.models.workforce import OffboardingChecklist

from tests.approval_helpers import approve_source

User = get_user_model()


class AnalyticsFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Analytics Co")
        self.other = Company.objects.create(name="Other Co")
        self.engineering = Department.objects.create(
            company=self.company, name="Engineering"
        )
        self.sales = Department.objects.create(company=self.company, name="Sales")

        self.alice = self._employee(
            "alice@example.com", "Alice", "A001", self.engineering
        )
        self.bob = self._employee(
            "bob@example.com", "Bob", "A002", self.sales
        )

    def _employee(self, email, first, emp_id, department, company=None, status="active"):
        company = company or self.company
        user = User.objects.create_user(
            email=email, password="password123", company=company,
            active_company=company,
        )
        profile = user.employee_user
        profile.company = company
        profile.department = department
        profile.emp_id = emp_id
        profile.first_name = first
        profile.status = status
        profile.save()
        return profile

    def _completed_offboarding(self, employee, last_working_day):
        """Drive a real offboarding through its approval workflow to COMPLETED."""
        checklist = OffboardingChecklist.objects.create(
            company=self.company, employee=employee,
            last_working_day=last_working_day, reason="Resignation",
        )
        approve_source(checklist, "offboarding.complete")
        checklist.refresh_from_db()
        return checklist

    def _approved_overtime(self, employee, work_date, hours, multiplier):
        """Drive a real overtime entry through its approval workflow to APPROVED."""
        overtime = OvertimeEntry.objects.create(
            company=self.company, employee=employee, date=work_date,
            hours=hours, rate_multiplier=multiplier,
        )
        approve_source(overtime, "overtime.approve")
        overtime.refresh_from_db()
        return overtime

    def _payroll_run(self, paydays):
        """Create a run with one entry; returns (run, entry_netpay).

        PayrollEntry.save() recomputes netpay from the pay config, so the
        caller asserts against the recomputed figure rather than a guess.
        """
        payroll = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("1200000")
        )
        self.alice.employee_pay = payroll
        self.alice.save(update_fields=["employee_pay"])
        entry = PayrollEntry.objects.create(
            company=self.company, pays=self.alice, netpay=Decimal("0")
        )
        # PayrollEntry.save() recomputes netpay from the pay config; read back
        # the real figure so the assertion tests the aggregation, not a guess.
        entry.refresh_from_db()
        run = PayrollRun.objects.create(
            company=self.company, name=f"Run {paydays}", paydays=paydays,
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        return run, entry.netpay


class HeadcountTests(AnalyticsFixture):
    def test_counts_active_and_groups_by_department(self):
        result = headcount(self.company)
        self.assertEqual(result["total"], 2)
        by_dept = {row["department"]: row["count"] for row in result["by_department"]}
        self.assertEqual(by_dept, {"Engineering": 1, "Sales": 1})

    def test_excludes_inactive_and_other_company(self):
        self.bob.status = "suspended"
        self.bob.save(update_fields=["status"])
        self._employee(
            "carol@example.com", "Carol", "A003", self.sales, company=self.other
        )
        result = headcount(self.company)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["by_department"][0]["department"], "Engineering")


class AttritionTests(AnalyticsFixture):
    def test_completed_offboarding_counts_as_exit(self):
        self._completed_offboarding(self.bob, date(2026, 3, 31))
        result = attrition(self.company, start=date(2026, 1, 1), end=date(2026, 12, 31))
        self.assertEqual(result["terminations"], 1)
        self.assertEqual(result["headcount"], 2)
        self.assertEqual(result["rate"], Decimal("0.5000"))

    def test_in_progress_and_out_of_window_excluded(self):
        # An in-progress (not yet approved) offboarding is not an exit.
        OffboardingChecklist.objects.create(
            company=self.company, employee=self.bob, last_working_day=date(2026, 3, 31),
            status="IN_PROGRESS", reason="Resignation",
        )
        # A completed offboarding dated before the window is out of scope.
        self._completed_offboarding(self.alice, date(2025, 1, 15))
        result = attrition(self.company, start=date(2026, 1, 1), end=date(2026, 12, 31))
        self.assertEqual(result["terminations"], 0)
        self.assertEqual(result["rate"], Decimal("0.0000"))


class AbsenceTests(AnalyticsFixture):
    def test_sums_absent_hours_per_employee(self):
        AttendanceRecord.objects.create(
            company=self.company, employee=self.alice, work_date=date(2026, 5, 4),
            status="absent", hours_worked=Decimal("8.00"),
        )
        AttendanceRecord.objects.create(
            company=self.company, employee=self.alice, work_date=date(2026, 5, 5),
            status="absent", hours_worked=Decimal("4.00"),
        )
        AttendanceRecord.objects.create(
            company=self.company, employee=self.alice, work_date=date(2026, 5, 6),
            status="present", hours_worked=Decimal("8.00"),
        )
        result = absence(self.company, start=date(2026, 5, 1), end=date(2026, 5, 31))
        self.assertEqual(result["total_hours"], Decimal("12.00"))
        self.assertEqual(result["total_days"], 2)
        self.assertEqual(result["by_employee"][0]["hours"], Decimal("12.00"))

    def test_window_bounds_filter(self):
        AttendanceRecord.objects.create(
            company=self.company, employee=self.alice, work_date=date(2026, 4, 30),
            status="absent", hours_worked=Decimal("8.00"),
        )
        result = absence(self.company, start=date(2026, 5, 1), end=date(2026, 5, 31))
        self.assertEqual(result["total_hours"], Decimal("0"))


class OvertimeTests(AnalyticsFixture):
    def test_only_approved_hours_and_weighted_pay(self):
        # Approved entry: 2h at 1.5x = 3.0 weighted hours.
        self._approved_overtime(self.alice, date(2026, 6, 1), Decimal("2.00"), Decimal("1.50"))
        # A pending (unapproved) entry must not count.
        OvertimeEntry.objects.create(
            company=self.company, employee=self.alice, date=date(2026, 6, 2),
            hours=Decimal("3.00"), rate_multiplier=Decimal("2.00"),
        )
        result = overtime(self.company, start=date(2026, 6, 1), end=date(2026, 6, 30))
        self.assertEqual(result["total_hours"], Decimal("2.00"))
        self.assertEqual(result["total_weighted_hours"], Decimal("3.00"))


class PayrollCostTests(AnalyticsFixture):
    def test_sums_netpay_by_run_within_window(self):
        run, netpay = self._payroll_run(date(2026, 6, 1))
        result = payroll_cost(self.company, start=date(2026, 6, 1), end=date(2026, 6, 30))
        self.assertEqual(result["total_net_pay"], netpay)
        self.assertEqual(result["runs"][0]["employees"], 1)
        self.assertEqual(result["runs"][0]["payroll_run_id"], run.pk)

    def test_excludes_runs_outside_window(self):
        self._payroll_run(date(2026, 5, 1))
        result = payroll_cost(self.company, start=date(2026, 6, 1), end=date(2026, 6, 30))
        self.assertEqual(result["total_net_pay"], Decimal("0"))
        self.assertEqual(result["runs"], [])


class DatasetAsJsonTests(AnalyticsFixture):
    def test_returns_all_metrics_json_safe(self):
        document = dataset_as_json(
            self.company, start=date(2026, 1, 1), end=date(2026, 12, 31)
        )
        self.assertEqual(
            set(document["metrics"]),
            {"headcount", "attrition", "absence", "overtime", "payroll_cost"},
        )
        self.assertNotIn("errors", document)
        # JSON-safe: Decimals are strings, dates are iso strings.
        self.assertEqual(document["metrics"]["headcount"]["total"], 2)
        self.assertIsInstance(document["metrics"]["attrition"]["rate"], str)

    def test_unknown_metric_rejected(self):
        with self.assertRaises(ValueError):
            dataset_as_json(self.company, metrics=["nope"])

    def test_single_metric_selection(self):
        document = dataset_as_json(self.company, metrics=["headcount"])
        self.assertEqual(set(document["metrics"]), {"headcount"})
