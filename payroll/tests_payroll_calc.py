"""Parity tests locking the canonical net-pay calculator (payroll_calc).

Gap #1 of docs/world_class_employee_management_research_2026-10-14.md required
finishing the delegation so that the three formerly competing net-pay
definitions all route through ``payroll.services.payroll_calc``:

- ``payroll.utils.get_net_pay``               -> ``monthly_net_pay``
- ``payroll.models.PayrollEntry.get_netpay``  -> ``entry_net_pay``
- ``payroll.utils.monthly_cost_breakdown``    -> ``annual_to_monthly`` +
  ``monthly_net_pay``

These tests assert each delegating function still returns exactly the value the
pre-migration implementation returned (behaviour-preserving refactor), and that
the pension ``/12`` discrepancy between the employer-cost view and the payslip
path is documented and pinned.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from company.models import Company
from payroll import utils
from payroll.models import (
    Deduction,
    EmployeeProfile,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
)
from payroll.services.payroll_calc import (
    annual_to_monthly,
    entry_net_pay,
    monthly_net_pay,
)

CENTS = Decimal("0.01")


def _legacy_get_net_pay(config):
    """The pre-delegation ``get_net_pay`` formula, inlined.

    Kept here (not imported from production code) so the parity test compares
    against an independent transcription rather than the code under test.
    """
    if config is None:
        return Decimal(0.0)
    annual_gross = Decimal(
        getattr(config, "gross_income", Decimal("0.00")) or Decimal("0.00")
    )
    if annual_gross <= 0:
        annual_gross = utils.gross_income(config)
    employee_health = Decimal(
        getattr(config, "employee_health", Decimal("0.00")) or Decimal("0.00")
    )
    nhf = Decimal(getattr(config, "nhf", Decimal("0.00")) or Decimal("0.00"))
    payee = Decimal(getattr(config, "payee", Decimal("0.00")) or Decimal("0.00"))
    water_rate = Decimal(
        getattr(config, "water_rate", Decimal("0.00")) or Decimal("0.00")
    )
    return (
        (annual_gross / Decimal("12"))
        - (employee_health / Decimal("12"))
        - (nhf / Decimal("12"))
        - payee
        - water_rate
    )


def _legacy_monthly_cost_breakdown(config):
    """The pre-delegation ``monthly_cost_breakdown`` formula, inlined."""
    gross = (Decimal(config.gross_income or 0) / Decimal("12")).quantize(CENTS)
    employee_paye = Decimal(config.payee or 0).quantize(CENTS)
    employee_pension = (
        Decimal(config.pension_employee or 0) / Decimal("12")
    ).quantize(CENTS)
    employee_nhf = (Decimal(config.nhf or 0) / Decimal("12")).quantize(CENTS)
    employee_nhia = (
        Decimal(config.employee_health or 0) / Decimal("12")
    ).quantize(CENTS)
    employee_water = Decimal(config.water_rate or 0).quantize(CENTS)
    net_pay = (
        gross
        - employee_paye
        - employee_pension
        - employee_nhf
        - employee_nhia
        - employee_water
    ).quantize(CENTS)
    employer_pension = (
        Decimal(config.pension_employer or 0) / Decimal("12")
    ).quantize(CENTS)
    employer_nhia = (
        Decimal(config.emplyr_health or 0) / Decimal("12")
    ).quantize(CENTS)
    employer_nsitf = Decimal(config.nsitf or 0).quantize(CENTS)
    employer_itf = (Decimal(config.itf or 0) / Decimal("12")).quantize(CENTS)
    employer_cost = (
        gross + employer_pension + employer_nhia + employer_nsitf + employer_itf
    ).quantize(CENTS)
    return {
        "gross": gross,
        "employee_paye": employee_paye,
        "employee_pension": employee_pension,
        "employee_nhf": employee_nhf,
        "employee_nhia": employee_nhia,
        "employee_water": employee_water,
        "net_pay": net_pay,
        "employer_pension": employer_pension,
        "employer_nhia": employer_nhia,
        "employer_nsitf": employer_nsitf,
        "employer_itf": employer_itf,
        "employer_cost": employer_cost,
    }


class NetPayFixtureBase(TestCase):
    """Lightweight employee + pay-config + entry stack, no ledger setup."""

    def setUp(self):
        self.company = Company.objects.create(name="Net Pay Parity Co")
        user = get_user_model().objects.create_user(
            email="parity@example.com",
            password="password123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )
        # EmployeeProfile is auto-created by the CustomUser post_save signal.
        self.employee = EmployeeProfile.objects.get(user=user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save()

    def _attach_config(self, basic_salary, **overrides):
        config = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal(basic_salary),
            **overrides,
        )
        self.employee.employee_pay = config
        self.employee.save()
        self.employee.refresh_from_db()
        return config

    @staticmethod
    def _first_of_month():
        return date.today().replace(day=1)

    def _run_entry(self, name):
        run = PayrollRun.objects.create(
            company=self.company,
            name=name,
            paydays=self._first_of_month(),
            is_active=True,
        )
        entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee, status="active"
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        return run, entry


class CanonicalCalculatorUnitTests(TestCase):
    """Direct unit behaviour of the three payroll_calc entry points."""

    def test_annual_to_monthly_divides_by_twelve(self):
        self.assertEqual(annual_to_monthly(Decimal("864000")), Decimal("72000"))

    def test_annual_to_monthly_handles_none_and_zero(self):
        self.assertEqual(annual_to_monthly(None), Decimal(0))
        self.assertEqual(annual_to_monthly(0), Decimal(0))

    def test_monthly_net_pay_matches_canonical_rule(self):
        result = monthly_net_pay(
            gross_annual=Decimal("864000"),
            employee_health_annual=Decimal("120000"),
            nhf_annual=Decimal("36000"),
            payee_monthly=Decimal("6560"),
            water_monthly=Decimal("200"),
        )
        # 72000 - 10000 - 3000 - 6560 - 200
        self.assertEqual(result["net"], Decimal("52240"))

    def test_monthly_net_pay_includes_allowances_and_deductions(self):
        result = monthly_net_pay(
            gross_annual=Decimal("600000"),
            allowances_monthly=Decimal("1500"),
            deductions_monthly=Decimal("300"),
        )
        # 50000 + 1500 - 300
        self.assertEqual(result["net"], Decimal("51200"))

    def test_entry_net_pay_composes_stored_net_with_adjustments(self):
        self.assertEqual(
            entry_net_pay(
                Decimal("52240"),
                allowances_monthly=Decimal("1500"),
                deductions_monthly=Decimal("300"),
            ),
            Decimal("53440"),
        )


class GetNetPayParityTests(NetPayFixtureBase):
    """``utils.get_net_pay`` is behaviour-identical to its legacy formula."""

    def test_get_net_pay_matches_legacy_formula(self):
        config = self._attach_config("120000.00")
        self.assertEqual(utils.get_net_pay(self.employee), _legacy_get_net_pay(config))

    def test_get_net_pay_falls_back_to_computed_gross_when_unset(self):
        # A config with no stored annual gross forces get_net_pay down the
        # ``gross_income(config)`` fallback path; delegation must still hold.
        config = self._attach_config("75000.00")
        Payroll.objects.filter(pk=config.pk).update(gross_income=0)
        config.refresh_from_db()
        expected = monthly_net_pay(
            gross_annual=utils.gross_income(config),
            employee_health_annual=config.employee_health,
            nhf_annual=config.nhf,
            payee_monthly=config.payee,
            water_monthly=config.water_rate,
        )["net"]
        self.assertEqual(utils.get_net_pay(self.employee), expected)

    def test_get_net_pay_without_config_returns_zero(self):
        self.assertEqual(utils.get_net_pay(self.employee), Decimal(0.0))

    def test_get_net_pay_matches_canonical_monthly_net_pay(self):
        config = self._attach_config("200000.00")
        expected = monthly_net_pay(
            gross_annual=config.gross_income,
            employee_health_annual=config.employee_health,
            nhf_annual=config.nhf,
            payee_monthly=config.payee,
            water_monthly=config.water_rate,
        )["net"]
        self.assertEqual(utils.get_net_pay(self.employee), expected)


class MonthlyCostBreakdownParityTests(NetPayFixtureBase):
    """``utils.monthly_cost_breakdown`` is behaviour-identical to its legacy."""

    def _assert_parity(self, basic_salary):
        config = self._attach_config(basic_salary)
        self.assertEqual(
            utils.monthly_cost_breakdown(config),
            _legacy_monthly_cost_breakdown(config),
        )

    def test_cost_breakdown_parity_for_typical_salary(self):
        self._assert_parity("120000.00")

    def test_cost_breakdown_parity_for_low_salary(self):
        self._assert_parity("30000.00")

    def test_cost_breakdown_parity_for_high_salary(self):
        self._assert_parity("850000.00")

    def test_net_pay_row_is_gross_less_all_employee_lines(self):
        self._attach_config("120000.00")
        values = utils.monthly_cost_breakdown(self.employee.employee_pay)
        self.assertEqual(
            values["net_pay"],
            (
                values["gross"]
                - values["employee_paye"]
                - values["employee_pension"]
                - values["employee_nhf"]
                - values["employee_nhia"]
                - values["employee_water"]
            ),
        )

    def test_employer_cost_is_gross_plus_employer_levies(self):
        self._attach_config("120000.00")
        values = utils.monthly_cost_breakdown(self.employee.employee_pay)
        self.assertEqual(
            values["employer_cost"],
            (
                values["gross"]
                + values["employer_pension"]
                + values["employer_nhia"]
                + values["employer_nsitf"]
                + values["employer_itf"]
            ),
        )


class PensionDiscrepancyDocumentationTests(NetPayFixtureBase):
    """Pin the known ``pension/12`` divergence between the two views.

    ``utils.get_net_pay`` (payslip/net-pay path) does NOT subtract employee
    pension; ``utils.monthly_cost_breakdown`` (employer-cost report) DOES. This
    is pre-existing, load-bearing behaviour shared by the accounting postings
    and the Cost of Employment report, so this refactor preserves it and pins
    it here rather than silently changing money semantics.
    """

    def test_cost_breakdown_net_is_lower_than_get_net_pay_by_pension(self):
        config = self._attach_config("120000.00")
        breakdown_net = utils.monthly_cost_breakdown(config)["net_pay"]
        payslip_net = utils.get_net_pay(self.employee)
        expected_gap = (config.pension_employee / Decimal("12")).quantize(CENTS)
        self.assertEqual(breakdown_net, payslip_net - expected_gap)


class PayrollEntryNetPayParityTests(NetPayFixtureBase):
    """``PayrollEntry.get_netpay`` composes stored net + allow - deduct."""

    def test_entry_netpay_without_run_is_base_net(self):
        self._attach_config("120000.00")
        entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee, status="active"
        )
        # No PayrollRunEntry yet -> allowances/deductions are zero.
        self.assertEqual(entry.get_netpay, entry_net_pay(self.employee.net_pay))

    def test_entry_netpay_subtracts_standard_deduction(self):
        self._attach_config("120000.00")
        _, entry = self._run_entry("Parity run")
        Deduction.objects.create(
            employee=self.employee,
            deduction_type="OTHER",
            amount=Decimal("1500.00"),
        )
        entry = PayrollEntry.objects.get(pk=entry.pk)
        self.assertEqual(
            entry.get_netpay,
            entry_net_pay(self.employee.net_pay, deductions_monthly=Decimal("1500.00")),
        )


class StoredNetPayStaysConsistentTests(NetPayFixtureBase):
    """Save-path netpay equals the canonical composition (no drift)."""

    def test_saved_entry_netpay_matches_canonical_composition(self):
        self._attach_config("90000.00")
        _, entry = self._run_entry("Save consistency run")
        entry = PayrollEntry.objects.get(pk=entry.pk)
        entry.save()  # save() recomputes and stores netpay
        entry.refresh_from_db()
        self.assertEqual(
            Decimal(entry.netpay),
            entry_net_pay(
                self.employee.net_pay,
                allowances_monthly=entry.calc_allowance,
                deductions_monthly=entry.calc_deduction,
            ),
        )
