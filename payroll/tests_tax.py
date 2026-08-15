from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from company.models import Company
from django.contrib.auth import get_user_model
from django.urls import reverse
from payroll import utils
from payroll.models import (
    CompanyPayrollSetting,
    EmployeeProfile,
    Payroll,
    PayrollRun,
    PayrollEntry,
    PayrollRunEntry,
    PublicHoliday,
    RemittanceRecord,
)
from payroll.services import compliance


class DummyPayroll:
    class _ProfileSet:
        def __init__(self, profile):
            self._profile = profile

        def first(self):
            return self._profile

    class _EmployeeProfile:
        def __init__(self, rent_relief_amount: Decimal):
            self.rent_relief_amount = rent_relief_amount

    def __init__(
        self,
        basic_salary: Decimal,
        annual_gross: Decimal,
        is_nhif: bool = True,
        pk: int | None = 1,
        pension_employee: Decimal = Decimal("0.00"),
        nhf: Decimal = Decimal("0.00"),
        employee_health: Decimal = Decimal("0.00"),
        rent_relief: Decimal = Decimal("0.00"),
    ):
        self.pk = pk
        self.basic_salary = basic_salary
        self.is_nhif = is_nhif
        self.get_annual_gross = annual_gross
        self.get_gross_income = annual_gross
        self.pension_employee = pension_employee
        self.nhf = nhf
        self.employee_health = employee_health
        profile = self._EmployeeProfile(rent_relief_amount=rent_relief)
        self.employee_pay = self._ProfileSet(profile)


class NigeriaTaxComputationTests(TestCase):
    def test_compute_annual_paye_first_800k_is_tax_free(self):
        self.assertEqual(utils.compute_annual_paye(Decimal("800000")), Decimal("0"))

    def test_compute_annual_paye_taxes_only_amount_above_800k(self):
        self.assertEqual(utils.compute_annual_paye(Decimal("900000")), Decimal("15000"))

    def test_compute_annual_paye_uses_new_progressive_bands(self):
        annual_tax = utils.compute_annual_paye(Decimal("3000000"))
        self.assertEqual(annual_tax, Decimal("330000"))

    def test_minimum_wage_earner_is_paye_exempt(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("70000"),
            annual_gross=Decimal("840000"),
        )
        self.assertEqual(utils.get_payee(payroll), Decimal("0.0"))

    def test_taxable_income_includes_pension_nhf_health_and_rent_relief(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("1000000"),
            annual_gross=Decimal("12000000"),
            pension_employee=Decimal("960000"),
            nhf=Decimal("300000"),
            employee_health=Decimal("210000"),
            rent_relief=Decimal("500000"),
        )
        self.assertEqual(utils.calculate_taxable_income(payroll), Decimal("10030000"))

    def test_taxable_income_excludes_rent_relief_when_payroll_not_persisted(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("1000000"),
            annual_gross=Decimal("12000000"),
            pk=None,
            pension_employee=Decimal("960000"),
            nhf=Decimal("300000"),
            employee_health=Decimal("210000"),
            rent_relief=Decimal("500000"),
        )
        self.assertEqual(utils.calculate_taxable_income(payroll), Decimal("10530000"))

    def test_nhif_defaults_to_statutory_5_10_split_on_basic(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("400000"),
            annual_gross=Decimal("4800000"),
        )
        self.assertEqual(utils.calc_employee_health_contrib(payroll), Decimal("20000"))
        self.assertEqual(utils.calc_employer_health_contrib(payroll), Decimal("40000"))
        self.assertEqual(utils.calc_health_contrib(payroll), Decimal("60000"))

    def test_nhif_statutory_5_10_applies_at_all_salary_levels(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("999999"),
            annual_gross=Decimal("11999988"),
        )
        self.assertEqual(
            utils.calc_employee_health_contrib(payroll), Decimal("49999.95")
        )
        self.assertEqual(
            utils.calc_employer_health_contrib(payroll), Decimal("99999.9")
        )
        self.assertEqual(utils.calc_health_contrib(payroll), Decimal("149999.85"))

        high_payroll = DummyPayroll(
            basic_salary=Decimal("1000000"),
            annual_gross=Decimal("12000000"),
        )
        self.assertEqual(
            utils.calc_employee_health_contrib(high_payroll), Decimal("50000")
        )
        self.assertEqual(
            utils.calc_employer_health_contrib(high_payroll), Decimal("100000")
        )

    def test_nhif_disabled_returns_zero_for_all_health_contributions(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("1000000"),
            annual_gross=Decimal("12000000"),
            is_nhif=False,
        )
        self.assertEqual(utils.calc_employee_health_contrib(payroll), Decimal("0.0"))
        self.assertEqual(utils.calc_employer_health_contrib(payroll), Decimal("0.0"))
        self.assertEqual(utils.calc_health_contrib(payroll), Decimal("0.0"))


