from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import date
from payroll.models import Payroll, PayrollRun, PayrollEntry, PayrollRunEntry
from payroll.models.payroll import BankPaymentFile
from company.models import Company

User = get_user_model()


def mark_submitted(*, payment_file, reference_number='BANK-FIXTURE'):
    """Complete genuine independent review for legacy bank integrity fixtures."""
    from payroll.services.bank_payment_service import mark_submitted as submit
    from tests.approval_helpers import approval_user, approve_request
    from approvals.proposals import _request_actor
    maker = payment_file.created_by or approval_user(payment_file.company, ['payroll.change_payrollrun'])
    token = _request_actor.set(maker)
    try:
        return approve_request(submit(payment_file=payment_file, reference_number=reference_number))
    finally:
        _request_actor.reset(token)


def mark_confirmed(*, payment_file):
    """Resume the approved instruction under its actual final checker."""
    from payroll.services.bank_payment_service import mark_confirmed as confirm
    from approvals.models import ApprovalRequest
    from approvals.proposals import _request_actor
    from tests.approval_helpers import approval_user
    request = ApprovalRequest.objects.filter(action='bank_payment.submit', object_id=payment_file.pk, company=payment_file.company, status='APPROVED').order_by('-pk').first()
    checker = request.decisions.filter(decision='APPROVE').order_by('-stage').first().actor if request else approval_user(payment_file.company, ['payroll.change_payrollrun'])
    token = _request_actor.set(checker)
    try:
        return confirm(payment_file=payment_file)
    finally:
        _request_actor.reset(token)


class BankPaymentTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        self.user = User.objects.create_user(
            email="hr@test.com", password="testpass123", is_staff=True
        )
        self.user.active_company = self.company
        self.user.save()
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.first_name = "John"
        self.employee.last_name = "Doe"
        self.employee.bank = "Zenith"
        self.employee.bank_account_number = "1234567890"
        self.salary = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("1200000.00"),
        )
        self.employee.employee_pay = self.salary
        self.employee.save()
        self.run = PayrollRun.objects.create(
            company=self.company, name="June 2026",
            paydays=date(2026, 6, 1),
        )
        self.entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee,
        )
        self.entry.netpay = Decimal("85000.00")
        self.entry.save(update_fields=["netpay"])
        PayrollRunEntry.objects.create(
            payroll_run=self.run, payroll_entry=self.entry,
        )
        from tests.approval_helpers import approve_source
        approve_source(self.run, 'payroll.lock')

    def test_generate_nip_file(self):
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        self.assertEqual(payment.bank_name, "Zenith")
        self.assertEqual(payment.total_records, 1)
        self.assertEqual(payment.status, "GENERATED")

    def test_mark_submitted(self):
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        mark_submitted(payment_file=payment, reference_number="REF123")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "SUBMITTED")
        self.assertEqual(payment.reference_number, "REF123")

    def test_mark_confirmed(self):
        from payroll.services.bank_payment_service import (
            generate_nip_file
        )
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        mark_submitted(payment_file=payment)
        mark_confirmed(payment_file=payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "CONFIRMED")

    def test_tenant_isolation(self):
        other_company = Company.objects.create(name="Other Co")
        self.assertFalse(
            BankPaymentFile.objects.filter(company=other_company).exists()
        )

    def test_export_total_and_beneficiary_bank_are_exact(self):
        import csv
        from io import StringIO
        from payroll.services.bank_payment_service import generate_nip_file
        self.employee.bank = "GTB"
        self.employee.save(update_fields=["bank"])
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        rows = list(csv.reader(StringIO(payment.file.read().decode("utf-8"))))
        self.assertEqual(rows[4][2], "058")
        self.assertEqual(payment.total_amount, sum(Decimal(row[3]) for row in rows[4:]))

    def test_open_run_cannot_be_submitted(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        open_run = PayrollRun.all_objects.create(
            company=self.company, name="Open payment run", paydays=date(2026, 7, 1)
        )
        payment.payroll_run = open_run
        payment.save(update_fields=["payroll_run"])
        with self.assertRaises(ValidationError):
            mark_submitted(payment_file=payment)

    def test_confirmation_requires_submission(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        with self.assertRaises(ValidationError):
            mark_confirmed(payment_file=payment)

    def test_submitted_file_cannot_be_changed_through_stale_instance(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        stale = BankPaymentFile.objects.get(pk=payment.pk)
        mark_submitted(payment_file=payment)
        stale.total_amount = Decimal("1.00")
        with self.assertRaises(ValidationError):
            stale.save()

    def test_missing_bank_account_cannot_silently_omit_salary(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        self.employee.bank_account_number = ""
        self.employee.save(update_fields=["bank_account_number"])
        with self.assertRaises(ValidationError):
            generate_nip_file(payroll_run=self.run, bank_code="057")

    def test_complete_confirmation_marks_run_paid_once(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        mark_submitted(payment_file=payment)
        mark_confirmed(payment_file=payment)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, PayrollRun.Status.PAID)
        with self.assertRaises(ValidationError):
            mark_submitted(payment_file=payment)

    def test_altered_export_cannot_confirm_or_mark_run_paid(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        mark_submitted(payment_file=payment)
        with payment.file.open("rb") as exported:
            altered = exported.read().replace(str(payment.total_amount).encode("utf-8"), b"1.00")
        with payment.file.storage.open(payment.file.name, "wb") as exported:
            exported.write(altered)
        with self.assertRaises(ValidationError):
            mark_confirmed(payment_file=payment)
        payment.refresh_from_db()
        self.run.refresh_from_db()
        self.assertEqual(payment.status, "SUBMITTED")
        self.assertEqual(self.run.status, PayrollRun.Status.LOCKED)

    def test_second_submission_cannot_duplicate_payroll_payout(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        first = generate_nip_file(payroll_run=self.run, bank_code="057")
        second = generate_nip_file(payroll_run=self.run, bank_code="057")
        mark_submitted(payment_file=first)
        with self.assertRaises(ValidationError):
            mark_submitted(payment_file=second)
        second.refresh_from_db()
        self.assertEqual(second.status, "GENERATED")

    def test_changed_employee_account_invalidates_generated_snapshot(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        self.employee.bank_account_number = "9999999999"
        self.employee.save(update_fields=["bank_account_number"])
        with self.assertRaises(ValidationError):
            mark_submitted(payment_file=payment)

    def test_payroll_paid_transition_failure_rolls_back_confirmation(self):
        from unittest.mock import patch
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        mark_submitted(payment_file=payment)
        with patch.object(PayrollRun, "mark_paid", side_effect=RuntimeError("injected save failure")):
            with self.assertRaises(RuntimeError):
                mark_confirmed(payment_file=payment)
        payment.refresh_from_db()
        self.run.refresh_from_db()
        self.assertEqual(payment.status, "SUBMITTED")
        self.assertIsNone(payment.confirmed_at)
        self.assertEqual(self.run.status, PayrollRun.Status.LOCKED)

    def test_consistent_totals_cannot_hide_omitted_employee(self):
        import csv
        from io import StringIO
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        with payment.file.open("rb") as exported:
            rows = list(csv.reader(StringIO(exported.read().decode("utf-8"))))
        output = StringIO()
        csv.writer(output).writerows(rows[:4])
        with payment.file.storage.open(payment.file.name, "wb") as exported:
            exported.write(output.getvalue().encode("utf-8"))
        payment.total_amount = Decimal("0.00")
        payment.total_records = 0
        payment.save(update_fields=["total_amount", "total_records"])
        with self.assertRaises(ValidationError):
            mark_submitted(payment_file=payment)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, PayrollRun.Status.LOCKED)

    def test_model_save_cannot_skip_submission(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        payment.status = "CONFIRMED"
        with self.assertRaises(ValidationError):
            payment.save(update_fields=["status"])

    def test_bank_review_shows_recipients_and_retains_approved_payroll_terms(self):
        from payroll.services.bank_payment_service import generate_nip_file
        from payroll.financial_approval_actions import bank_snapshot, change_salary
        from tests.approval_helpers import approval_user, approve_request
        payment = generate_nip_file(payroll_run=self.run, bank_code='057')
        original = bank_snapshot(payment)
        self.assertEqual(original['recipients'][0]['account_number'], '1234567890')
        self.assertEqual(Decimal(original['recipients'][0]['amount']), payment.total_amount)
        finance = approval_user(self.company, ['payroll.change_payroll'])
        approve_request(change_salary(employee=self.employee, basic_salary=Decimal('1500000'), user=finance))
        latest = bank_snapshot(payment)
        self.assertEqual(latest['payroll'], original['payroll'])
        self.assertEqual(latest['recipients'], original['recipients'])


class BankPaymentWriteBoundaryTest(TestCase):
    setUp = BankPaymentTest.setUp
    def test_direct_submission_cannot_bypass_file_validation(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        payment.status = "SUBMITTED"
        with self.assertRaises(ValidationError):
            payment.save(update_fields=["status"])

    def test_queryset_cannot_modify_or_hide_submitted_payment(self):
        from django.core.exceptions import ValidationError
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        mark_submitted(payment_file=payment)
        with self.assertRaises(ValidationError):
            BankPaymentFile.all_objects.filter(pk=payment.pk).update(total_amount=1)
        with self.assertRaises(ValidationError):
            BankPaymentFile.objects.filter(pk=payment.pk).delete()
