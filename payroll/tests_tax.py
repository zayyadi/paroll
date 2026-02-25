from decimal import Decimal

from django.test import SimpleTestCase

from payroll import utils


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


class NigeriaTaxComputationTests(SimpleTestCase):
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

    def test_nhif_below_500k_uses_5_10_split(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("400000"),
            annual_gross=Decimal("4800000"),
        )
        self.assertEqual(utils.calc_employee_health_contrib(payroll), Decimal("20000"))
        self.assertEqual(utils.calc_employer_health_contrib(payroll), Decimal("40000"))
        self.assertEqual(utils.calc_health_contrib(payroll), Decimal("60000"))

    def test_nhif_500k_to_999999_uses_10_5_split(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("999999"),
            annual_gross=Decimal("11999988"),
        )
        self.assertEqual(utils.calc_employee_health_contrib(payroll), Decimal("99999.9"))
        self.assertEqual(utils.calc_employer_health_contrib(payroll), Decimal("49999.95"))
        self.assertEqual(utils.calc_health_contrib(payroll), Decimal("149999.85"))

    def test_nhif_at_or_above_1m_employee_pays_full_15_percent(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("1000000"),
            annual_gross=Decimal("12000000"),
        )
        self.assertEqual(utils.calc_employee_health_contrib(payroll), Decimal("150000"))
        self.assertEqual(utils.calc_employer_health_contrib(payroll), Decimal("0"))
        self.assertEqual(utils.calc_health_contrib(payroll), Decimal("150000"))

    def test_nhif_disabled_returns_zero_for_all_health_contributions(self):
        payroll = DummyPayroll(
            basic_salary=Decimal("1000000"),
            annual_gross=Decimal("12000000"),
            is_nhif=False,
        )
        self.assertEqual(utils.calc_employee_health_contrib(payroll), Decimal("0.0"))
        self.assertEqual(utils.calc_employer_health_contrib(payroll), Decimal("0.0"))
        self.assertEqual(utils.calc_health_contrib(payroll), Decimal("0.0"))