class StatutoryRateVersionTests(TestCase):
    """Effective-dated statutory rates resolve by the pay period's date."""

    def setUp(self):
        # The version list is cached briefly; keep tests independent of order.
        cache.delete(utils._STATUTORY_VERSIONS_CACHE_KEY)

    def test_seeded_versions_exist(self):
        from payroll.models import StatutoryRateVersion

        self.assertGreaterEqual(StatutoryRateVersion.objects.count(), 3)

    def test_paye_bands_resolve_by_effective_date(self):
        # Pre-NTA run (2025) uses the PITA bands: 7%-24% from NGN 300,000.
        pita_tax = utils.compute_annual_paye(Decimal("3000000"), as_of=date(2025, 6, 1))
        self.assertEqual(pita_tax, Decimal("518000"))
        # NTA run (2026): 0% on the first NGN 800,000, 15% on the next 2.2m.
        nta_tax = utils.compute_annual_paye(Decimal("3000000"), as_of=date(2026, 6, 1))
        self.assertEqual(nta_tax, Decimal("330000"))

    def test_get_paye_bands_pre_nta(self):
        bands = utils.get_paye_bands(as_of=date(2025, 12, 31))
        self.assertEqual(bands[0], (Decimal("300000"), Decimal("7")))
        self.assertEqual(bands[-1], (None, Decimal("24")))

    def test_get_paye_bands_nta_2025(self):
        bands = utils.get_paye_bands(as_of=date(2026, 1, 1))
        self.assertEqual(bands[0], (Decimal("800000"), Decimal("0")))
        self.assertEqual(bands[-1], (None, Decimal("25")))

    def test_minimum_wage_exemption_is_date_aware(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("50000"),
            annual_gross=Decimal("600000"),
        )
        # Pre-2024 minimum wage was NGN 30,000: 50,000 is taxable under PITA.
        # 600,000 @ PITA bands = 21,000 + 33,000 = 54,000/yr => 4,500/mo.
        self.assertEqual(
            utils.get_payee(payroll, as_of=date(2022, 6, 1)), Decimal("4500")
        )
        # From 29 Jul 2024 the minimum wage is NGN 70,000: 50,000 is exempt.
        self.assertEqual(
            utils.get_payee(payroll, as_of=date(2024, 8, 1)), Decimal("0.0")
        )

    def test_pension_and_nhf_rates_resolve_from_version_without_company_override(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("100000"),
            annual_gross=Decimal("1200000"),
        )
        # No CompanyPayrollSetting -> statutory version percentages (8/10, 2.5).
        self.assertEqual(
            utils.get_pension_employee(payroll, as_of=date(2025, 6, 1)),
            Decimal("96000"),
        )
        self.assertEqual(
            utils.get_pension_employee(payroll, as_of=date(2026, 6, 1)),
            Decimal("96000"),
        )
        self.assertEqual(
            utils.get_pension_employer(payroll, as_of=date(2026, 6, 1)),
            Decimal("120000"),
        )


