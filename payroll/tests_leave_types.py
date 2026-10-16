"""Tests for company-configurable leave types and lifecycle states (P2-12).

Gap #12 of docs/world_class_employee_management_research_2026-10-14.md:
leave types become company-configurable with half-day/encashment rules and a
fourth/fifth request state (withdrawn, cancelled, pending HR), reusing the
escalation already wired in ``escalation_service``.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from company.models import Company
from payroll.models import (
    EmployeeProfile,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    get_leave_balance,
)
from payroll.services import leave_lifecycle, leave_type_service

User = get_user_model()


class LeaveTypeFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="LeaveType Co")
        self.user = User.objects.create_user(
            email="leave-type@test.com",
            password="password123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.save(update_fields=["company"])

    def _leave(self, **overrides):
        defaults = dict(
            leave_type="ANNUAL",
            start_date=date(2026, 6, 3),
            end_date=date(2026, 6, 4),
            reason="Annual leave",
        )
        defaults.update(overrides)
        return LeaveRequest.objects.create(employee=self.employee, **defaults)


class LeaveTypeCatalogueTests(LeaveTypeFixture):
    def test_defaults_are_seeded_on_first_balance_read(self):
        self.assertFalse(LeaveType.objects.filter(company=self.company).exists())
        get_leave_balance(self.employee, 2026)
        codes = set(
            LeaveType.objects.filter(company=self.company).values_list(
                "code", flat=True
            )
        )
        self.assertEqual(
            codes, {"ANNUAL", "SICK", "CASUAL", "MATERNITY", "PATERNITY"}
        )

    def test_seeding_is_idempotent_and_preserves_customisations(self):
        leave_type_service.ensure_default_leave_types(self.company)
        # Admin customises the annual entitlement.
        annual = LeaveType.objects.get(company=self.company, code="ANNUAL")
        annual.default_days = Decimal("25")
        annual.save()
        leave_type_service.ensure_default_leave_types(self.company)
        annual.refresh_from_db()
        self.assertEqual(annual.default_days, Decimal("25"))
        self.assertEqual(
            LeaveType.objects.filter(company=self.company).count(), 5
        )

    def test_entitlement_comes_from_leave_type(self):
        leave_type_service.ensure_default_leave_types(self.company)
        annual = LeaveType.objects.get(company=self.company, code="ANNUAL")
        annual.default_days = Decimal("30")
        annual.save()
        balance = get_leave_balance(self.employee, 2026)
        self.assertEqual(balance.annual_leave, 30)

    def test_create_leave_type_rejects_duplicate_code(self):
        leave_type_service.ensure_default_leave_types(self.company)
        with self.assertRaises(ValidationError):
            leave_type_service.create_leave_type(
                company=self.company,
                code="ANNUAL",
                name="Duplicate Annual",
                default_days=Decimal("5"),
            )

    def test_custom_company_type_is_usable(self):
        leave_type_service.create_leave_type(
            company=self.company,
            code="STUDY",
            name="Study Leave",
            default_days=Decimal("10"),
        )
        self.assertEqual(
            leave_type_service.entitlement_days("STUDY", self.company),
            Decimal("10"),
        )


class HalfDayRuleTests(LeaveTypeFixture):
    def test_half_day_rejected_for_type_that_disallows_it(self):
        # SICK defaults to allows_half_day=False; LeaveRequest.save() runs
        # full_clean(), so the rejection surfaces at creation time.
        with self.assertRaises(ValidationError):
            self._leave(
                leave_type="SICK",
                start_date=date(2026, 6, 3),
                end_date=date(2026, 6, 3),
                is_half_day=True,
            )

    def test_half_day_allowed_for_type_that_allows_it(self):
        # ANNUAL defaults to allows_half_day=True.
        leave = self._leave(
            is_half_day=True,
            start_date=date(2026, 6, 3),
            end_date=date(2026, 6, 3),
        )
        leave.full_clean()  # should not raise

    def test_making_a_type_half_day_capable_unlocks_it(self):
        leave_type_service.ensure_default_leave_types(self.company)
        sick = LeaveType.objects.get(company=self.company, code="SICK")
        sick.allows_half_day = True
        sick.save()
        leave = self._leave(
            leave_type="SICK",
            start_date=date(2026, 6, 3),
            end_date=date(2026, 6, 3),
            is_half_day=True,
        )
        leave.full_clean()  # should not raise


class WithdrawAndCancelTests(LeaveTypeFixture):
    def test_withdraw_pending_request(self):
        leave = self._leave()
        leave_lifecycle.withdraw_request(leave=leave, actor=self.user)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "WITHDRAWN")

    def _approve(self, leave):
        """Route the request through the real leave-approval workflow."""
        from tests.approval_helpers import approve_source

        approve_source(leave, "leave.approve", maker=self.employee.user)
        leave.refresh_from_db()
        return leave

    def test_cannot_withdraw_approved_request(self):
        leave = self._leave()
        self._approve(leave)
        self.assertEqual(leave.status, "APPROVED")
        with self.assertRaises(ValidationError):
            leave_lifecycle.withdraw_request(leave=leave, actor=self.user)

    def test_only_requester_may_withdraw(self):
        leave = self._leave()
        other = User.objects.create_user(
            email="other@test.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        with self.assertRaises(ValidationError):
            leave_lifecycle.withdraw_request(leave=leave, actor=other)

    def test_cancel_approved_is_blocked_requires_workflow(self):
        # An approved leave is a reviewed decision; direct cancellation is
        # refused so the reversal goes through the leave.approve workflow.
        leave = self._leave()
        self._approve(leave)
        with self.assertRaises(ValidationError):
            leave_lifecycle.cancel_request(
                leave=leave, actor=self.user, reason="Changed plans"
            )

    def test_cancel_pending_does_not_touch_balance(self):
        from payroll.services import leave_ledger

        leave = self._leave()
        baseline = leave_ledger.ledger_balance(self.employee, "ANNUAL", 2026)
        leave_lifecycle.cancel_request(leave=leave, actor=self.user, reason="Duplicate")
        leave.refresh_from_db()
        self.assertEqual(leave.status, "CANCELLED")
        after = leave_ledger.ledger_balance(self.employee, "ANNUAL", 2026)
        self.assertEqual(after, baseline)

    def test_cannot_cancel_already_closed_request(self):
        from approvals.models import ApprovalRequest
        from approvals.services import decide_approval, submit_approval
        from tests.approval_helpers import approval_user

        leave = self._leave()
        company = self.company
        requester = self.employee.user
        checker = approval_user(company, ["payroll.change_leaverequest"])
        request = submit_approval(
            source=leave, action="leave.approve", requester=requester
        )
        request = ApprovalRequest.objects.get(pk=request.pk)
        decide_approval(
            approval=request,
            actor=checker,
            decision="REJECT",
            comment="Not eligible this cycle",
        )
        leave.refresh_from_db()
        self.assertEqual(leave.status, "REJECTED")
        with self.assertRaises(ValidationError):
            leave_lifecycle.cancel_request(leave=leave, actor=self.user)


class PendingHRStateTests(LeaveTypeFixture):
    def test_escalate_moves_pending_to_pending_hr(self):
        leave = self._leave()
        leave_lifecycle.escalate_to_hr(leave=leave)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "PENDING_HR")

    def test_cannot_escalate_non_pending(self):
        # Reject through the real workflow so guard_state's execution context
        # is satisfied; escalate_to_hr must then refuse a non-pending request.
        leave = self._leave()
        from tests.approval_helpers import reject_source

        reject_source(leave, "leave.approve", maker=self.employee.user)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "REJECTED")
        with self.assertRaises(ValidationError):
            leave_lifecycle.escalate_to_hr(leave=leave)

    def test_pending_hr_blocks_overlapping_requests(self):
        # A PENDING_HR request must block overlaps exactly like a PENDING one
        # (it is still an undecided, date-holding request).
        from django.core.exceptions import ValidationError as VE

        leave = self._leave()
        leave.status = "PENDING_HR"
        leave.save(update_fields=["status"])

        def overlap_probe():
            return LeaveRequest(
                employee=self.employee,
                leave_type="ANNUAL",
                start_date=date(2026, 6, 4),
                end_date=date(2026, 6, 5),
                reason="Overlap probe",
            )

        with self.assertRaises(VE):
            overlap_probe().full_clean()

        # Same result as the PENDING baseline.
        leave.status = "PENDING"
        leave.save(update_fields=["status"])
        with self.assertRaises(VE):
            overlap_probe().full_clean()
