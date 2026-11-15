"""Payroll moves through the ledger in three steps, and every liability clears.

1. Lock (approved payroll.lock):  Dr salary & employer-cost expense
                                  Cr Net Salaries Payable (2105) + one payable
                                  per body. Cash/bank is not touched yet.
2. Bank file confirmed:           Dr Net Salaries Payable / Cr Bank (1020)
3. Remittance marked done:        Dr <body> Payable / Cr Bank, for exactly what
                                  the period's accruals credited. Like any
                                  manual journal it posts once independently
                                  approved; undo raises a reversal request.

Worked example: ₦50,000/month on a 60/25/15 basic/housing/transport split,
PAYE nil (minimum-wage exempt), water ₦150, no NHF/NHIA.
  employee pension 8% x 50,000  = 4,000;  employer 10% = 5,000
  NSITF 1% x 600,000 / 12       =   500
  ITF   1% x 600,000 / 12       =   500 (only when the company is liable)
  net = 50,000 - 4,000 - 150    = 45,850
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from accounting.models import Journal, JournalEntry
from approvals.models import ApprovalRequest
from approvals.proposals import _request_actor
from company.models import Company
from payroll.models import (
    CompanyPayrollSetting,
    EmployeeProfile,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
    PayslipEmailJob,
)
from payroll.services import payroll_settlement as settlement
from tests.approval_helpers import approval_user, approve_request, approve_source

User = get_user_model()


class PayrollSettlementTestBase(TestCase):
    itf_applicable = False

    def setUp(self):
        self.company = Company.objects.create(name="Settlement Ltd")
        CompanyPayrollSetting.objects.create(
            company=self.company,
            basic_percentage=Decimal("60"),
            housing_percentage=Decimal("25"),
            transport_percentage=Decimal("15"),
            itf_applicable=self.itf_applicable,
        )
        self.employee = EmployeeProfile.objects.create(
            company=self.company,
            first_name="Amina",
            last_name="Usman",
            email="amina@settlement.test",
            bank="Zenith",
            bank_account_number="0123456789",
            employee_pay=Payroll.objects.create(
                company=self.company, basic_salary=Decimal("50000")
            ),
            status="active",
        )
        self.run = PayrollRun.objects.create(
            company=self.company,
            name="Payroll 2026-01",
            paydays=date(2026, 1, 1),
            is_active=True,
        )
        PayrollRunEntry.objects.create(
            payroll_run=self.run,
            payroll_entry=PayrollEntry.objects.create(
                company=self.company, pays=self.employee, status="active"
            ),
        )
        self.run.refresh_from_db()

    def lock(self):
        with patch.object(PayslipEmailJob, "enqueue"):
            with self.captureOnCommitCallbacks(execute=True):
                approve_source(self.run, "payroll.lock")
        self.run.refresh_from_db()

    def balance(self, account_number):
        """Debit-positive balance across posted and later-reversed journals."""
        lines = JournalEntry.objects.filter(
            journal__company=self.company,
            journal__status__in=[Journal.JournalStatus.POSTED, Journal.JournalStatus.REVERSED],
            account__account_number=account_number,
        )
        debit = lines.filter(entry_type="DEBIT").aggregate(t=Sum("amount"))["t"] or 0
        credit = lines.filter(entry_type="CREDIT").aggregate(t=Sum("amount"))["t"] or 0
        return Decimal(debit) - Decimal(credit)

    def pay_by_bank(self):
        """Generate, independently approve and confirm a NIP file."""
        from payroll.services.bank_payment_service import (
            generate_nip_file,
            mark_confirmed,
            mark_submitted,
        )

        maker = approval_user(self.company, ["payroll.change_payrollrun"])
        payment_file = generate_nip_file(payroll_run=self.run, bank_code="057")
        payment_file.created_by = maker
        payment_file.save(update_fields=["created_by"])
        token = _request_actor.set(maker)
        try:
            request = approve_request(
                mark_submitted(payment_file=payment_file, reference_number="NIP-1")
            )
        finally:
            _request_actor.reset(token)
        approval = ApprovalRequest.objects.filter(
            action="bank_payment.submit", object_id=payment_file.pk, status="APPROVED"
        ).latest("pk")
        checker = approval.decisions.filter(decision="APPROVE").latest("stage").actor
        token = _request_actor.set(checker)
        try:
            mark_confirmed(payment_file=payment_file)
        finally:
            _request_actor.reset(token)
        self.run.refresh_from_db()
        return payment_file


class AccrualOnLockTests(PayrollSettlementTestBase):
    def test_lock_credits_net_salaries_payable_not_cash(self):
        self.lock()
        self.assertEqual(self.balance("2105"), Decimal("-45850.00"))
        self.assertEqual(self.balance("1100"), Decimal("0"))
        self.assertEqual(self.balance("1020"), Decimal("0"))

    def test_accrual_journal_has_a_posting_key_and_posts_once(self):
        from payroll.services.payroll_accounting_service import handle_payroll_period_closure

        self.lock()
        handle_payroll_period_closure(self.run)
        journals = Journal.objects.filter(
            company=self.company, posting_key=f"payroll_run:{self.run.pk}:accrual"
        )
        self.assertEqual(journals.count(), 1)


class ItfAccrualTests(PayrollSettlementTestBase):
    itf_applicable = True

    def test_itf_is_accrued_when_company_is_liable(self):
        self.lock()
        self.assertEqual(self.balance("6050"), Decimal("500.00"))
        self.assertEqual(self.balance("2180"), Decimal("-500.00"))


class PayslipEmailTimingTests(PayrollSettlementTestBase):
    def jobs(self):
        return PayslipEmailJob.objects.filter(payroll_run=self.run)

    def test_lock_queues_payslip_emails_once(self):
        with patch.object(PayslipEmailJob, "enqueue") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                approve_source(self.run, "payroll.lock")
        self.assertEqual(self.jobs().count(), 1)
        enqueue.assert_called_once_with()

    def test_creating_a_pay_period_sends_no_payslips(self):
        hr = approval_user(
            self.company,
            ["payroll.add_payrollrun", "payroll.view_payrollrun", "payroll.change_payrollrun"],
        )
        self.client.force_login(hr)
        with patch.object(PayslipEmailJob, "enqueue") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    reverse("payroll:payday_create_new"),
                    data={
                        "name": "February Payroll",
                        "paydays": "2026-02",
                        "is_active": "on",
                        "payroll_payday": str(self.employee.pk),
                    },
                )
        new_run = PayrollRun.objects.get(company=self.company, name="February Payroll")
        self.assertEqual(PayslipEmailJob.objects.filter(payroll_run=new_run).count(), 0)
        enqueue.assert_not_called()


class SalaryPaymentTests(PayrollSettlementTestBase):
    def test_confirmed_bank_file_clears_net_salaries_payable(self):
        self.lock()
        self.pay_by_bank()
        self.assertEqual(self.run.status, PayrollRun.Status.PAID)
        self.assertEqual(self.balance("2105"), Decimal("0"))
        self.assertEqual(self.balance("1020"), Decimal("-45850.00"))
        self.assertEqual(
            Journal.objects.filter(
                company=self.company,
                posting_key__startswith=f"payroll_run:{self.run.pk}:payment:",
            ).count(),
            1,
        )


class RemittanceTests(PayrollSettlementTestBase):
    def setUp(self):
        super().setUp()
        self.lock()
        self.finance = approval_user(
            self.company,
            ["payroll.change_payrollrun", "payroll.view_payrollrun", "accounting.change_journal"],
        )

    def remit(self, obligation, unmark=False):
        self.client.force_login(self.finance)
        return self.client.post(
            reverse(
                "payroll:mark_remittance",
                kwargs={"obligation": obligation, "period": "2026-01"},
            ),
            {"unmark": "1"} if unmark else {},
        )

    def pending(self):
        return ApprovalRequest.objects.filter(company=self.company, status="PENDING")

    def approve_all_pending(self):
        for request in list(self.pending()):
            approve_request(request)

    def test_remittance_journal_posts_after_independent_approval(self):
        self.remit("pension")
        self.assertEqual(self.balance("2120"), Decimal("-9000.00"))  # nothing posted yet
        self.assertEqual(self.pending().count(), 1)

        self.approve_all_pending()
        self.assertEqual(self.balance("2120"), Decimal("0"))
        self.assertEqual(self.balance("1020"), Decimal("-9000.00"))

    def test_marking_twice_raises_one_request(self):
        self.remit("pension")
        self.remit("pension")
        self.assertEqual(self.pending().count(), 1)

    def test_undo_raises_a_reversal_that_reopens_the_payable(self):
        self.remit("pension")
        self.approve_all_pending()
        self.remit("pension", unmark=True)
        self.approve_all_pending()
        self.assertEqual(self.balance("2120"), Decimal("-9000.00"))
        self.assertEqual(self.balance("1020"), Decimal("0"))

        self.remit("pension")
        self.approve_all_pending()
        self.assertEqual(self.balance("2120"), Decimal("0"))

    def test_filing_only_obligation_posts_nothing(self):
        self.remit("paye_annual")
        self.assertEqual(self.pending().count(), 0)

    def test_liabilities_net_to_zero_once_paid_and_remitted(self):
        self.pay_by_bank()
        for obligation in ("paye", "pension", "nhf", "nhia", "nsitf"):
            self.remit(obligation)
        self.approve_all_pending()
        for account in ("2105", "2110", "2120", "2130", "2140", "2150"):
            self.assertEqual(self.balance(account), Decimal("0"), account)

    def test_remittance_amount_matches_compliance_calendar(self):
        from payroll.services.compliance import period_remittance_amounts

        calendar = period_remittance_amounts(self.company, self.run)
        for obligation in ("pension", "nsitf"):
            self.assertEqual(
                settlement.accrued_amount(self.company, obligation, date(2026, 1, 1)),
                calendar[obligation],
                obligation,
            )