class NhisEngineTests(TestCase):
    """NHIA/NHIS engine: statutory basis selection and HMO premium override."""

    def setUp(self):
        self.company = Company.objects.create(name="Health Co")
        self.setting = CompanyPayrollSetting.objects.create(company=self.company)

    def _make_payroll(self, basic_salary: Decimal):
        from payroll.models import Payroll

        payroll = Payroll(
            company=self.company,
            basic_salary=basic_salary,
            is_nhif=True,
        )
        payroll.save()
        return Payroll.objects.get(pk=payroll.pk)

    def test_consolidated_basis_uses_1_75_3_25_of_monthly_consolidated(self):
        self.setting.health_basis = "consolidated"
        self.setting.save(update_fields=["health_basis"])

        payroll = self._make_payroll(Decimal("400000"))
        monthly_consolidated = payroll.gross_income / Decimal("12")
        expected_employee = (monthly_consolidated * Decimal("1.75")) / Decimal("100")
        expected_employer = (monthly_consolidated * Decimal("3.25")) / Decimal("100")

        self.assertEqual(
            payroll.employee_health, expected_employee.quantize(Decimal("0.01"))
        )
        self.assertEqual(
            payroll.emplyr_health, expected_employer.quantize(Decimal("0.01"))
        )

    def test_hmo_premium_override_employer_tops_up_to_premium(self):
        self.setting.hmo_monthly_premium = Decimal("50000")
        self.setting.save(update_fields=["hmo_monthly_premium"])

        payroll = self._make_payroll(Decimal("400000"))
        # Employee keeps the statutory 5% of basic (20,000); the employer
        # pays the negotiated premium minus the employee share.
        self.assertEqual(payroll.employee_health, Decimal("20000.00"))
        self.assertEqual(payroll.emplyr_health, Decimal("30000.00"))
        self.assertEqual(payroll.nhif, Decimal("50000.00"))

    def test_configured_health_tier_still_overrides_statutory_split(self):
        from payroll.models import CompanyHealthInsuranceTier

        CompanyHealthInsuranceTier.objects.create(
            setting=self.setting,
            min_salary=Decimal("0"),
            max_salary=None,
            employee_percentage=Decimal("3"),
            employer_percentage=Decimal("7"),
            sort_order=1,
        )

        payroll = self._make_payroll(Decimal("400000"))
        self.assertEqual(payroll.employee_health, Decimal("12000.00"))
        self.assertEqual(payroll.emplyr_health, Decimal("28000.00"))

    def test_health_contribution_summary_reflects_mode(self):
        summary = utils.health_contribution_summary(self._make_payroll(Decimal("400000")))
        self.assertEqual(summary["basis"], "basic")
        self.assertEqual(summary["employee_percentage"], Decimal("5"))
        self.assertIn("employee 5% / employer 10%", summary["label"])

        self.setting.health_basis = "consolidated"
        self.setting.save(update_fields=["health_basis"])
        summary = utils.health_contribution_summary(self._make_payroll(Decimal("400000")))
        self.assertIn("1.75% / employer 3.25%", summary["label"])


class StatutorySchemeFlagTests(TestCase):
    """Per-employee NHF scheme and company-level ITF/NSITF applicability flags."""

    def setUp(self):
        self.company = Company.objects.create(name="Flags Co")
        self.setting = CompanyPayrollSetting.objects.create(company=self.company)

    def _make_payroll(self, basic_salary: Decimal, **kwargs):
        payroll = Payroll(company=self.company, basic_salary=basic_salary, **kwargs)
        payroll.save()
        return Payroll.objects.get(pk=payroll.pk)

    def test_nhf_scheme_compulsory_deducts_without_is_housing(self):
        payroll = self._make_payroll(Decimal("200000"), nhf_scheme="compulsory")
        self.assertTrue(payroll.is_housing)  # synced by save()
        self.assertGreater(payroll.nhf, 0)

    def test_legacy_is_housing_is_preserved_as_voluntary(self):
        payroll = self._make_payroll(Decimal("200000"), is_housing=True)
        self.assertEqual(payroll.nhf_scheme, "voluntary")
        self.assertGreater(payroll.nhf, 0)

    def test_nhf_scheme_none_means_no_nhf(self):
        payroll = self._make_payroll(Decimal("200000"))
        self.assertEqual(payroll.nhf, Decimal("0.00"))

    def test_itf_gated_by_company_applicability(self):
        payroll = self._make_payroll(Decimal("200000"))
        self.assertEqual(payroll.itf, Decimal("0.00"))

        self.setting.itf_applicable = True
        self.setting.save(update_fields=["itf_applicable"])
        payroll = self._make_payroll(Decimal("200000"))
        self.assertEqual(payroll.itf, payroll.gross_income / Decimal("100"))

    def test_nsitf_gated_by_company_applicability(self):
        self.setting.nsitf_applicable = False
        self.setting.save(update_fields=["nsitf_applicable"])
        payroll = self._make_payroll(Decimal("200000"))
        self.assertEqual(payroll.nsitf, Decimal("0.00"))


