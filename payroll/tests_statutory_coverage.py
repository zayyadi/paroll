"""End-to-end statutory coverage for all seven Nigerian obligations.

Gap #3 of docs/world_class_employee_management_research_2026-10-14.md: the rate
toggles and due dates exist, but each of the seven obligations must have its
*amount*, *penalty exposure* and *RemittanceRecord* creation exercised by tests.

The seven obligations (``RemittanceRecord.OBLIGATION_CHOICES``):
    paye, pension, nhf, nhia, nsitf, itf, paye_annual

Stored-field conventions under test (``period_remittance_amounts``):
    payee / nhf / nhif / nsitf are monthly; pension is annual (÷12);
    itf is annual (1% of annual gross); paye_annual carries no amount.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from company.models import Company
from payroll import utils
from payroll.models import (
    CompanyPayrollSetting,
    EmployeeProfile,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
    RemittanceRecord,
)
from payroll.services import compliance


class StatutoryCoverageFixture(TestCase):
    """One employee at NGN 120,000 basic with every statutory scheme on.

    Monthly figures for this salary (NGN basic basis):
        NHF   2.5% of 120,000 = 3,000
        NHIA  5%   of 120,000 = 6,000 (employee share)
        NSITF 1%   of 120,000 = 1,200
        Pension (18% of 1,440,000 annual) / 12 = 21,600
        PAYE  = 6,560 (locked by tests_tax.ComplianceCalendarTests)
        ITF   1% of 1,440,000 annual = 14,400 (annual)
    """

    PERIOD = date(2026, 6, 1)

    def setUp(self):
        self.company = Company.objects.create(name="Statutory Coverage Co")
        self.user = get_user_model().objects.create_user(
            email="statutory@example.com",
            password="testpass123",
            first_name="Stat",
            last_name="Cover",
            company=self.company,
            active_company=self.company,
            is_staff=True,
            is_superuser=True,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])

        # Enable every scheme: housing (NHF), NHIA, and both annual levies.
        CompanyPayrollSetting.objects.create(
            company=self.company, itf_applicable=True, nhia_applicable=True
        )
        config = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("120000.00"),
            is_housing=True,
            is_nhif=True,
        )
        self.employee.employee_pay = config
        self.employee.save(update_fields=["employee_pay"])
        self.config = config

        self.run = PayrollRun.objects.create(
            company=self.company,
            name="June 2026 Payroll",
            paydays=self.PERIOD,
            is_active=True,
        )
        entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee, status="active"
        )
        PayrollRunEntry.objects.create(payroll_run=self.run, payroll_entry=entry)

        self.client.login(email=self.user.email, password="testpass123")

    # -- helpers ------------------------------------------------------------

    def _obligations(self, as_of):
        return compliance.compliance_obligations(self.company, as_of=as_of)

    def _by_key(self, obligations, key):
        return next(o for o in obligations if o["key"] == key)

    def _mark(self, obligation, period="2026-06"):
        return self.client.post(
            reverse(
                "payroll:mark_remittance",
                kwargs={"obligation": obligation, "period": period},
            )
        )


class MonthlyAmountTests(StatutoryCoverageFixture):
    """Exact monthly remittance amounts for every obligation that has one.

    Amounts are pinned to the stored config fields (the contract
    ``period_remittance_amounts`` implements), not to guessed magic numbers.
    """

    def test_paye_amount_is_monthly(self):
        amounts = compliance.period_remittance_amounts(self.company, self.run)
        self.assertEqual(amounts["paye"], self.config.payee)
        self.assertGreater(amounts["paye"], 0)

    def test_pension_amount_is_annual_divided_by_twelve(self):
        amounts = compliance.period_remittance_amounts(self.company, self.run)
        self.assertEqual(
            amounts["pension"],
            (self.config.pension / Decimal("12")).quantize(Decimal("0.01")),
        )

    def test_nhf_amount_is_monthly_stored_field(self):
        amounts = compliance.period_remittance_amounts(self.company, self.run)
        self.assertEqual(amounts["nhf"], self.config.nhf)
        self.assertGreater(amounts["nhf"], 0)

    def test_nhia_amount_is_monthly_stored_field(self):
        amounts = compliance.period_remittance_amounts(self.company, self.run)
        self.assertEqual(amounts["nhia"], self.config.nhif)
        self.assertGreater(amounts["nhia"], 0)

    def test_nsitf_amount_is_one_percent_of_monthly_basic(self):
        amounts = compliance.period_remittance_amounts(self.company, self.run)
        self.assertEqual(amounts["nsitf"], Decimal("1200.00"))


class ObligationPresenceAndDueDateTests(StatutoryCoverageFixture):
    """Each obligation appears with the right due date and amount."""

    def test_all_seven_obligations_present(self):
        keys = {o["key"] for o in self._obligations(as_of=date(2026, 6, 5))}
        self.assertEqual(
            keys,
            {"paye", "pension", "nhf", "nhia", "nsitf", "itf", "paye_annual"},
        )

    def test_paye_due_10th_of_following_month(self):
        paye = self._by_key(self._obligations(date(2026, 6, 5)), "paye")
        self.assertEqual(paye["due_date"], date(2026, 7, 10))
        self.assertEqual(paye["amount"], self.config.payee)

    def test_nhf_and_nhia_due_10th_of_following_month(self):
        obligations = self._obligations(date(2026, 6, 5))
        self.assertEqual(
            self._by_key(obligations, "nhf")["due_date"], date(2026, 7, 10)
        )
        self.assertEqual(
            self._by_key(obligations, "nhia")["due_date"], date(2026, 7, 10)
        )

    def test_nsitf_due_last_day_of_period_month(self):
        nsitf = self._by_key(self._obligations(date(2026, 6, 5)), "nsitf")
        self.assertEqual(nsitf["due_date"], date(2026, 6, 30))

    def test_itf_is_annual_due_1_april(self):
        itf = self._by_key(self._obligations(date(2026, 6, 5)), "itf")
        self.assertEqual(itf["due_date"], date(2027, 4, 1))
        self.assertEqual(itf["period"], date(2026, 1, 1))
        # ITF is the annual sum of the stored 1%-of-annual-gross levy.
        self.assertEqual(itf["amount"], self.config.itf)
        self.assertGreater(itf["amount"], 0)

    def test_paye_annual_is_31_january_with_no_amount(self):
        paye_annual = self._by_key(self._obligations(date(2026, 6, 5)), "paye_annual")
        self.assertEqual(paye_annual["due_date"], date(2027, 1, 31))
        self.assertIsNone(paye_annual["amount"])


class OverduePenaltyTests(StatutoryCoverageFixture):
    """Penalty exposure is surfaced for every obligation once overdue."""

    def test_paye_overdue_has_state_defined_penalty(self):
        paye = self._by_key(self._obligations(date(2026, 8, 1)), "paye")
        self.assertEqual(paye["status"], "overdue")
        self.assertIsNotNone(paye["penalty"])
        self.assertIsNone(paye["penalty"]["amount"])

    def test_pension_overdue_accrues_two_percent_per_month(self):
        pension = self._by_key(self._obligations(date(2026, 8, 1)), "pension")
        self.assertEqual(pension["status"], "overdue")
        self.assertEqual(pension["penalty"]["rate"], "2% per month")
        # 21,600 x 2% x 2 months (Jun 10 -> Aug 1 = 52 days -> ceil/30).
        self.assertEqual(pension["penalty"]["amount"], Decimal("864.00"))

    def test_nhf_overdue_penalty_is_note_only(self):
        nhf = self._by_key(self._obligations(date(2026, 8, 1)), "nhf")
        self.assertEqual(nhf["status"], "overdue")
        self.assertIsNotNone(nhf["penalty"])
        self.assertIsNone(nhf["penalty"]["amount"])

    def test_nhia_overdue_penalty_is_note_only(self):
        nhia = self._by_key(self._obligations(date(2026, 8, 1)), "nhia")
        self.assertEqual(nhia["status"], "overdue")
        self.assertIsNone(nhia["penalty"]["amount"])

    def test_nsitf_overdue_penalty_is_note_only(self):
        nsitf = self._by_key(self._obligations(date(2026, 7, 15)), "nsitf")
        self.assertEqual(nsitf["status"], "overdue")
        self.assertIsNone(nsitf["penalty"]["amount"])

    def test_itf_overdue_penalty_is_note_only(self):
        itf = self._by_key(self._obligations(date(2027, 5, 1)), "itf")
        self.assertEqual(itf["status"], "overdue")
        self.assertIsNotNone(itf["penalty"])
        self.assertIsNone(itf["penalty"]["amount"])

    def test_paye_annual_overdue_penalty_is_note_only(self):
        paye_annual = self._by_key(
            self._obligations(date(2027, 3, 1)), "paye_annual"
        )
        self.assertEqual(paye_annual["status"], "overdue")
        self.assertIsNotNone(paye_annual["penalty"])
        self.assertIsNone(paye_annual["penalty"]["amount"])


class RemittanceRecordCreationTests(StatutoryCoverageFixture):
    """Marking an obligation remitted creates a RemittanceRecord and flips done."""

    def _assert_marked(self, obligation, period_date, post_period="2026-06"):
        self._mark(obligation, period=post_period)
        record = RemittanceRecord.objects.get(
            company=self.company, obligation=obligation, period=period_date
        )
        self.assertIsNotNone(record.remitted_on)
        return record

    def test_paye_remittance_record_created(self):
        record = self._assert_marked("paye", self.PERIOD)
        self.assertIsNotNone(record.remitted_on)

    def test_pension_remittance_record_created(self):
        record = self._assert_marked("pension", self.PERIOD)
        self.assertIsNotNone(record.remitted_on)

    def test_nhf_remittance_record_created(self):
        record = self._assert_marked("nhf", self.PERIOD)
        self.assertIsNotNone(record.remitted_on)

    def test_nhia_remittance_record_created(self):
        record = self._assert_marked("nhia", self.PERIOD)
        self.assertIsNotNone(record.remitted_on)

    def test_nsitf_remittance_record_created(self):
        record = self._assert_marked("nsitf", self.PERIOD)
        self.assertIsNotNone(record.remitted_on)

    def test_itf_remittance_record_created(self):
        # ITF is annual; its calendar period is the year start.
        record = self._assert_marked("itf", date(2026, 1, 1), post_period="2026-01")
        self.assertIsNotNone(record.remitted_on)

    def test_paye_annual_remittance_record_created(self):
        record = self._assert_marked(
            "paye_annual", date(2027, 1, 1), post_period="2027-01"
        )
        self.assertIsNotNone(record.remitted_on)


class RemittanceClearsObligationTests(StatutoryCoverageFixture):
    """A remitted record takes the obligation out of the open exposure."""

    def _assert_cleared(self, obligation):
        # Overdue before remittance.
        before = self._by_key(self._obligations(date(2026, 8, 1)), obligation)
        self.assertEqual(before["status"], "overdue")
        self._mark(obligation)
        after = self._by_key(self._obligations(date(2026, 8, 1)), obligation)
        self.assertEqual(after["status"], "done")
        self.assertIsNone(after["penalty"])

    def test_paye_remitted_clears(self):
        self._assert_cleared("paye")

    def test_pension_remitted_clears(self):
        self._assert_cleared("pension")

    def test_nhf_remitted_clears(self):
        self._assert_cleared("nhf")

    def test_nhia_remitted_clears(self):
        self._assert_cleared("nhia")

    def test_nsitf_remitted_clears(self):
        self._assert_cleared("nsitf")


class ObligationAmountMatchesStoredFieldTests(StatutoryCoverageFixture):
    """Cross-check the calendar amount against the stored config field."""

    def test_every_monthly_obligation_matches_its_stored_field(self):
        obligations = self._obligations(date(2026, 6, 5))
        by_key = {o["key"]: o for o in obligations}
        config = self.config
        self.assertEqual(
            by_key["paye"]["amount"], config.payee
        )
        self.assertEqual(
            by_key["pension"]["amount"],
            (config.pension / Decimal("12")).quantize(Decimal("0.01")),
        )
        self.assertEqual(by_key["nhf"]["amount"], config.nhf)
        self.assertEqual(by_key["nhia"]["amount"], config.nhif)
        self.assertEqual(by_key["nsitf"]["amount"], config.nsitf)
