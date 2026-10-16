from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth.models import Permission
from django.test import TransactionTestCase

from accounting.models import AccountingPeriod, Journal
from accounting.utils import get_or_create_fiscal_year, get_or_create_period
from company.models import Company
from payroll.models import EmployeeProfile, IOU
from users.models import CustomUser


class IOUAtomicityTests(TransactionTestCase):
    def setUp(self):
        self.company = Company.objects.create(name="IOU atomicity")
        self.maker = CustomUser.objects.create_user(
            email="iou@example.com",
            password="test-password",
            company=self.company,
            active_company=self.company,
        )
        self.checker = CustomUser.objects.create_user(email="iou-checker@example.test", password="x", company=self.company, active_company=self.company)
        self.receipt_maker = CustomUser.objects.create_user(email="iou-receipt-maker@example.test", password="x", company=self.company, active_company=self.company)
        permissions = Permission.objects.filter(content_type__app_label="payroll", codename="change_iou")
        self.checker.user_permissions.add(*permissions)
        self.receipt_maker.user_permissions.add(*permissions)
        closing_permission = Permission.objects.get(content_type__app_label="accounting", codename="change_accountingperiod")
        self.maker.user_permissions.add(closing_permission)
        self.checker.user_permissions.add(closing_permission)
        self.employee = EmployeeProfile.objects.get(user=self.maker)
        self.iou = IOU.objects.create(
            employee_id=self.employee, amount=Decimal("100.00"), tenor=1
        )

    def approve(self):
        from approvals.services import submit_approval, decide_approval
        self.iou.refresh_from_db()
        request = submit_approval(source=self.iou, action="iou.approve", requester=self.maker)
        result = decide_approval(approval=request, actor=self.checker)
        self.iou.refresh_from_db()
        return result

    def repay_directly(self):
        from approvals.services import submit_approval, decide_approval
        self.iou.refresh_from_db()
        request = submit_approval(source=self.iou, action="iou.settle", requester=self.receipt_maker,
            payload={"payment_method":"DIRECT_PAYMENT", "amount_received":str(self.iou.total_amount), "receipt_reference":"TEST-RECEIPT"})
        result = decide_approval(approval=request, actor=self.checker)
        self.iou.refresh_from_db()
        return result

    def assert_pending_decision(self, action):
        from approvals.models import ApprovalRequest
        from django.contrib.contenttypes.models import ContentType
        request = ApprovalRequest.objects.get(content_type=ContentType.objects.get_for_model(self.iou), object_id=self.iou.pk, action=action, status="PENDING")
        self.assertFalse(request.decisions.exists())

    def test_partial_save_does_not_account_for_unsaved_approval(self):
        count = Journal.objects.count()
        self.iou.status = "APPROVED"
        self.iou.reason = "Description only"
        self.iou.save(update_fields=["reason"])
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "PENDING")
        self.assertEqual(Journal.objects.count(), count)

    def test_approval_accounting_failure_preserves_pending_status(self):
        with patch(
            "payroll.signals.handle_iou_approval_accounting",
            side_effect=ValidationError("posting failed"),
        ):
            with self.assertRaisesMessage(ValidationError, "posting failed"):
                self.approve()
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "PENDING")
        self.assert_pending_decision("iou.approve")


    def test_direct_payment_accounting_failure_preserves_approved_status(self):
        self.approve()
        with patch(
            "payroll.signals.handle_iou_direct_payment_accounting",
            side_effect=ValidationError("posting failed"),
        ):
            with self.assertRaisesMessage(ValidationError, "posting failed"):
                self.repay_directly()
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "APPROVED")
        self.assert_pending_decision("iou.settle")


    def test_journal_is_rolled_back_if_accounting_audit_fails(self):
        journal_count = Journal.objects.count()
        with patch(
            "payroll.services.payroll_accounting_service.log_accounting_activity",
            side_effect=ValidationError("audit failed"),
        ):
            with self.assertRaisesMessage(ValidationError, "audit failed"):
                self.approve()
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "PENDING")
        self.assertEqual(Journal.objects.count(), journal_count)
        self.assert_pending_decision("iou.approve")


    def test_journal_is_rolled_back_if_model_write_fails(self):
        journal_count = Journal.objects.count()
        with patch.object(
            IOU, "_save_table", side_effect=ValidationError("model write failed")
        ):
            with self.assertRaisesMessage(ValidationError, "model write failed"):
                self.approve()
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "PENDING")
        self.assertEqual(Journal.objects.count(), journal_count)
        self.assert_pending_decision("iou.approve")


    def _close_current_period(self):
        from django.utils import timezone
        today = timezone.localdate()
        year = get_or_create_fiscal_year(today.year, company=self.company)
        period = get_or_create_period(year, today.month, company=self.company)
        from accounting.utils import close_accounting_period
        from approvals.services import decide_approval
        request = close_accounting_period(period, self.maker, reason="Close the test period")
        decide_approval(approval=request, actor=self.checker)

    def test_closed_period_blocks_approval_without_journal_or_status_change(self):
        self._close_current_period()
        journal_count = Journal.objects.count()
        with self.assertRaisesMessage(ValidationError, "closed period"):
            self.approve()
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "PENDING")
        self.assertEqual(Journal.objects.count(), journal_count)
        self.assert_pending_decision("iou.approve")


    def test_closed_period_blocks_direct_repayment_without_status_change(self):
        self.approve()
        self._close_current_period()
        journal_count = Journal.objects.count()
        with self.assertRaisesMessage(ValidationError, "closed period"):
            self.repay_directly()
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "APPROVED")
        self.assertEqual(self.iou.payment_method, "SALARY_DEDUCTION")
        self.assertEqual(Journal.objects.count(), journal_count)
        self.assert_pending_decision("iou.settle")


    def test_direct_repayment_journal_is_rolled_back_if_audit_fails(self):
        self.approve()
        journal_count = Journal.objects.count()
        with patch(
            "payroll.services.payroll_accounting_service.log_accounting_activity",
            side_effect=ValidationError("audit failed"),
        ):
            with self.assertRaisesMessage(ValidationError, "audit failed"):
                self.repay_directly()
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "APPROVED")
        self.assertEqual(Journal.objects.count(), journal_count)
        self.assert_pending_decision("iou.settle")


    def test_successful_approval_and_direct_repayment_post_once_each(self):
        self.approve()
        self.iou.save()
        self.assertEqual(Journal.objects.count(), 1)
        self.repay_directly()
        self.iou.save()
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "PAID")
        journals = Journal.objects.all()
        self.assertEqual(journals.count(), 2)
        for journal in journals:
            self.assertEqual(journal.company_id, self.company.pk)
            self.assertEqual(journal.object_id, self.iou.pk)
            self.assertEqual(journal.status, Journal.JournalStatus.POSTED)
            debit = sum(
                entry.amount for entry in journal.entries.filter(entry_type="DEBIT")
            )
            credit = sum(
                entry.amount for entry in journal.entries.filter(entry_type="CREDIT")
            )
            self.assertEqual(debit, credit)
