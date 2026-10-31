"""Worked-example tests for the stored-unit convention on ``Payroll``.

Convention (see ``Payroll`` docstring): every stored statutory amount is
ANNUAL, except ``payee`` and ``water_rate`` which are MONTHLY.

Worked example: ₦500,000 monthly gross, default 40/10/10 split, NHF voluntary
with the employee's consent,
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
from django.utils import timezone

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
        self.employee.nhf_consent_at = timezone.now()
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



class PayrollEntrySnapshotTests(WorkedExampleFixture):
    """A run's figures are frozen on its entries when net pay is calculated."""

    def setUp(self):
        super().setUp()
        self.run = PayrollRun.objects.create(
            company=self.company, name="Oct", paydays=date(2026, 10, 1), is_active=True
        )
        self.entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee, status="active"
        )
        PayrollRunEntry.objects.create(payroll_run=self.run, payroll_entry=self.entry)
        self.entry.save()

    def _raise_salary(self):
        from payroll.financial_approval_actions import change_salary
        from tests.approval_helpers import approved_operation_for

        approved_operation_for("payroll.change_payroll")(
            change_salary, employee=self.employee, basic_salary=Decimal("800000.00")
        )

    def test_entry_captures_monthly_figures(self):
        figures = self.entry.figures
        self.assertEqual(figures["gross"], Decimal("500000.00"))
        self.assertEqual(figures["employee_paye"], Decimal("65480.00"))
        self.assertEqual(figures["pension_total"], Decimal("54000.00"))

    def test_later_salary_change_does_not_rewrite_the_run(self):
        self._raise_salary()

        entry = PayrollEntry.all_objects.get(pk=self.entry.pk)
        self.assertEqual(entry.figures["gross"], Decimal("500000.00"))
        self.assertEqual(period_remittance_amounts(self.company, self.run)["paye"], Decimal("65480.00"))

    def test_recalculating_an_unlocked_run_refreshes_the_figures(self):
        self._raise_salary()

        entry = PayrollEntry.all_objects.get(pk=self.entry.pk)
        entry.save()
        self.assertEqual(entry.figures["gross"], Decimal("800000.00"))

    def test_entries_without_a_snapshot_fall_back_to_the_live_config(self):
        PayrollEntry.all_objects.filter(pk=self.entry.pk).update(statutory_snapshot={})

        entry = PayrollEntry.all_objects.get(pk=self.entry.pk)
        self.assertEqual(entry.figures["gross"], Decimal("500000.00"))


class NhfConsentTests(WorkedExampleFixture):
    """Voluntary NHF needs the employee's consent; compulsory NHF does not."""

    def test_voluntary_nhf_is_not_deducted_without_consent(self):
        self.employee.nhf_consent_at = None
        self.employee.save()
        self.config.refresh_from_db()

        self.assertEqual(self.config.nhf, Decimal("0.00"))

    def test_voluntary_nhf_is_deducted_with_consent(self):
        self.assertEqual(self.config.nhf, Decimal("60000.00"))

    def test_compulsory_nhf_is_deducted_without_consent(self):
        from payroll.financial_approval_actions import change_salary
        from tests.approval_helpers import approved_operation_for

        self.employee.nhf_consent_at = None
        self.employee.save()
        approved_operation_for("payroll.change_payroll")(
            change_salary,
            employee=self.employee,
            basic_salary=self.config.basic_salary,
            salary_options={"nhf_scheme": "compulsory"},
        )
        self.employee.refresh_from_db()

        self.assertEqual(self.employee.employee_pay.nhf, Decimal("60000.00"))


class RentDeclarationTests(WorkedExampleFixture):
    """Rent relief applies only once HR approves a declaration with proof.

    Approved rent 3,000,000 -> relief min(600,000, 500,000) = 500,000;
    taxable 5,532,000 - 500,000 = 5,032,000;
    PAYE = 330,000 + 18% x 2,032,000 = 695,760 a year = 57,980 a month.
    """

    def setUp(self):
        super().setUp()
        from payroll.models import RentDeclaration

        self.hr = get_user_model().objects.create_user(
            email="hr-units@example.com",
            password="password123",
            first_name="Hr",
            last_name="Units",
            company=self.company,
            active_company=self.company,
        )
        self.declaration = RentDeclaration.objects.create(
            company=self.company,
            employee=self.employee,
            tax_year=timezone.localdate().year,
            annual_rent=Decimal("3000000.00"),
        )

    def _review(self, reviewer, approve=True, note=""):
        from payroll.services.rent_relief import review_declaration

        return review_declaration(
            declaration=self.declaration, reviewer=reviewer, approve=approve, note=note
        )

    def test_pending_declaration_gives_no_relief(self):
        self.assertEqual(self.employee.rent_relief_amount, Decimal("0.00"))
        self.assertEqual(self.config.payee, Decimal("65480.00"))

    def test_approval_applies_capped_relief_to_paye(self):
        self._review(self.hr)

        self.config.refresh_from_db()
        self.assertEqual(self.employee.rent_relief_amount, Decimal("500000.00"))
        self.assertEqual(self.config.taxable_income, Decimal("5032000.00"))
        self.assertEqual(self.config.payee, Decimal("57980.00"))

    def test_employee_cannot_review_own_declaration(self):
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            self._review(self.employee.user)

    def test_rejection_needs_a_reason_and_gives_no_relief(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self._review(self.hr, approve=False)
        self._review(self.hr, approve=False, note="Receipt is for 2024")
        self.assertEqual(self.employee.rent_relief_amount, Decimal("0.00"))

    def test_employee_submits_declaration_with_proof(self):
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from django.urls import reverse

        media_root = tempfile.TemporaryDirectory()
        self.addCleanup(media_root.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media_root.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.declaration.delete()
        self.client.login(email="units@example.com", password="password123")
        response = self.client.post(
            reverse("payroll:my_rent_declarations"),
            {
                "tax_year": timezone.localdate().year,
                "annual_rent": "1200000",
                "document": SimpleUploadedFile("receipt.pdf", b"%PDF-1.4", "application/pdf"),
            },
        )

        self.assertEqual(response.status_code, 302)
        declaration = self.employee.rent_declarations.get()
        self.assertEqual(declaration.status, "pending")
        self.assertEqual(declaration.annual_rent, Decimal("1200000.00"))

    def test_hr_review_page_needs_permission(self):
        from django.urls import reverse

        self.client.login(email="hr-units@example.com", password="password123")
        response = self.client.get(reverse("payroll:rent_declaration_review"))
        self.assertEqual(response.status_code, 403)
