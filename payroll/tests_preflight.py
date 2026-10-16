"""Tests for the run-level pre-flight readiness check (payroll.services.preflight).

Gap #2 of docs/world_class_employee_management_research_2026-10-14.md: a run
must not reach REVIEWED while any typed, resolvable blocker stands in the way.
"""
from datetime import date
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
    RemittanceRecord,
)
from payroll.services.preflight import Blocker, PreflightReport, run_preflight


def _prev_month(period: date) -> date:
    if period.month == 1:
        return date(period.year - 1, 12, 1)
    return date(period.year, period.month - 1, 1)


def _strip_salary_config(employee):
    """Fixture setup only: null the FK with a raw UPDATE to bypass the
    EmployeeProfile.save() guard and the custom queryset's save-routing."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE payroll_employeeprofile SET employee_pay_id = NULL "
            "WHERE id = %s",
            [employee.pk],
        )
    employee.refresh_from_db()


class PreflightFixtureBase(TestCase):
    """A CALCULATED run for a single employee, with settings + bank data."""

    def setUp(self):
        self.company = Company.objects.create(name="Preflight Co")
        CompanyPayrollSetting.objects.create(company=self.company)
        user = get_user_model().objects.create_user(
            email="preflight@example.com",
            password="password123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.bank = "GTB"
        self.employee.bank_account_number = "0123456789"
        config = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("120000.00")
        )
        self.employee.employee_pay = config
        self.employee.save()

        self.period = date.today().replace(day=1)
        self.run = self._make_run(self.period, name="Preflight run")
        entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee, status="active"
        )
        PayrollRunEntry.objects.create(payroll_run=self.run, payroll_entry=entry)

    def _make_run(self, period, name):
        run = PayrollRun.objects.create(
            company=self.company, name=name, paydays=period, is_active=True
        )
        run.status = PayrollRun.Status.CALCULATED
        run.save(update_fields=["status"])
        return run


class PreflightCleanRunTests(PreflightFixtureBase):
    def test_ready_run_has_no_blockers(self):
        report = run_preflight(self.run)
        self.assertEqual(report.blockers, [])
        self.assertTrue(report.ok)
        self.assertTrue(bool(report))
        self.assertEqual(report.codes(), [])

    def test_raise_if_blocked_is_noop_when_ready(self):
        run_preflight(self.run).raise_if_blocked()  # must not raise

    def test_gate_allows_reviewed_for_ready_run(self):
        self.run.mark_reviewed()
        self.assertEqual(self.run.status, PayrollRun.Status.REVIEWED)


class PreflightBlockerTests(PreflightFixtureBase):
    def _codes(self):
        return run_preflight(self.run).codes()

    def test_missing_pay_schedule(self):
        self.run.paydays = None
        self.run.save(update_fields=["paydays"])
        self.assertIn("missing_pay_schedule", self._codes())

    def test_missing_company_payroll_settings(self):
        CompanyPayrollSetting.objects.filter(company=self.company).delete()
        self.assertIn("missing_payroll_settings", self._codes())

    def test_no_employees(self):
        PayrollRunEntry.objects.filter(payroll_run=self.run).delete()
        self.assertIn("no_employees", self._codes())

    def test_missing_salary_config(self):
        # Bypass the EmployeeProfile.save() guard that forbids direct salary
        # changes; this is fixture setup, not a workflow under test.
        _strip_salary_config(self.employee)
        report = run_preflight(self.run)
        self.assertIn("missing_salary_config", report.codes())
        blocker = next(b for b in report.blockers if b.code == "missing_salary_config")
        self.assertEqual(blocker.employee_id, self.employee.pk)

    def test_missing_bank_details(self):
        self.employee.bank_account_number = ""
        self.employee.save(update_fields=["bank_account_number"])
        self.assertIn("missing_bank_details", self._codes())

    def test_negative_net_pay(self):
        entry = PayrollEntry.objects.get(pays=self.employee)
        PayrollEntry.objects.filter(pk=entry.pk).update(netpay=Decimal("-500.00"))
        self.assertIn("negative_net_pay", self._codes())

    def test_prior_period_unlocked(self):
        prior = self._make_run(_prev_month(self.period), name="Prior run")
        self.assertFalse(prior.is_locked)
        self.assertIn("prior_period_unlocked", self._codes())

    def test_prior_period_locked_is_fine(self):
        prior = self._make_run(_prev_month(self.period), name="Prior run locked")
        # Fixture setup only: flip the legacy closed flag with a raw UPDATE to
        # bypass the lifecycle guard (is_locked is True when closed is set).
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE payroll_payrollrun SET closed = TRUE WHERE id = %s",
                [prior.pk],
            )
        prior.refresh_from_db()
        self.assertTrue(prior.is_locked)
        self.assertNotIn("prior_period_unlocked", self._codes())

    def test_unresolved_remittance(self):
        RemittanceRecord.objects.create(
            company=self.company,
            obligation="paye",
            period=_prev_month(self.period),
        )
        report = run_preflight(self.run)
        self.assertIn("unresolved_remittance", report.codes())
        blocker = next(
            b for b in report.blockers if b.code == "unresolved_remittance"
        )
        self.assertEqual(blocker.obligation, "paye")

    def test_remitted_record_is_not_a_blocker(self):
        RemittanceRecord.objects.create(
            company=self.company,
            obligation="paye",
            period=_prev_month(self.period),
            remitted_on=date.today(),
        )
        self.assertNotIn("unresolved_remittance", self._codes())

    def test_blocker_as_dict_is_json_shaped(self):
        CompanyPayrollSetting.objects.filter(company=self.company).delete()
        report = run_preflight(self.run)
        payload = report.blockers[0].as_dict()
        for key in ("code", "message", "resolution", "employee_id"):
            self.assertIn(key, payload)


class PreflightGateEnforcementTests(PreflightFixtureBase):
    def test_gate_blocks_reviewed_when_not_ready(self):
        _strip_salary_config(self.employee)
        with self.assertRaises(ValidationError) as ctx:
            self.run.mark_reviewed()
        self.assertIn("missing_salary_config", str(ctx.exception))
        # Status must not have advanced.
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, PayrollRun.Status.CALCULATED)

    def test_gate_message_lists_every_blocker(self):
        _strip_salary_config(self.employee)
        self.employee.bank = ""
        self.employee.save(update_fields=["bank"])
        with self.assertRaises(ValidationError) as ctx:
            self.run.mark_reviewed()
        message = str(ctx.exception)
        self.assertIn("missing_salary_config", message)
        self.assertIn("missing_bank_details", message)

    def test_gate_does_not_affect_other_transitions(self):
        # DRAFT -> CALCULATED is not gated.
        self.run.status = PayrollRun.Status.DRAFT
        self.run.save(update_fields=["status"])
        _strip_salary_config(self.employee)
        self.run.mark_calculated()
        self.assertEqual(self.run.status, PayrollRun.Status.CALCULATED)


class BlockerAndReportUnitTests(TestCase):
    def test_blocker_defaults_and_dict(self):
        blocker = Blocker(
            code="x", message="m", resolution="r", employee_id=7
        )
        self.assertEqual(
            blocker.as_dict(),
            {
                "code": "x",
                "message": "m",
                "resolution": "r",
                "employee_id": 7,
                "obligation": None,
                "period": None,
            },
        )

    def test_report_ok_reflects_blockers(self):
        empty = PreflightReport()
        self.assertTrue(empty.ok)
        blocked = PreflightReport(
            blockers=[Blocker(code="x", message="m", resolution="r")]
        )
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.codes(), ["x"])
        with self.assertRaises(ValidationError):
            blocked.raise_if_blocked()
