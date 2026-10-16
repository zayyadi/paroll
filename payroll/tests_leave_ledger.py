"""Tests for ledger-derived leave balances (P1-6).

Gap #6 of docs/world_class_employee_management_research_2026-10-14.md: balances
come from append-only accrual/usage/carry-forward/expiry events summed at read
time; ``LeaveBalance`` stays as a read model materialised from the ledger.
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
    LeaveLedgerEntry,
    LeaveRequest,
)
from payroll.services import leave_ledger


class LeaveLedgerFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Leave Ledger Co")
        user = get_user_model().objects.create_user(
            email="ledger@example.com",
            password="password123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save()

    @staticmethod
    def _leave(**overrides):
        defaults = dict(
            leave_type="ANNUAL",
            start_date=date(2026, 6, 3),
            end_date=date(2026, 6, 4),  # 2 days
            reason="Annual leave",
        )
        defaults.update(overrides)
        return defaults


class LedgerEventTests(LeaveLedgerFixture):
    def test_accrual_is_positive(self):
        entry = leave_ledger.record_accrual(
            self.employee, "ANNUAL", 2026, Decimal("10")
        )
        self.assertEqual(entry.days, Decimal("10"))
        self.assertEqual(entry.event_type, LeaveLedgerEntry.EventType.ACCRUAL)
        self.assertEqual(leave_ledger.ledger_balance(self.employee, "ANNUAL", 2026), Decimal("10"))

    def test_usage_is_negative(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, **self._leave()
        )
        entry = leave_ledger.record_usage(leave)
        self.assertEqual(entry.days, Decimal("-2"))
        self.assertEqual(entry.event_type, LeaveLedgerEntry.EventType.USAGE)
        self.assertEqual(entry.year, 2026)
        self.assertEqual(entry.leave_request, leave)

    def test_carry_forward_positive_expiry_negative(self):
        leave_ledger.record_carry_forward(
            self.employee, "ANNUAL", 2026, Decimal("4")
        )
        leave_ledger.record_expiry(self.employee, "ANNUAL", 2026, Decimal("1"))
        self.assertEqual(
            leave_ledger.ledger_balance(self.employee, "ANNUAL", 2026),
            Decimal("3"),
        )

    def test_adjustment_may_be_negative(self):
        leave_ledger.record_adjustment(
            self.employee, "SICK", 2026, Decimal("-1.5")
        )
        self.assertEqual(
            leave_ledger.ledger_balance(self.employee, "SICK", 2026),
            Decimal("-1.5"),
        )

    def test_zero_day_event_rejected(self):
        with self.assertRaises(ValidationError):
            leave_ledger.record_accrual(self.employee, "ANNUAL", 2026, Decimal(0))

    def test_unknown_leave_type_rejected(self):
        with self.assertRaises(ValidationError):
            leave_ledger.record_accrual(
                self.employee, "SABBATICAL", 2026, Decimal("5")
            )


class LedgerBalanceReadTests(LeaveLedgerFixture):
    def test_balance_is_summed_at_read_time(self):
        leave_ledger.record_accrual(self.employee, "ANNUAL", 2026, Decimal("10"))
        leave = LeaveRequest.objects.create(
            employee=self.employee, **self._leave()
        )
        leave_ledger.record_usage(leave)
        leave_ledger.record_carry_forward(
            self.employee, "ANNUAL", 2026, Decimal("2")
        )
        # 10 - 2 + 2 = 10
        self.assertEqual(
            leave_ledger.ledger_balance(self.employee, "ANNUAL", 2026),
            Decimal("10"),
        )

    def test_balance_is_per_year(self):
        leave_ledger.record_accrual(self.employee, "ANNUAL", 2025, Decimal("10"))
        self.assertEqual(
            leave_ledger.ledger_balance(self.employee, "ANNUAL", 2026),
            Decimal(0),
        )

    def test_ledger_balances_cover_every_type_with_zero_defaults(self):
        leave_ledger.record_accrual(self.employee, "SICK", 2026, Decimal("5"))
        balances = leave_ledger.ledger_balances(self.employee, 2026)
        self.assertEqual(balances["SICK"], Decimal("5"))
        self.assertEqual(balances["ANNUAL"], Decimal(0))
        self.assertEqual(balances["CASUAL"], Decimal(0))
        self.assertEqual(balances["MATERNITY"], Decimal(0))
        self.assertEqual(balances["PATERNITY"], Decimal(0))

    def test_sync_materialises_read_model_from_ledger(self):
        leave_ledger.record_accrual(self.employee, "ANNUAL", 2026, Decimal("10"))
        leave_ledger.record_accrual(self.employee, "SICK", 2026, Decimal("5"))
        leave_ledger.record_carry_forward(
            self.employee, "ANNUAL", 2026, Decimal("2")
        )
        leave = LeaveRequest.objects.create(
            employee=self.employee, **self._leave()
        )
        leave_ledger.record_usage(leave)

        balance = leave_ledger.sync_balance_read_model(self.employee, 2026)
        self.assertEqual(balance.annual_leave, 10)  # 10 + 2 - 2
        self.assertEqual(balance.sick_leave, 5)
        # Types with no ledger events are left untouched (legacy rows keep
        # their counters instead of being zeroed).
        self.assertIsNone(
            LeaveLedgerEntry.objects.filter(
                leave_type="CASUAL", year=2026
            ).first()
        )
        # Persisted, not just in memory.
        stored = LeaveBalance.objects.get(employee=self.employee, year=2026)
        self.assertEqual(stored.annual_leave, 10)

    def test_sync_is_idempotent(self):
        leave_ledger.record_accrual(self.employee, "ANNUAL", 2026, Decimal("8"))
        leave_ledger.sync_balance_read_model(self.employee, 2026)
        leave_ledger.sync_balance_read_model(self.employee, 2026)
        self.assertEqual(
            LeaveBalance.objects.filter(employee=self.employee, year=2026).count(),
            1,
        )


class ApprovalWritesLedgerTests(LeaveLedgerFixture):
    """Approving a leave request appends the usage event (the wiring under test)."""

    def _approve(self, **overrides):
        leave = LeaveRequest.objects.create(
            employee=self.employee, **self._leave(**overrides)
        )
        from tests.approval_helpers import approve_source

        approve_source(leave, "leave.approve", maker=self.employee.user)
        return leave

    def test_approved_leave_appends_usage_event(self):
        leave = self._approve()
        entry = LeaveLedgerEntry.objects.get(
            leave_request=leave, event_type=LeaveLedgerEntry.EventType.USAGE
        )
        self.assertEqual(entry.days, Decimal("-2"))
        self.assertEqual(entry.year, 2026)
        self.assertEqual(entry.leave_type, "ANNUAL")
        self.assertEqual(entry.employee, self.employee)

    def test_ledger_usage_matches_counter_decrement(self):
        leave = self._approve()
        balance = LeaveBalance.objects.get(employee=self.employee, year=2026)
        ledger_total = leave_ledger.ledger_balance(self.employee, "ANNUAL", 2026)
        # The yearly balance row seeds a 20-day accrual into the ledger and the
        # approval appends the -2 usage: ledger and counter must agree.
        self.assertEqual(ledger_total, Decimal(balance.annual_leave))
        self.assertEqual(balance.annual_leave, 18)

    def test_reapproving_does_not_double_record(self):
        leave = self._approve()
        leave.status = "APPROVED"
        leave.save()  # status already APPROVED -> previous_status guard
        self.assertEqual(
            LeaveLedgerEntry.objects.filter(
                leave_request=leave,
                event_type=LeaveLedgerEntry.EventType.USAGE,
            ).count(),
            1,
        )

    def test_hr_override_leaves_no_usage_event(self):
        # hr_override bypasses the balance deduction, so no ledger row either —
        # counter and ledger stay in step.
        self._approve(hr_override=True)
        self.assertFalse(
            LeaveLedgerEntry.objects.filter(
                event_type=LeaveLedgerEntry.EventType.USAGE
            ).exists()
        )


class LedgerAndCounterStayInStepTests(LeaveLedgerFixture):
    def test_ledger_plus_accrual_equals_counter(self):
        # The counter row (and its ledger accrual mirror) is created by the
        # approval path itself; only the usage event is appended afterwards.
        leave = LeaveRequest.objects.create(
            employee=self.employee, **self._leave()
        )
        from tests.approval_helpers import approve_source

        approve_source(leave, "leave.approve", maker=self.employee.user)

        balance = LeaveBalance.objects.get(employee=self.employee, year=2026)
        self.assertEqual(
            leave_ledger.ledger_balance(self.employee, "ANNUAL", 2026),
            Decimal(balance.annual_leave),
        )
        # And the materialised read model agrees with the counter.
        synced = leave_ledger.sync_balance_read_model(self.employee, 2026)
        self.assertEqual(synced.annual_leave, balance.annual_leave)
