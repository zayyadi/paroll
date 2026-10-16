"""Tests: attendance feeds gross pay + Odoo-style integrity (P1-7).

Gap #7 of docs/world_class_employee_management_research_2026-10-14.md:
- approved OvertimeEntry and absent days reach the payroll calculation path;
- one open check-in per employee, no overlapping attendance records
  (Odoo hr_attendance ``_check_validity`` style).
"""
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from company.models import Company
from payroll.models import (
    CompanyPayrollSetting,
    EmployeeProfile,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
)
from payroll.models.workforce import AttendanceRecord, OvertimeEntry
from payroll.services.payroll_calc import absence_deduction

CENTS = Decimal("0.01")


class AttendanceIntegrityTests(TestCase):
    """Odoo-style constraints: one open check-in, no overlapping sessions."""

    def setUp(self):
        self.company = Company.objects.create(name="Attendance Integrity Co")
        user = get_user_model().objects.create_user(
            email="attend@example.com",
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

    def _record(self, work_date, clock_in=None, clock_out=None, **overrides):
        defaults = dict(
            company=self.company,
            employee=self.employee,
            work_date=work_date,
            status="present",
            clock_in=clock_in,
            clock_out=clock_out,
        )
        defaults.update(overrides)
        return AttendanceRecord.objects.create(**defaults)

    def test_clock_out_without_clock_in_rejected(self):
        with self.assertRaises(ValidationError):
            self._record(
                date(2026, 6, 1),
                clock_in=None,
                clock_out=datetime(2026, 6, 1, 17, 0),
            )

    def test_single_open_check_in_allowed(self):
        record = self._record(
            date(2026, 6, 1), clock_in=datetime(2026, 6, 1, 9, 0)
        )
        self.assertIsNotNone(record.pk)

    def test_second_open_check_in_rejected(self):
        self._record(date(2026, 6, 1), clock_in=datetime(2026, 6, 1, 9, 0))
        with self.assertRaises(ValidationError) as ctx:
            self._record(
                date(2026, 6, 2), clock_in=datetime(2026, 6, 2, 9, 0)
            )
        self.assertIn("open check-in", str(ctx.exception))

    def test_closed_then_open_check_in_allowed(self):
        # First session closed: a new open check-in is fine.
        self._record(
            date(2026, 6, 1),
            clock_in=datetime(2026, 6, 1, 9, 0),
            clock_out=datetime(2026, 6, 1, 17, 0),
        )
        record = self._record(
            date(2026, 6, 2), clock_in=datetime(2026, 6, 2, 9, 0)
        )
        self.assertIsNotNone(record.pk)

    def test_overlapping_sessions_rejected(self):
        # Session crossing midnight to day 2 noon...
        self._record(
            date(2026, 6, 1),
            clock_in=datetime(2026, 6, 1, 9, 0),
            clock_out=datetime(2026, 6, 2, 12, 0),
        )
        # ...overlaps a day-2 session starting at 10:00.
        with self.assertRaises(ValidationError) as ctx:
            self._record(
                date(2026, 6, 2),
                clock_in=datetime(2026, 6, 2, 10, 0),
                clock_out=datetime(2026, 6, 2, 18, 0),
            )
        self.assertIn("overlap", str(ctx.exception))

    def test_back_to_back_sessions_allowed(self):
        # Previous session ends exactly when the next begins: not an overlap.
        self._record(
            date(2026, 6, 1),
            clock_in=datetime(2026, 6, 1, 9, 0),
            clock_out=datetime(2026, 6, 2, 1, 0),
        )
        record = self._record(
            date(2026, 6, 2),
            clock_in=datetime(2026, 6, 2, 1, 0),
            clock_out=datetime(2026, 6, 2, 18, 0),
        )
        self.assertIsNotNone(record.pk)

    def test_disjoint_sessions_allowed(self):
        self._record(
            date(2026, 6, 1),
            clock_in=datetime(2026, 6, 1, 9, 0),
            clock_out=datetime(2026, 6, 1, 17, 0),
        )
        record = self._record(
            date(2026, 6, 2),
            clock_in=datetime(2026, 6, 2, 9, 0),
            clock_out=datetime(2026, 6, 2, 17, 0),
        )
        self.assertIsNotNone(record.pk)

    def test_status_only_rows_exempt_from_check_in_rules(self):
        # A leave row (no clock times) may exist while a check-in is open.
        self._record(
            date(2026, 6, 1), clock_in=datetime(2026, 6, 1, 9, 0)
        )
        record = self._record(date(2026, 6, 2), status="leave")
        self.assertIsNotNone(record.pk)

    def test_one_record_per_employee_day_still_enforced(self):
        self._record(date(2026, 6, 1))
        with self.assertRaises(ValidationError):
            self._record(date(2026, 6, 1))


class AttendancePayrollFixture(TestCase):
    """Employee on 176,000 monthly basic with a June 2026 payroll run."""

    PERIOD = date(2026, 6, 1)

    def setUp(self):
        self.company = Company.objects.create(name="Attendance Payroll Co")
        user = get_user_model().objects.create_user(
            email="att-pay@example.com",
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
        config = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("176000.00")
        )
        self.employee.employee_pay = config
        self.employee.save()
        self.config = config

        self.run = PayrollRun.objects.create(
            company=self.company,
            name="June 2026 attendance run",
            paydays=self.PERIOD,
            is_active=True,
        )
        self.entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee, status="active"
        )
        PayrollRunEntry.objects.create(
            payroll_run=self.run, payroll_entry=self.entry
        )
        self.entry = PayrollEntry.objects.get(pk=self.entry.pk)

    def _approve_overtime(self, overtime_date, hours="2.00", multiplier="1.50"):
        entry = OvertimeEntry.objects.create(
            company=self.company,
            employee=self.employee,
            date=overtime_date,
            hours=Decimal(hours),
            rate_multiplier=Decimal(multiplier),
        )
        checker = get_user_model().objects.create_user(
            email=f"ot-checker-{OvertimeEntry.objects.count()}@example.com",
            password="x",
            company=self.company,
        )
        from django.contrib.auth.models import Permission

        checker.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="payroll",
                codename="change_overtimeentry",
            )
        )
        from payroll.services.overtime_service import approve_overtime

        approve_overtime(entry=entry, approved_by=checker)
        entry.refresh_from_db()
        return entry


