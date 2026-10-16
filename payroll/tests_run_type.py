"""Tests for off-cycle and correction payrolls (P1-4).

Gap #4 of docs/world_class_employee_management_research_2026-10-14.md: add a run
type (regular / off_cycle / termination) with reason codes. Same-period re-runs
of a regular run remain allowed (a supported product flow), so corrections are
kept tidy by reason-coded run types rather than an overlap ban.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from company.models import Company
from payroll.models import (
    EmployeeProfile,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
)

PERIOD = date(2026, 6, 1)


class RunTypeFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Run Type Co")
        user = get_user_model().objects.create_user(
            email="runtype@example.com",
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
            company=self.company, basic_salary=Decimal("120000.00")
        )
        self.employee.employee_pay = config
        self.employee.save()

    def _run(self, **kwargs):
        defaults = dict(
            company=self.company, name="Run", paydays=PERIOD, is_active=True
        )
        defaults.update(kwargs)
        return PayrollRun.objects.create(**defaults)

    def _attach_entry(self, run):
        entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee, status="active"
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        return entry


class RunTypeDefaultsTests(RunTypeFixture):
    def test_default_run_type_is_regular(self):
        run = self._run(name="Default run")
        self.assertEqual(run.run_type, PayrollRun.RunType.REGULAR)
        self.assertEqual(run.reason_code, "")

    def test_run_type_choices_are_regular_offcycle_termination(self):
        codes = {code for code, _ in PayrollRun.RunType.choices}
        self.assertEqual(codes, {"regular", "off_cycle", "termination"})


class ReasonCodeTests(RunTypeFixture):
    def test_off_cycle_run_requires_reason_code(self):
        with self.assertRaises(ValidationError) as ctx:
            self._run(name="Off-cycle no reason", run_type="off_cycle")
        self.assertIn("reason code", str(ctx.exception))

    def test_termination_run_requires_reason_code(self):
        with self.assertRaises(ValidationError):
            self._run(name="Term no reason", run_type="termination")

    def test_off_cycle_run_with_reason_code_is_saved(self):
        run = self._run(
            name="Correction run", run_type="off_cycle", reason_code="correction"
        )
        self.assertEqual(run.run_type, "off_cycle")
        self.assertEqual(run.reason_code, "correction")

    def test_termination_run_with_reason_code_is_saved(self):
        run = self._run(
            name="Final run",
            run_type="termination",
            reason_code="final_settlement",
        )
        self.assertEqual(run.reason_code, "final_settlement")


class RegularOverlapTests(RunTypeFixture):
    """Re-runs of the same period stay legal.

    The product supports re-running a pay period (report period lists dedupe
    repeated paydays — ``payroll.tests_tax.ReportListPagePortabilityTests``),
    so no overlap guard exists; run *types* are what keep corrections tidy.
    """

    def test_same_period_re_run_is_allowed(self):
        self._run(name="Regular June")
        # Re-runs share the auto slug base (pay-period-YYYY-MM), so they carry
        # an explicit slug — the same flow the report dedupe test exercises.
        rerun = self._run(
            name="Regular June (re-run)", slug="pay-period-2026-06-b"
        )
        self.assertEqual(rerun.paydays, PERIOD)
        self.assertEqual(
            PayrollRun.objects.filter(paydays=PERIOD, run_type="regular").count(),
            2,
        )

    def test_regular_run_for_different_period_is_allowed(self):
        self._run(name="Regular June")
        other = self._run(name="Regular July", paydays=date(2026, 7, 1))
        self.assertEqual(other.paydays, date(2026, 7, 1))

    def test_off_cycle_run_may_overlap_regular_run(self):
        self._run(name="Regular June")
        correction = self._run(
            name="June correction",
            run_type="off_cycle",
            reason_code="correction",
        )
        self.assertEqual(correction.run_type, "off_cycle")

    def test_termination_run_may_overlap_regular_run(self):
        self._run(name="Regular June")
        term = self._run(
            name="June termination",
            run_type="termination",
            reason_code="final_settlement",
        )
        self.assertEqual(term.run_type, "termination")

    def test_two_off_cycle_runs_may_overlap(self):
        self._run(
            name="Correction A", run_type="off_cycle", reason_code="correction"
        )
        second = self._run(
            name="Correction B", run_type="off_cycle", reason_code="bonus"
        )
        self.assertEqual(second.reason_code, "bonus")

    def test_resaving_a_regular_run_is_allowed(self):
        run = self._run(name="Regular June")
        run.name = "Regular June renamed"
        run.save()
        self.assertEqual(PayrollRun.objects.filter(paydays=PERIOD).count(), 1)

    def test_same_period_runs_in_other_companies_are_independent(self):
        self._run(name="Regular June")
        other_company = Company.objects.create(name="Other Co")
        # A different company's regular run for the same period is fine.
        PayrollRun.objects.create(
            company=other_company,
            name="Other regular June",
            paydays=PERIOD,
            is_active=True,
        )
        self.assertEqual(
            PayrollRun.objects.filter(paydays=PERIOD).count(), 2
        )
