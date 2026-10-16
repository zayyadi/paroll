"""Regressions for source membership and payroll lifecycle integrity."""
from tests.approval_helpers import (
    approve_source,
)
from datetime import date
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounting.tests import test_payroll_postings as posting_tests
from django.test import TransactionTestCase
from payroll.models import PayrollRun, PayrollRunEntry


class PayrollRunIntegrityTests(posting_tests.PayrollClosePostingTests):
    def _open_run(self, entry):
        run = PayrollRun.objects.create(
            company=self.company, name="Integrity run", paydays=date(2026, 10, 1), is_active=True
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        return run

    def test_inactive_run_close_still_creates_source_journal(self):
        from accounting.models import Journal
        from django.contrib.contenttypes.models import ContentType
        _, _, entry = self._create_employee_stack()
        run = self._open_run(entry)
        run.is_active = False
        run.save(update_fields=["is_active"])
        approve_source(run, "payroll.lock")
        self.assertTrue(Journal.objects.filter(
            content_type=ContentType.objects.get_for_model(PayrollRun), object_id=run.pk,
            status=Journal.JournalStatus.POSTED,
        ).exists())

    def test_partial_save_does_not_post_unsaved_close(self):
        from accounting.models import Journal
        _, _, entry = self._create_employee_stack()
        run = self._open_run(entry)
        count = Journal.objects.count()
        run.closed = True
        run.name = "Description only"
        run.save(update_fields=["name"])
        run.refresh_from_db()
        self.assertFalse(run.closed)
        self.assertEqual(Journal.objects.count(), count)

    def test_employee_cannot_be_counted_twice_in_same_run(self):
        _, _, entry = self._create_employee_stack()
        run = self._open_run(entry)
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        self.assertEqual(run.payroll_run_entries.count(), 1)

    def test_membership_rejects_other_company_employee(self):
        from company.models import Company
        _, _, entry = self._create_employee_stack()
        other = Company.objects.create(name="Other company")
        run = PayrollRun.objects.create(
            company=other, name="Other run", paydays=date(2026, 10, 1)
        )
        with self.assertRaises(ValidationError):
            PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        self.assertFalse(run.payroll_run_entries.exists())

    def test_locked_run_rejects_new_membership(self):
        _, _, first = self._create_employee_stack()
        run = self._open_run(first)
        approve_source(run, "payroll.lock")
        _, _, second = self._create_employee_stack()
        with self.assertRaises(ValidationError):
            PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=second)
        self.assertEqual(run.payroll_run_entries.count(), 1)

    def test_bulk_membership_rejects_cross_company_employee(self):
        from company.models import Company
        _, _, entry = self._create_employee_stack()
        other = Company.objects.create(name="Bulk other")
        run = PayrollRun.objects.create(company=other, name="Bulk run", paydays=date(2026, 10, 1))
        with self.assertRaises(ValidationError):
            PayrollRunEntry.objects.bulk_create([PayrollRunEntry(payroll_run=run, payroll_entry=entry)])
        self.assertFalse(run.payroll_run_entries.exists())

    def test_bulk_membership_rejects_duplicate_employee(self):
        _, _, entry = self._create_employee_stack()
        run = PayrollRun.objects.create(company=self.company, name="Bulk run", paydays=date(2026, 10, 1))
        with self.assertRaises(ValidationError):
            PayrollRunEntry.objects.bulk_create([
                PayrollRunEntry(payroll_run=run, payroll_entry=entry),
                PayrollRunEntry(payroll_run=run, payroll_entry=entry),
            ])
        self.assertFalse(run.payroll_run_entries.exists())

    def test_locked_membership_rejects_model_and_queryset_delete(self):
        _, _, entry = self._create_employee_stack()
        run = self._open_run(entry)
        membership = run.payroll_run_entries.get()
        approve_source(run, "payroll.lock")
        with self.assertRaises(ValidationError):
            membership.delete()
        with self.assertRaises(ValidationError):
            run.payroll_run_entries.all().delete()
        self.assertEqual(run.payroll_run_entries.count(), 1)

    def test_locked_payroll_amount_rejects_model_save(self):
        _, _, entry = self._create_employee_stack()
        run = self._open_run(entry)
        approve_source(run, "payroll.lock")
        entry.status = "inactive"
        with self.assertRaises(ValidationError):
            entry.save()

    def test_locked_payroll_amount_rejects_queryset_update(self):
        from payroll.models import PayrollEntry
        _, _, entry = self._create_employee_stack()
        run = self._open_run(entry)
        approve_source(run, "payroll.lock")
        with self.assertRaises(ValidationError):
            PayrollEntry.all_objects.filter(pk=entry.pk).update(netpay=1)

    def test_locked_run_cannot_be_reopened_by_queryset_update(self):
        _, _, entry = self._create_employee_stack()
        run = self._open_run(entry)
        approve_source(run, "payroll.lock")
        with self.assertRaises(ValidationError):
            PayrollRun.all_objects.filter(pk=run.pk).update(closed=False, status="draft")

    def test_employee_cascade_cannot_delete_locked_payroll(self):
        _, employee, entry = self._create_employee_stack()
        run = self._open_run(entry)
        approve_source(run, "payroll.lock")
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                type(employee).objects.filter(pk=employee.pk).delete()
        self.assertEqual(run.payroll_run_entries.count(), 1)

    def test_locked_run_cannot_be_reopened_by_partial_save(self):
        _, _, entry = self._create_employee_stack()
        run = self._open_run(entry)
        approve_source(run, "payroll.lock")
        run.status = PayrollRun.Status.DRAFT
        run.closed = False
        with self.assertRaises(ValidationError):
            run.save(update_fields=["status", "closed"])
        run.refresh_from_db()
        self.assertTrue(run.is_locked)



class PayrollSaveAtomicityTests(TransactionTestCase):
    setUp = posting_tests.PayrollClosePostingTests.setUp
    _create_employee_stack = posting_tests.PayrollClosePostingTests._create_employee_stack
    _open_run = PayrollRunIntegrityTests._open_run

    def test_run_and_posting_roll_back_together_on_save_failure(self):
        from accounting.models import Journal
        from django.contrib.contenttypes.models import ContentType
        _, _, entry = self._create_employee_stack()
        run = self._open_run(entry)
        with patch.object(PayrollRun, "_save_table", side_effect=RuntimeError("injected save failure")):
            with self.assertRaises(RuntimeError):
                approve_source(run, "payroll.lock")
        run.refresh_from_db()
        self.assertFalse(run.closed)
        self.assertFalse(Journal.objects.filter(
            content_type=ContentType.objects.get_for_model(PayrollRun), object_id=run.pk
        ).exists())