class OvertimeFeedsGrossPayTests(AttendancePayrollFixture):
    def _expected(self, hours, multiplier):
        weighted = Decimal(str(float(hours) * float(multiplier)))
        return (weighted * (self.config.basic / Decimal("176"))).quantize(CENTS)

    def test_approved_overtime_appears_in_allowances(self):
        ot = self._approve_overtime(date(2026, 6, 10))
        self.assertEqual(ot.status, "APPROVED")
        self.assertEqual(
            self.entry.calc_allowance, self._expected(ot.hours, ot.rate_multiplier)
        )

    def test_pending_overtime_not_in_allowances(self):
        OvertimeEntry.objects.create(
            company=self.company,
            employee=self.employee,
            date=date(2026, 6, 10),
            hours=Decimal("2.00"),
            rate_multiplier=Decimal("1.50"),
        )
        self.assertEqual(self.entry.calc_allowance, Decimal(0))

    def test_overtime_outside_period_not_counted(self):
        self._approve_overtime(date(2026, 5, 20))
        self.assertEqual(self.entry.calc_allowance, Decimal(0))

    def test_overtime_is_not_counted_twice(self):
        ot = self._approve_overtime(date(2026, 6, 10))
        first = self.entry.calc_allowance
        second = self.entry.calc_allowance
        self.assertEqual(first, second)
        self.assertEqual(first, self._expected(ot.hours, ot.rate_multiplier))


class AbsenceDeductionTests(AttendancePayrollFixture):
    def _absent(self, work_date):
        AttendanceRecord.objects.create(
            company=self.company,
            employee=self.employee,
            work_date=work_date,
            status="absent",
        )

    def test_opt_out_by_default_no_deduction(self):
        self._absent(date(2026, 6, 3))
        self._absent(date(2026, 6, 4))
        self.assertEqual(self.entry.calc_deduction, Decimal(0))
        self.assertEqual(self.entry.calc_absence_deduction, Decimal(0))

    def test_opt_in_deducts_one_daily_rate_per_absent_day(self):
        CompanyPayrollSetting.objects.create(
            company=self.company, deduct_unpaid_absence=True
        )
        self._absent(date(2026, 6, 3))
        self._absent(date(2026, 6, 4))
        expected = absence_deduction(self.config.basic_salary, 2)
        self.assertEqual(self.entry.calc_absence_deduction, expected)
        self.assertEqual(self.entry.calc_deduction, expected)

    def test_absence_in_other_month_not_counted(self):
        CompanyPayrollSetting.objects.create(
            company=self.company, deduct_unpaid_absence=True
        )
        self._absent(date(2026, 5, 20))
        self.assertEqual(self.entry.calc_absence_deduction, Decimal(0))

    def test_canonical_daily_rate(self):
        # 176,000 / 22 = 8,000 per day.
        self.assertEqual(
            absence_deduction(Decimal("176000"), 2), Decimal("16000.00")
        )
        self.assertEqual(absence_deduction(Decimal("176000"), 0), Decimal("0.00"))
        self.assertEqual(absence_deduction(Decimal("0"), 3), Decimal("0.00"))
