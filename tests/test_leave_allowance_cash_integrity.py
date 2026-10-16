"""A separately paid leave allowance must not create another payroll payment."""
from datetime import date, timedelta, datetime, time
from django.utils import timezone
from decimal import Decimal

from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum

from accounting.tests import test_payroll_postings as payroll_fixtures
from accounting.models import Journal
from payroll.models import (
    Allowance,
    CompanyPayrollSetting,
    LeaveRequest,
    PayrollRun,
    PayrollRunEntry,
)
from tests.approval_helpers import approve_source


class LeaveAllowanceCashIntegrityTests(TestCase):
    setUp = payroll_fixtures.PayrollClosePostingTests.setUp
    _create_employee_stack = (
        payroll_fixtures.PayrollClosePostingTests._create_employee_stack
    )
    _q = payroll_fixtures.PayrollClosePostingTests._q

    def test_approved_leave_and_payroll_pay_allowance_only_once(self):
        salary, employee, entry = self._create_employee_stack(basic_salary="50000.00")
        CompanyPayrollSetting.objects.update_or_create(
            company=self.company,
            defaults={
                "leave_allowance_percentage": Decimal("10"),
                "pays_thirteenth_month": False,
            },
        )
        period = date.today().replace(day=1)
        leave = LeaveRequest.objects.create(
            employee=employee,
            leave_type="ANNUAL",
            start_date=period + timedelta(days=1),
            end_date=period + timedelta(days=2),
            reason="Annual leave",
        )
        approve_source(leave, "leave.approve", maker=employee.user)
        allowance = Allowance.objects.get(source_leave_request=leave)
        leave_journal = Journal.objects.get(
            company=self.company,
            content_type=ContentType.objects.get_for_model(Allowance),
            object_id=allowance.pk,
        )
        self.assertEqual(leave_journal.status, "POSTED")
        self.assertEqual(
            leave_journal.entries.get(entry_type="CREDIT").amount, Decimal("60000")
        )
        run = PayrollRun.objects.create(
            company=self.company,
            name="Leave allowance cash check",
            paydays=period,
            is_active=True,
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        entry.save()
        approve_source(run, "payroll.lock")
        payroll_journal = Journal.objects.get(
            company=self.company,
            content_type=ContentType.objects.get_for_model(PayrollRun),
            object_id=run.pk,
        )
        allowance_expense = payroll_journal.entries.filter(
            account__account_number="6015", entry_type="DEBIT"
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        self.assertEqual(
            allowance_expense,
            Decimal("0"),
            "The allowance expense was recognized once at leave approval.",
        )
        cash = payroll_journal.entries.filter(
            account__account_number="1100", entry_type="CREDIT"
        ).aggregate(total=Sum("amount"))["total"]
        self.assertEqual(
            cash,
            self._q(employee.net_pay),
            "Monthly cash must contain salary only; leave cash was already paid.",
        )
        entry.refresh_from_db()
        self.assertEqual(entry.calc_allowance, Decimal("0"))

    def _draft_run(self, entry):
        run = PayrollRun.objects.create(
            company=self.company,
            name="Draft source-bound payroll",
            paydays=date.today().replace(day=1),
            is_active=True,
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        return run

    def test_unpaid_manual_leave_allowance_remains_in_the_approved_payroll(self):
        from payroll.financial_approval_actions import request_payroll_lock
        from tests.approval_helpers import approval_user, approve_request

        _, employee, entry = self._create_employee_stack(basic_salary="50000")
        Allowance.objects.create(
            employee=employee,
            allowance_type="LV",
            amount=Decimal("1500"),
            created_at=timezone.now(),
        )
        run = self._draft_run(entry)
        maker = approval_user(self.company, ["payroll.change_payrollrun"])
        request = request_payroll_lock(run, maker)
        entry.refresh_from_db()
        self.assertEqual(entry.calc_allowance, Decimal("1500"))
        self.assertEqual(entry.netpay, self._q(employee.net_pay + Decimal("1500")))
        approve_request(request)
        journal = Journal.objects.get(
            company=self.company,
            content_type=ContentType.objects.get_for_model(PayrollRun),
            object_id=run.pk,
        )
        self.assertEqual(
            journal.entries.filter(account__account_number="6015", entry_type="DEBIT")
            .get()
            .amount,
            Decimal("1500"),
        )
        self.assertEqual(
            journal.entries.filter(account__account_number="1100", entry_type="CREDIT")
            .get()
            .amount,
            entry.netpay,
        )

    def test_same_net_changed_inputs_after_first_stage_cannot_change_posting(self):
        from payroll.models import Deduction
        from payroll.financial_approval_actions import request_payroll_lock
        from approvals.models import ApprovalPolicy
        from approvals.services import decide_approval
        from django.core.exceptions import ValidationError
        from tests.approval_helpers import approval_user

        _, employee, entry = self._create_employee_stack(basic_salary="50000")
        allowance = Allowance.objects.create(
            employee=employee,
            allowance_type="OTHER",
            amount=Decimal("1000"),
            created_at=timezone.now(),
        )
        deduction = Deduction.objects.create(
            employee=employee,
            deduction_type="OTHER",
            amount=Decimal("1000"),
            created_at=timezone.now(),
        )
        run = self._draft_run(entry)
        ApprovalPolicy.objects.create(
            company=self.company,
            action="payroll.lock",
            stages=[
                {"permission": "payroll.change_payrollrun"},
                {"permission": "payroll.change_payrollrun"},
            ],
        )
        maker = approval_user(self.company, ["payroll.change_payrollrun"])
        first = approval_user(self.company, ["payroll.change_payrollrun"])
        second = approval_user(self.company, ["payroll.change_payrollrun"])
        request = request_payroll_lock(run, maker)
        request = decide_approval(approval=request, actor=first)
        reviewed_net = entry.get_netpay
        allowance.amount = Decimal("1200")
        allowance.save()
        deduction.amount = Decimal("1200")
        deduction.save()
        self.assertEqual(entry.get_netpay, reviewed_net)
        with self.assertRaises(ValidationError):
            decide_approval(approval=request, actor=second)
        self.assertEqual(request.decisions.count(), 1)
        self.assertFalse(
            Journal.objects.filter(
                company=self.company,
                content_type=ContentType.objects.get_for_model(PayrollRun),
                object_id=run.pk,
            ).exists()
        )

    def test_other_period_allowance_does_not_invalidate_current_review(self):
        from payroll.financial_approval_actions import request_payroll_lock
        from tests.approval_helpers import approval_user, approve_request

        _, employee, entry = self._create_employee_stack(basic_salary="50000")
        run = self._draft_run(entry)
        maker = approval_user(self.company, ["payroll.change_payrollrun"])
        request = request_payroll_lock(run, maker)
        other_month = date.today().replace(day=1) - timedelta(days=1)
        Allowance.objects.create(
            employee=employee,
            allowance_type="OTHER",
            amount=Decimal("999"),
            created_at=timezone.make_aware(datetime.combine(other_month, time.min)),
        )
        approve_request(request)
        request.refresh_from_db()
        self.assertEqual(request.status, "APPROVED")

    def test_source_leave_allowance_without_active_payment_remains_payable(self):
        from tests.approval_helpers import approved_operation_for

        _, employee, entry = self._create_employee_stack(basic_salary="50000")
        CompanyPayrollSetting.objects.update_or_create(
            company=self.company,
            defaults={
                "leave_allowance_percentage": Decimal("10"),
                "pays_thirteenth_month": False,
            },
        )
        period = date.today().replace(day=1)
        leave = LeaveRequest.objects.create(
            employee=employee,
            leave_type="ANNUAL",
            start_date=period + timedelta(days=1),
            end_date=period + timedelta(days=2),
            reason="Payment reversal boundary",
        )
        approve_source(leave, "leave.approve", maker=employee.user)
        allowance = Allowance.objects.get(source_leave_request=leave)
        journal = Journal.objects.get(
            company=self.company,
            content_type=ContentType.objects.get_for_model(Allowance),
            object_id=allowance.pk,
        )
        approved_operation_for("accounting.change_journal")(
            journal.reverse, user=None, reason="Actual payment was returned"
        )
        self._draft_run(entry)
        self.assertEqual(entry.calc_allowance, Decimal("60000"))
        journal.refresh_from_db()
        self.assertEqual(journal.status, "REVERSED")
        self.assertEqual(
            Allowance.objects.get(pk=allowance.pk).amount, Decimal("60000")
        )

    def test_legacy_unpaid_sick_leave_link_does_not_create_annual_allowance(self):
        _, employee, entry = self._create_employee_stack(basic_salary="50000")
        period = date.today().replace(day=1)
        sick = LeaveRequest.objects.create(
            employee=employee,
            leave_type="SICK",
            start_date=period + timedelta(days=1),
            end_date=period + timedelta(days=2),
            reason="Historical bad automatic allowance link",
        )
        Allowance.objects.create(
            employee=employee,
            allowance_type="LV",
            source_leave_request=sick,
            amount=Decimal("60000"),
        )
        self._draft_run(entry)
        self.assertEqual(entry.calc_allowance, Decimal("0"))
        self.assertEqual(
            Allowance.objects.get(source_leave_request=sick).amount, Decimal("60000")
        )