class CostOfEmploymentReportTests(TestCase):
    """The cost-of-employment report surfaces the employer-vs-employee split."""

    def setUp(self):
        self.company = Company.objects.create(name="Cost Co")
        self.user = get_user_model().objects.create_user(
            email="cost-admin@example.com",
            password="testpass123",
            first_name="Cost",
            last_name="Admin",
            company=self.company,
            active_company=self.company,
            is_staff=True,
            is_superuser=True,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])

        payroll_config = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("120000.00"),
        )
        self.employee.employee_pay = payroll_config
        self.employee.save(update_fields=["employee_pay"])

        self.payroll_run = PayrollRun.objects.create(
            company=self.company,
            name="Cost June 2026",
            paydays=date(2026, 6, 1),
            is_active=True,
        )
        payroll_entry = PayrollEntry.objects.create(
            company=self.company,
            pays=self.employee,
            status="active",
        )
        PayrollRunEntry.objects.create(
            payroll_run=self.payroll_run,
            payroll_entry=payroll_entry,
        )
        self.client.login(email=self.user.email, password="testpass123")

    def test_cost_of_employment_report_renders_with_splits(self):
        response = self.client.get(
            reverse(
                "payroll:cost_of_employment_report",
                kwargs={"pay_id": self.payroll_run.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Employer Cost")
        self.assertContains(response, "Pension (ER)")

    def test_cost_of_employment_reports_list_renders(self):
        response = self.client.get(reverse("payroll:cost_of_employment"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cost of Employment Reports")

    def test_cost_of_employment_report_download_exports_excel(self):
        response = self.client.get(
            reverse(
                "payroll:cost_of_employment_report_download",
                kwargs={"pay_id": self.payroll_run.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/ms-excel")
        self.assertIn(
            "cost_of_employment_report_202606.xls",
            response["Content-Disposition"],
        )
        body = response.content
        # Header row (EmpNo, ... Employer Cost), the employee's own row, and
        # the totals row are all present in the workbook.
        self.assertIn(b"EmpNo", body)
        self.assertIn(b"Employer Cost", body)
        self.assertIn(b"Total Employer Cost", body)
        self.assertIn(self.employee.emp_id.encode(), body)

    def test_cost_of_employment_report_download_requires_permission(self):
        self.client.logout()
        response = self.client.get(
            reverse(
                "payroll:cost_of_employment_report_download",
                kwargs={"pay_id": self.payroll_run.id},
            )
        )
        # permission_required(raise_exception=True) returns 403 for anonymous.
        self.assertEqual(response.status_code, 403)


class PensionReportMonthlyTests(TestCase):
    """The pension report shows monthly remittance amounts (stored annual ÷ 12)."""

    def setUp(self):
        self.company = Company.objects.create(name="Pension Co")
        self.user = get_user_model().objects.create_user(
            email="pension-admin@example.com",
            password="testpass123",
            first_name="Pension",
            last_name="Admin",
            company=self.company,
            active_company=self.company,
            is_staff=True,
            is_superuser=True,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])
        self.employee.employee_pay = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("120000.00"),
        )
        self.employee.save(update_fields=["employee_pay"])
        self.payroll_run = PayrollRun.objects.create(
            company=self.company,
            name="June 2026 Pension",
            paydays=date(2026, 6, 1),
            is_active=True,
        )
        payroll_entry = PayrollEntry.objects.create(
            company=self.company,
            pays=self.employee,
            status="active",
        )
        PayrollRunEntry.objects.create(
            payroll_run=self.payroll_run,
            payroll_entry=payroll_entry,
        )
        self.client.login(email=self.user.email, password="testpass123")

    def test_pension_report_shows_monthly_amounts(self):
        response = self.client.get(
            reverse("payroll:pensionReport", kwargs={"pay_id": self.payroll_run.id})
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Pension Contribution (Monthly)", content)
        # Stored annual pension is 259,200 (employee 115,200 + employer
        # 144,000); the monthly remittance is 21,600 with a 9,600 / 12,000
        # employee / employer split.
        self.assertIn("₦21,600.00", content)
        self.assertIn("₦9,600.00 / ₦12,000.00", content)
        # The annual figure must not be shown anywhere on the page.
        self.assertNotIn("₦259,200", content)

    def test_pension_report_download_exports_monthly_amounts(self):
        response = self.client.get(
            reverse(
                "payroll:pensionReportDownload",
                kwargs={"pay_id": self.payroll_run.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/ms-excel")
        self.assertIn(
            "pension_report_202606.xls", response["Content-Disposition"]
        )
        body = response.content
        self.assertIn(b"EmpNo", body)
        self.assertIn(b"Total Pension Contribution", body)
        self.assertIn(self.employee.emp_id.encode(), body)


class ReportListPagePortabilityTests(TestCase):
    """Report period-list pages must work under the SQLite test settings.

    ``DISTINCT ON (paydays)`` is Postgres-only; the portable Python dedupe
    (payroll_runs_distinct_by_period) keeps these pages green on SQLite.
    """

    def setUp(self):
        self.company = Company.objects.create(name="List Co")
        self.user = get_user_model().objects.create_user(
            email="list-admin@example.com",
            password="testpass123",
            first_name="List",
            last_name="Admin",
            company=self.company,
            active_company=self.company,
            is_staff=True,
            is_superuser=True,
        )
        PayrollRun.objects.create(
            company=self.company,
            name="June 2026 Payroll",
            paydays=date(2026, 6, 1),
            is_active=True,
        )
        self.client.login(email=self.user.email, password="testpass123")

    def test_period_list_pages_render_under_sqlite(self):
        for url_name in [
            "payroll:varview",
            "payroll:bank",
            "payroll:nhis",
            "payroll:nhf",
            "payroll:payee",
            "payroll:pension",
            "payroll:cost_of_employment",
        ]:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_period_list_dedupes_repeated_paydays(self):
        # A re-run of the same pay period must appear once in the period list.
        PayrollRun.objects.create(
            company=self.company,
            name="June 2026 Payroll (re-run)",
            slug="pay-period-2026-06-b",
            paydays=date(2026, 6, 1),
            is_active=True,
        )
        response = self.client.get(reverse("payroll:nhis"))
        self.assertEqual(len(response.context["payroll"]), 1)


class ComplianceCalendarTests(TestCase):
    """Statutory compliance calendar: due dates, overdue flags, penalties."""

    def setUp(self):
        self.company = Company.objects.create(name="Compliance Co")
        self.user = get_user_model().objects.create_user(
            email="compliance-admin@example.com",
            password="testpass123",
            first_name="Compliance",
            last_name="Admin",
            company=self.company,
            active_company=self.company,
            is_staff=True,
            is_superuser=True,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])

        payroll_config = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("120000.00"),
        )
        self.employee.employee_pay = payroll_config
        self.employee.save(update_fields=["employee_pay"])

        self.payroll_run = PayrollRun.objects.create(
            company=self.company,
            name="June 2026 Payroll",
            paydays=date(2026, 6, 1),
            is_active=True,
        )
        payroll_entry = PayrollEntry.objects.create(
            company=self.company,
            pays=self.employee,
            status="active",
        )
        PayrollRunEntry.objects.create(
            payroll_run=self.payroll_run,
            payroll_entry=payroll_entry,
        )
        self.client.login(email=self.user.email, password="testpass123")

    # --- pure due-date math ------------------------------------------------

    def test_paye_due_date_is_10th_of_following_month(self):
        self.assertEqual(compliance.paye_due_date(date(2026, 6, 1)), date(2026, 7, 10))
        self.assertEqual(compliance.paye_due_date(date(2026, 12, 1)), date(2027, 1, 10))

    def test_annual_paye_return_due_31_jan(self):
        self.assertEqual(compliance.annual_paye_return_due(2026), date(2027, 1, 31))

    def test_nsitf_due_date_is_last_day_of_month(self):
        self.assertEqual(compliance.nsitf_due_date(date(2026, 6, 1)), date(2026, 6, 30))
        self.assertEqual(compliance.nsitf_due_date(date(2026, 12, 1)), date(2026, 12, 31))
        self.assertEqual(compliance.nsitf_due_date(date(2027, 2, 1)), date(2027, 2, 28))

    def test_itf_due_date_is_1_april(self):
        self.assertEqual(compliance.itf_due_date(2026), date(2027, 4, 1))

    def test_pension_due_date_is_seven_working_days(self):
        # Mon 2026-06-01 + 7 working days = Wed 2026-06-10.
        self.assertEqual(compliance.pension_due_date(date(2026, 6, 1)), date(2026, 6, 10))

    def test_pension_due_date_skips_weekends_and_public_holidays(self):
        # 2026-06-08 (Mon) is a public holiday: due slips to Thu 2026-06-11.
        due = compliance.pension_due_date(
            date(2026, 6, 1), holidays=[date(2026, 6, 8)]
        )
        self.assertEqual(due, date(2026, 6, 11))

    def test_pension_due_anchored_to_run_payment_date(self):
        # When the run tracks the actual payment date, the 7-working-day
        # clock starts from it instead of the period start: paid on Mon
        # 2026-06-15 -> due Wed 2026-06-24.
        self.payroll_run.payment_date = date(2026, 6, 15)
        self.payroll_run.save(update_fields=["payment_date"])
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        pension = next(o for o in obligations if o["key"] == "pension")
        self.assertEqual(pension["due_date"], date(2026, 6, 24))
        self.assertEqual(pension["paid_on"], date(2026, 6, 15))
        # The anchor the clock ran from is surfaced for audit, with no
        # fallback flag when the payment date was recorded.
        self.assertEqual(pension["anchor"], date(2026, 6, 15))
        self.assertFalse(pension["anchor_fallback"])
        # The period-based obligations keep their existing due dates.
        paye = next(o for o in obligations if o["key"] == "paye")
        self.assertEqual(paye["due_date"], date(2026, 7, 10))

    def test_pension_anchor_falls_back_to_period_start(self):
        # No stored payment date -> the clock runs from the period start and
        # the fallback is flagged so the calendar can say so.
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        pension = next(o for o in obligations if o["key"] == "pension")
        self.assertEqual(pension["anchor"], date(2026, 6, 1))
        self.assertTrue(pension["anchor_fallback"])
        self.assertIsNone(pension["paid_on"])

    def test_months_overdue_and_pension_penalty(self):
        due = date(2026, 6, 10)
        self.assertEqual(compliance.months_overdue(due, date(2026, 6, 20)), 1)
        self.assertEqual(compliance.months_overdue(due, date(2026, 8, 15)), 3)
        # 2% per month of the outstanding amount.
        self.assertEqual(
            compliance.pension_penalty(Decimal("1000000"), due, date(2026, 6, 20)),
            Decimal("20000.00"),
        )
        self.assertEqual(
            compliance.pension_penalty(Decimal("1000000"), due, date(2026, 8, 15)),
            Decimal("60000.00"),
        )
        # Not overdue -> no penalty.
        self.assertEqual(
            compliance.pension_penalty(Decimal("1000000"), due, date(2026, 6, 5)),
            Decimal("0.00"),
        )

    # --- per-period amounts -------------------------------------------------

    def test_period_remittance_amounts_are_monthly(self):
        amounts = compliance.period_remittance_amounts(self.company, self.payroll_run)
        # payee = annual PAYE / 12. Taxable income deducts the employee
        # pension (8% x 1,440,000 = 115,200): 1,324,800 @ NTA bands =
        # 78,720/yr -> 6,560/mo. Pension is stored annual, divided by 12.
        # NHF/NHIA absent (no is_housing / is_nhif on the config).
        self.assertEqual(amounts["paye"], Decimal("6560.00"))
        self.assertEqual(amounts["pension"], Decimal("21600.00"))
        self.assertEqual(amounts["nhf"], Decimal("0.00"))
        self.assertEqual(amounts["nhia"], Decimal("0.00"))

    # --- obligation builder -------------------------------------------------

    def test_obligations_include_paye_pension_and_annual_return(self):
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        keys = {o["key"] for o in obligations}
        self.assertIn("paye", keys)
        self.assertIn("pension", keys)
        self.assertIn("paye_annual", keys)
        self.assertNotIn("nhf", keys)
        self.assertNotIn("nhia", keys)

    def test_nhf_obligation_included_when_deduction_exists(self):
        config = self.employee.employee_pay
        config.is_housing = True
        config.save()  # recomputes the stored NHF amount
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        nhf = next(o for o in obligations if o["key"] == "nhf")
        self.assertGreater(nhf["amount"], 0)

    def test_nhia_obligation_included_when_company_applicable(self):
        CompanyPayrollSetting.objects.create(company=self.company, nhia_applicable=True)
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        self.assertIn("nhia", {o["key"] for o in obligations})

    def test_nsitf_obligation_due_last_day_of_month_with_amount(self):
        # NSITF applies by default (ECA 2010): 1% of monthly basic = 1,200
        # for a NGN 120,000 salary, due on the last day of the period month.
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        nsitf = next(o for o in obligations if o["key"] == "nsitf")
        self.assertEqual(nsitf["due_date"], date(2026, 6, 30))
        self.assertEqual(nsitf["amount"], Decimal("1200.00"))

    def test_nsitf_obligation_absent_when_flag_off(self):
        CompanyPayrollSetting.objects.create(
            company=self.company, nsitf_applicable=False
        )
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        self.assertNotIn("nsitf", {o["key"] for o in obligations})

    def test_itf_obligation_appears_when_applicable(self):
        CompanyPayrollSetting.objects.create(company=self.company, itf_applicable=True)
        # Re-save the pay config so the stored ITF levy (1% of annual gross)
        # is recomputed now that the flag is on.
        self.employee.employee_pay.save()
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        itf = next(o for o in obligations if o["key"] == "itf")
        self.assertEqual(itf["due_date"], date(2027, 4, 1))
        self.assertGreater(itf["amount"], 0)
        self.assertEqual(itf["period"], date(2026, 1, 1))

    def test_itf_obligation_absent_by_default(self):
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        self.assertNotIn("itf", {o["key"] for o in obligations})

    def test_overdue_flag_with_penalty_exposure(self):
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 8, 1)
        )
        paye = next(o for o in obligations if o["key"] == "paye")
        self.assertEqual(paye["status"], "overdue")
        self.assertIsNotNone(paye["penalty"])
        self.assertIsNone(paye["penalty"]["amount"])  # state-defined, not computed

        pension = next(o for o in obligations if o["key"] == "pension")
        self.assertEqual(pension["status"], "overdue")
        self.assertEqual(pension["penalty"]["rate"], "2% per month")
        # 21,600 x 2% x 2 months overdue (Jun 10 -> Aug 1 = 52 days -> ceil/30).
        self.assertEqual(pension["penalty"]["amount"], Decimal("864.00"))

    def test_pension_due_date_uses_company_public_holidays(self):
        PublicHoliday.objects.create(
            company=self.company, name="Public Holiday", date=date(2026, 6, 8)
        )
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 6, 5)
        )
        pension = next(o for o in obligations if o["key"] == "pension")
        self.assertEqual(pension["due_date"], date(2026, 6, 11))

    def test_remitted_record_marks_obligation_done(self):
        RemittanceRecord.objects.create(
            company=self.company,
            obligation="paye",
            period=date(2026, 6, 1),
            remitted_on=date(2026, 7, 5),
        )
        obligations = compliance.compliance_obligations(
            self.company, as_of=date(2026, 8, 1)
        )
        paye = next(o for o in obligations if o["key"] == "paye")
        self.assertEqual(paye["status"], "done")

    # --- views -------------------------------------------------------------

    def test_calendar_page_renders(self):
        response = self.client.get(reverse("payroll:compliance_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Statutory Compliance")
        self.assertContains(response, "PAYE")
        self.assertContains(response, "Pension")

    def test_calendar_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("payroll:compliance_calendar"))
        # permission_required(raise_exception=True) returns 403 for anonymous.
        self.assertEqual(response.status_code, 403)

    def test_calendar_page_shows_payment_date_anchor(self):
        self.payroll_run.payment_date = date(2026, 6, 15)
        self.payroll_run.save(update_fields=["payment_date"])
        response = self.client.get(reverse("payroll:compliance_calendar"))
        self.assertEqual(response.status_code, 200)
        # PAYE keeps the "Paid" line; the pension row shows the anchor
        # instead of a duplicate Paid line.
        self.assertContains(response, "Paid 15 Jun 2026")
        self.assertContains(response, "7 working days from 15 Jun 2026")
        self.assertNotContains(response, "period start — payment date not recorded")

    def test_calendar_page_flags_period_start_fallback_anchor(self):
        response = self.client.get(reverse("payroll:compliance_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "7 working days from 01 Jun 2026")
        self.assertContains(
            response, "period start — payment date not recorded"
        )

    def test_calendar_rule_basis_describes_payment_date_anchoring(self):
        # The rule-basis copy must keep describing the payment-date anchor
        # so the UI text can't silently regress to the old "period start,
        # adjust manually" wording that contradicted the code.
        response = self.client.get(reverse("payroll:compliance_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "runs from the run's stored salary payment date"
        )
        self.assertContains(response, "falls back to the period start")
        # The stale pre-anchoring phrasing must never return.
        self.assertNotContains(response, "is the pay period start")
        self.assertNotContains(
            response, "so adjust to the actual salary payment date"
        )

    def test_mark_remittance_view_records_remittance(self):
        response = self.client.post(
            reverse(
                "payroll:mark_remittance",
                kwargs={"obligation": "paye", "period": "2026-06"},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            RemittanceRecord.objects.filter(
                company=self.company,
                obligation="paye",
                period=date(2026, 6, 1),
                remitted_on__isnull=False,
            ).exists()
        )

    def test_mark_remittance_view_unmarks(self):
        RemittanceRecord.objects.create(
            company=self.company,
            obligation="paye",
            period=date(2026, 6, 1),
            remitted_on=date(2026, 7, 5),
        )
        response = self.client.post(
            reverse(
                "payroll:mark_remittance",
                kwargs={"obligation": "paye", "period": "2026-06"},
            ),
            {"unmark": "1"},
        )
        self.assertEqual(response.status_code, 302)
        record = RemittanceRecord.objects.get(
            company=self.company, obligation="paye", period=date(2026, 6, 1)
        )
        self.assertIsNone(record.remitted_on)

    def test_mark_remittance_rejects_unknown_obligation(self):
        response = self.client.post(
            reverse(
                "payroll:mark_remittance",
                kwargs={"obligation": "bogus", "period": "2026-06"},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_mark_remittance_view_records_nsitf(self):
        response = self.client.post(
            reverse(
                "payroll:mark_remittance",
                kwargs={"obligation": "nsitf", "period": "2026-06"},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            RemittanceRecord.objects.filter(
                company=self.company,
                obligation="nsitf",
                period=date(2026, 6, 1),
                remitted_on__isnull=False,
            ).exists()
        )

    # --- per-scheme overdue breakdown --------------------------------------

    def _enable_all_schemes(self):
        """Turn on NHF and NHIA amounts so all five schemes produce rows."""
        config = self.employee.employee_pay
        config.nhf_scheme = "voluntary"
        config.is_nhif = True
        config.save()

    def test_scheme_breakdown_groups_overdue_by_scheme(self):
        self._enable_all_schemes()
        response = self.client.get(reverse("payroll:compliance_calendar"))
        self.assertEqual(response.status_code, 200)
        breakdown = response.context["scheme_breakdown"]
        # Every June obligation (paye/pension/nhf/nhia/nsitf) is overdue by
        # now, so each scheme appears once; the annual return is not yet due.
        self.assertEqual(len(breakdown), 5)
        labels = {row["label"] for row in breakdown}
        self.assertEqual(labels, {"PAYE", "Pension", "NHF", "NHIA", "NSITF"})
        # Counts and amounts roll up to the total overdue stats.
        self.assertEqual(
            sum(row["count"] for row in breakdown),
            response.context["overdue_count"],
        )
        self.assertEqual(
            sum(row["amount"] for row in breakdown),
            response.context["overdue_amount"],
        )

    def test_scheme_breakdown_pension_leads_with_penalty_exposure(self):
        self._enable_all_schemes()
        response = self.client.get(reverse("payroll:compliance_calendar"))
        breakdown = response.context["scheme_breakdown"]
        # Pension is the only scheme with a verified penalty rate, so it must
        # lead the sorted breakdown and carry the exposure amount.
        self.assertEqual(breakdown[0]["key"], "pension")
        pension = breakdown[0]
        self.assertGreater(pension["penalty"], 0)
        self.assertEqual(pension["penalty_rate"], "2% per month")
        self.assertTrue(
            all(row["penalty"] == 0 for row in breakdown[1:]),
            "only pension carries a computed penalty amount",
        )

    def test_scheme_breakdown_paye_includes_annual_return(self):
        # With as_of after the annual-return deadline, PAYE counts both the
        # monthly obligation and the filing under one scheme row.
        summary = compliance.compliance_summary(
            self.company, as_of=date(2027, 3, 1)
        )
        paye = next(
            row for row in summary["scheme_breakdown"] if row["key"] == "paye"
        )
        self.assertEqual(paye["count"], 2)

    def test_scheme_breakdown_clears_when_remitted(self):
        for key in ("paye", "pension", "nhf", "nhia", "nsitf"):
            RemittanceRecord.objects.create(
                company=self.company,
                obligation=key,
                period=date(2026, 6, 1),
                remitted_on=date(2026, 6, 20),
            )
        response = self.client.get(reverse("payroll:compliance_calendar"))
        self.assertEqual(response.context["scheme_breakdown"], [])
        self.assertEqual(response.context["overdue_count"], 0)
        self.assertNotContains(response, "Exposure by scheme")

    def test_calendar_page_renders_scheme_breakdown(self):
        self._enable_all_schemes()
        response = self.client.get(reverse("payroll:compliance_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Exposure by scheme")
        self.assertContains(response, "Pension")
        self.assertContains(response, "2% per month")


class PayrollRecomputeStatutoryTests(TestCase):
    """Retrospective runs recompute against the regime for their pay period."""

    def setUp(self):
        cache.delete(utils._STATUTORY_VERSIONS_CACHE_KEY)
        self.company = Company.objects.create(name="Recompute Co")

    def _make_payroll(self, basic_salary: Decimal):
        from payroll.models import Payroll

        payroll = Payroll(company=self.company, basic_salary=basic_salary)
        payroll.save()
        return Payroll.objects.get(pk=payroll.pk)

    def test_recompute_statutory_uses_regime_for_as_of_date(self):
        payroll = self._make_payroll(Decimal("1000000"))
        nta_payee = payroll.payee  # computed against today's (NTA 2025) rates

        payroll.recompute_statutory(as_of=date(2025, 6, 1))
        expected_pita = (
            utils.compute_annual_paye(payroll.taxable_income, as_of=date(2025, 6, 1))
            / Decimal("12")
        ).quantize(Decimal("0.01"))
        self.assertEqual(payroll.payee, expected_pita)
        self.assertNotEqual(payroll.payee, nta_payee)

    def test_recompute_statutory_leaves_salary_structure_untouched(self):
        payroll = self._make_payroll(Decimal("1000000"))
        basic_before = payroll.basic
        gross_before = payroll.gross_income

        payroll.recompute_statutory(as_of=date(2025, 6, 1))

        self.assertEqual(payroll.basic, basic_before)
        self.assertEqual(payroll.gross_income, gross_before)
