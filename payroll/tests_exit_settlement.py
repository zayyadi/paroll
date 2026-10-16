"""Tests: exit settlement parity — one Full-and-Final document (P2-15).

Gap #15 of docs/world_class_employee_management_research_2026-10-14.md:
combine payables, receivables and asset recovery into a single settlement
document with journal linkage, posted through the approval machinery.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from company.models import Company
from payroll.models import (
    EmployeeProfile,
    ExitSettlement,
    IOU,
    LeaveBalance,
    Payroll,
)
from payroll.models.workforce import EmployeeAsset, OffboardingChecklist
from payroll.services import exit_settlement_service
from payroll.services.offboarding_service import calculate_final_settlement
from tests.approval_helpers import approval_user, approve_request, submit_approval

User = get_user_model()


class ExitSettlementFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Exit Co")
        user = User.objects.create_user(
            email="leaver@example.com",
            password="password123",
            first_name="Liam",
            last_name="Leaver",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.employee_pay = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("1200000")
        )
        self.employee.save()

        self.hr = approval_user(self.company, ["payroll.change_exitsettlement"])
        self.checklist = OffboardingChecklist.objects.create(
            company=self.company,
            employee=self.employee,
            last_working_day=date(2026, 6, 30),
            reason="Resignation",
            initiated_by=self.hr,
        )

    def _settlement(self, **overrides):
        defaults = dict(checklist=self.checklist)
        defaults.update(overrides)
        return exit_settlement_service.build_settlement(**defaults)


class IOUFixtureMixin:
    """Approved IOUs must be created through the iou.approve workflow."""

    def _iou(self, amount, interest="5", status="APPROVED"):
        from tests.approval_helpers import approve_source

        iou = IOU.objects.create(
            employee_id=self.employee,
            requested_by=self.hr,
            amount=Decimal(amount),
            tenor=6,
            repayment_deduction_percentage=Decimal("10"),
            interest_rate=Decimal(interest),
        )
        if status == "APPROVED":
            approve_source(iou, "iou.approve")
            iou.refresh_from_db()
        elif status == "PAID":
            # PAID is guarded like APPROVED; drive the real iou.settle
            # workflow (direct payment with a full receipt) on top of the
            # iou.approve approval.
            from approvals.services import submit_approval as _submit
            from payroll.services.hr_workflow import decide_iou

            approve_source(iou, "iou.approve")
            iou.refresh_from_db()
            settle_request = _submit(
                source=iou,
                action="iou.settle",
                requester=self.hr,
                payload={
                    "payment_method": "DIRECT_PAYMENT",
                    "amount_received": str(iou.total_amount),
                    "receipt_reference": "RCPT-EXIT-SETTLEMENT",
                },
            )
            approve_request(settle_request)
            iou.refresh_from_db()
        return iou


class PayablesTests(ExitSettlementFixture):
    def test_final_month_salary_is_one_month_of_basic(self):
        payables = exit_settlement_service.payables_for(self.employee)
        # ``Payroll.basic`` is the derived monthly basic on the pay config;
        # the statement pays one month of it.
        self.assertEqual(
            payables["final_month_salary"],
            self.employee.employee_pay.basic / Decimal("12"),
        )

    def test_leave_encashment_uses_leave_type_rates(self):
        from payroll.services import leave_type_service

        leave_type_service.ensure_default_leave_types(self.company)
        LeaveBalance.objects.create(
            employee=self.employee, year=2026, annual_leave=Decimal("10")
        )
        payables = exit_settlement_service.payables_for(self.employee)
        daily = self.employee.employee_pay.basic / Decimal("12") / Decimal("20")
        # ANNUAL encashment_rate defaults to 1.0 → 10 days × daily rate.
        self.assertEqual(
            payables["leave_encashment"], Decimal("10") * daily
        )

    def test_non_encashable_leave_pays_nothing(self):
        from payroll.models import LeaveType
        from payroll.services import leave_type_service

        leave_type_service.ensure_default_leave_types(self.company)
        LeaveBalance.objects.create(
            employee=self.employee, year=2026, annual_leave=Decimal("10")
        )
        LeaveType.objects.filter(
            company=self.company, code="ANNUAL"
        ).update(encashable=False)
        payables = exit_settlement_service.payables_for(self.employee)
        self.assertEqual(payables["leave_encashment"], Decimal("0.00"))


class ReceivablesTests(IOUFixtureMixin, ExitSettlementFixture):
    def test_approved_iou_counts_outstanding_principal_and_interest(self):
        self._iou("60000", interest="5")
        receivables = exit_settlement_service.receivables_for(self.employee)
        # 60,000 + 5% = 63,000
        self.assertEqual(receivables["outstanding_iou"], Decimal("63000.00"))

    def test_paid_iou_counts_nothing(self):
        self._iou("60000", interest="5", status="PAID")
        receivables = exit_settlement_service.receivables_for(self.employee)
        self.assertEqual(receivables["outstanding_iou"], Decimal("0.00"))

    def test_unreturned_assets_charge_replacement_cost(self):
        EmployeeAsset.objects.create(
            company=self.company,
            employee=self.employee,
            name="Laptop",
            asset_tag="TAG-1",
            status=EmployeeAsset.Status.IN_USE,
            replacement_cost=Decimal("450000"),
        )
        EmployeeAsset.objects.create(
            company=self.company,
            employee=self.employee,
            name="Phone",
            asset_tag="TAG-2",
            status=EmployeeAsset.Status.LOST,
            replacement_cost=Decimal("150000"),
        )
        receivables = exit_settlement_service.receivables_for(self.employee)
        self.assertEqual(
            receivables["unreturned_assets_value"], Decimal("600000")
        )

    def test_returned_assets_charge_nothing(self):
        EmployeeAsset.objects.create(
            company=self.company,
            employee=self.employee,
            name="Laptop",
            asset_tag="TAG-1",
            status=EmployeeAsset.Status.RETURNED,
            replacement_cost=Decimal("450000"),
        )
        receivables = exit_settlement_service.receivables_for(self.employee)
        self.assertEqual(receivables["unreturned_assets_value"], Decimal("0.00"))


class StatementTests(IOUFixtureMixin, ExitSettlementFixture):
    def test_statement_combines_both_sides_and_syncs_checklist(self):
        LeaveBalance.objects.create(
            employee=self.employee, year=2026, annual_leave=Decimal("10")
        )
        settlement = self._settlement()
        expected = self.employee.employee_pay.basic / Decimal("12")
        self.assertEqual(settlement.payables_total, expected)
        self.assertEqual(settlement.receivables_total, Decimal("0.00"))
        self.assertEqual(settlement.net_settlement, expected)
        self.assertTrue(settlement.is_payable)
        # Legacy checklist summary stays in step with the statement's payables.
        self.checklist.refresh_from_db()
        self.assertEqual(
            self.checklist.final_settlement_amount, settlement.payables_total
        )

    def test_net_can_favour_the_company(self):
        self._iou("500000", interest="0")
        settlement = self._settlement()
        # payables 480,000 (basic/12) vs receivables 500,000 → leaver owes.
        self.assertEqual(
            settlement.net_settlement, settlement.payables_total - Decimal("500000")
        )
        self.assertFalse(settlement.is_payable)

    def test_rebuild_refreshes_computed_fields_only(self):
        settlement = self._settlement()
        settlement.other_payables = Decimal("20000")
        settlement.save(update_fields=["other_payables"])
        self._iou("30000", interest="0")
        settlement = self._settlement()
        self.assertEqual(settlement.outstanding_iou, Decimal("30000.00"))
        # Discretionary add-backs survive a rebuild.
        self.assertEqual(settlement.other_payables, Decimal("20000"))

    def test_negative_components_rejected(self):
        settlement = self._settlement()
        settlement.other_receivables = Decimal("-1")
        with self.assertRaises(ValidationError):
            settlement.full_clean()

    def test_legacy_calculate_agrees_with_statement_payables(self):
        legacy = calculate_final_settlement(checklist=self.checklist)
        settlement = self._settlement()
        self.assertEqual(legacy, settlement.payables_total)


class PostingTests(IOUFixtureMixin, ExitSettlementFixture):
    def _posted(self):
        settlement = self._settlement()
        request = submit_approval(
            source=settlement, action="exit.settlement", requester=self.hr
        )
        approve_request(request)
        settlement.refresh_from_db()
        return settlement

    def test_approval_posts_settlement_and_links_journal(self):
        settlement = self._posted()
        self.assertEqual(settlement.status, ExitSettlement.Status.POSTED)
        self.assertIsNotNone(settlement.journal_id)
        self.assertIsNotNone(settlement.posted_at)
        self.assertEqual(settlement.journal.status, "POSTED")

    def test_journal_is_balanced_and_double_entry(self):
        LeaveBalance.objects.create(
            employee=self.employee, year=2026, annual_leave=Decimal("10")
        )
        settlement = self._posted()
        journal = settlement.journal
        debits = sum(
            (e.amount for e in journal.entries.filter(entry_type="DEBIT")),
            Decimal("0"),
        )
        credits = sum(
            (e.amount for e in journal.entries.filter(entry_type="CREDIT")),
            Decimal("0"),
        )
        self.assertEqual(debits, credits)
        self.assertEqual(debits, settlement.payables_total)

    def test_journal_linkage_points_at_the_statement(self):
        settlement = self._posted()
        journal = settlement.journal
        self.assertEqual(journal.content_object, settlement)

    def test_receivable_side_credits_employee_advances(self):
        self._iou("30000", interest="0")
        settlement = self._posted()
        advance_credit = settlement.journal.entries.get(
            account__account_number="1400", entry_type="CREDIT"
        )
        self.assertEqual(advance_credit.amount, Decimal("30000.00"))

    def test_posted_statement_cannot_be_rebuilt(self):
        settlement = self._posted()
        with self.assertRaises(ValidationError):
            self._settlement()

    def test_direct_status_write_is_guarded(self):
        settlement = self._settlement()
        settlement.status = ExitSettlement.Status.POSTED
        with self.assertRaises(PermissionDenied):
            settlement.save(update_fields=["status"])

    def test_double_post_is_refused(self):
        settlement = self._posted()
        # A posted statement refuses a second posting at the status check.
        with self.assertRaises(ValidationError):
            exit_settlement_service.post_settlement(
                settlement=settlement, actor=self.hr
            )
