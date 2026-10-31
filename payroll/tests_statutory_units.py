"""Worked-example tests for the stored-unit convention on ``Payroll``.

Convention (see ``Payroll`` docstring): every stored statutory amount is
ANNUAL, except ``payee`` and ``water_rate`` which are MONTHLY.

Worked example: ₦500,000 monthly gross, default 40/10/10 split, NHF voluntary,
NHIA on (statutory basic basis 5%/10%), no rent declared, NTA 2025 bands.

  annual gross            6,000,000
  basic / housing / transport  2,400,000 / 600,000 / 600,000 (BHT 3,600,000)
  pension employee 8% BHT   288,000   employer 10% BHT  360,000
  NHF 2.5% basic             60,000
  NHIA 5% / 10% monthly basic (200,000) -> 10,000 / 20,000 a month
                            120,000 / 240,000 a year
  NSITF 1% gross             60,000
  taxable = 6,000,000 - 288,000 - 60,000 - 120,000 = 5,532,000
  PAYE = 15% x 2,200,000 + 18% x 2,532,000 = 785,760 a year = 65,480 a month
  net = 500,000 - 24,000 - 5,000 - 10,000 - 65,480 - 200 = 395,320
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from company.models import Company
from payroll import utils
from payroll.models import EmployeeProfile, Payroll, PayrollEntry, PayrollRun, PayrollRunEntry
from payroll.services.compliance import period_remittance_amounts
from payroll.services.retro_pay_service import monthly_net_for

CENTS = Decimal("0.01")


class WorkedExampleFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Units Co")
        user = get_user_model().objects.create_user(
            email="units@example.com",
            password="password123",
            first_name="Chi",
            last_name="Obi",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save()
        self.config = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("500000.00"),
            nhf_scheme="voluntary",
            is_nhif=True,
        )
        self.employee.employee_pay = self.config
        self.employee.save()
        self.employee.refresh_from_db()
        self.config.refresh_from_db()


class StatutoryUnitsWorkedExampleTests(WorkedExampleFixture):
    def test_stored_figures_are_annual(self):
        c = self.config
        self.assertEqual(c.gross_income, Decimal("6000000.00"))
        self.assertEqual(c.bht, Decimal("3600000.00"))
        self.assertEqual(c.pension_employee, Decimal("288000.00"))
        self.assertEqual(c.pension_employer, Decimal("360000.00"))
        self.assertEqual(c.nhf, Decimal("60000.00"))
        self.assertEqual(c.employee_health, Decimal("120000.00"))
        self.assertEqual(c.emplyr_health, Decimal("240000.00"))
        self.assertEqual(c.nhif, Decimal("360000.00"))
        self.assertEqual(c.nsitf, Decimal("60000.00"))

    def test_paye_uses_all_reliefs_in_annual_units(self):
        self.assertEqual(self.config.taxable_income, Decimal("5532000.00"))
        self.assertEqual(self.config.payee, Decimal("65480.00"))

    def test_net_pay_is_full_gross_less_all_employee_deductions(self):
        self.assertEqual(self.employee.net_pay, Decimal("395320.00"))
        self.assertEqual(utils.get_net_pay(self.employee).quantize(CENTS), Decimal("395320.00"))

    def test_cost_breakdown_agrees_with_payslip_net(self):
        breakdown = utils.monthly_cost_breakdown(self.config)
        self.assertEqual(breakdown["gross"], Decimal("500000.00"))
        self.assertEqual(breakdown["employee_pension"], Decimal("24000.00"))
        self.assertEqual(breakdown["employee_nhia"], Decimal("10000.00"))
        self.assertEqual(breakdown["employer_nsitf"], Decimal("5000.00"))
        self.assertEqual(breakdown["net_pay"], self.employee.net_pay)

    def test_retro_pay_net_matches_payslip_net(self):
        self.assertEqual(monthly_net_for(self.config).quantize(CENTS), Decimal("395320.00"))

    def test_compliance_remittances_are_monthly(self):
        run = PayrollRun.objects.create(
            company=self.company, name="Oct", paydays=date(2026, 10, 1), is_active=True
        )
        entry = PayrollEntry.objects.create(company=self.company, pays=self.employee, status="active")
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)

        amounts = period_remittance_amounts(self.company, run)

        self.assertEqual(amounts["paye"], Decimal("65480.00"))
        self.assertEqual(amounts["pension"], Decimal("54000.00"))
        self.assertEqual(amounts["nhf"], Decimal("5000.00"))
        self.assertEqual(amounts["nhia"], Decimal("30000.00"))
        self.assertEqual(amounts["nsitf"], Decimal("5000.00"))


class RecomputePayrollFiguresTests(WorkedExampleFixture):
    def _store_legacy_figures(self):
        # Pre-fix rows held NHIA and NSITF monthly and net pay without pension.
        Payroll.all_objects.filter(pk=self.config.pk).update(
            employee_health=Decimal("25000.00"), nsitf=Decimal("5000.00")
        )
        EmployeeProfile.objects.filter(pk=self.employee.pk).update(net_pay=Decimal("228691.67"))

    def test_dry_run_reports_but_does_not_persist(self):
        from payroll.services.payroll_recompute import recompute_payroll_figures

        self._store_legacy_figures()
        result = recompute_payroll_figures(apply=False)

        self.assertEqual(result, {"configs": 1, "profiles": 1, "applied": False})
        self.config.refresh_from_db()
        self.assertEqual(self.config.employee_health, Decimal("25000.00"))

    def test_apply_restores_annual_figures_and_net_pay(self):
        from payroll.services.payroll_recompute import recompute_payroll_figures

        self._store_legacy_figures()
        result = recompute_payroll_figures(apply=True)

        self.assertEqual(result, {"configs": 1, "profiles": 1, "applied": True})
        self.config.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertEqual(self.config.employee_health, Decimal("120000.00"))
        self.assertEqual(self.config.nsitf, Decimal("60000.00"))
        self.assertEqual(self.employee.net_pay, Decimal("395320.00"))
