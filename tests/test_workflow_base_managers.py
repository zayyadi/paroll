"""Framework base managers must enforce the same decisions as public CRUD."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounting.models import AccountingPeriod, Journal
from accounting.tests.fixtures import JournalFactory, get_test_company
from payroll.models import Appraisal, AppraisalAssignment, LeaveRequest, Payroll, Rating, Review, Metric
from tests.approval_helpers import approval_user
from company.models import Company


class WorkflowBaseManagerTests(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.maker = approval_user(self.company, ["accounting.change_journal"])
        self.employee_user = approval_user(self.company)
        self.employee = self.employee_user.employee_user
        self.employee.company = self.company
        self.employee.save(update_fields=["company"])
        self.salary = Payroll.objects.create(company=self.company, basic_salary=Decimal("50000"))
        self.employee.employee_pay = self.salary
        self.employee.save(update_fields=["employee_pay"])

    def test_base_manager_cannot_approve_unreviewed_journal(self):
        journal = JournalFactory.create_journal_with_entries(user=self.maker)
        with self.assertRaises(ValidationError):
            Journal._base_manager.filter(pk=journal.pk).update(status="APPROVED")
        journal.refresh_from_db()
        self.assertEqual(journal.status, "DRAFT")

    def test_base_manager_cannot_close_accounting_period(self):
        journal = JournalFactory.create_journal_with_entries(user=self.maker)
        with self.assertRaises(ValidationError):
            AccountingPeriod._base_manager.filter(pk=journal.period_id).update(is_closed=True)
        journal.period.refresh_from_db()
        self.assertFalse(journal.period.is_closed)

    def test_base_manager_cannot_change_assigned_salary(self):
        with self.assertRaises(ValidationError):
            Payroll._base_manager.filter(pk=self.salary.pk).update(basic_salary=Decimal("90000"))
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.basic_salary, Decimal("50000"))

    def test_base_manager_cannot_replace_employee_salary(self):
        replacement = Payroll.objects.create(company=self.company, basic_salary=Decimal("90000"))
        with self.assertRaises(ValidationError):
            type(self.employee)._base_manager.filter(pk=self.employee.pk).update(employee_pay=replacement)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.employee_pay_id, self.salary.pk)

    def _review(self):
        reviewer = self.maker.employee_user
        reviewer.company = self.company
        reviewer.save(update_fields=["company"])
        appraisal = Appraisal.objects.create(company=self.company, name="Protected review", start_date=date(2026,1,1), end_date=date(2026,12,31))
        AppraisalAssignment.objects.create(appraisal=appraisal, appraisee=self.employee, appraiser=reviewer)
        return Review.objects.create(appraisal=appraisal, employee=self.employee, reviewer=reviewer)

    def test_base_manager_cannot_publish_reviewer_draft(self):
        review = self._review()
        with self.assertRaises(ValidationError):
            Review._base_manager.filter(pk=review.pk).update(status="PUBLISHED")
        review.refresh_from_db()
        self.assertEqual(review.status, "DRAFT")

    def test_base_manager_cannot_change_submitted_rating(self):
        review = self._review()
        rating = Rating.objects.create(review=review, metric=Metric.objects.create(name="Delivery"), rating=4)
        review.status = "SUBMITTED"
        review.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            Rating._base_manager.filter(pk=rating.pk).update(rating=1)
        rating.refresh_from_db()
        self.assertEqual(rating.rating, 4)

    def test_base_salary_manager_is_unfiltered(self):
        self.salary.status = "inactive"
        self.salary.save(update_fields=["status"])
        self.assertFalse(Payroll.objects.filter(pk=self.salary.pk).exists())
        self.assertTrue(Payroll._base_manager.filter(pk=self.salary.pk).exists())

    def test_base_manager_cannot_approve_inventory_document(self):
        from inventory.models import InventoryDocument
        document = InventoryDocument.objects.create(company=self.company, document_type="OPENING_STOCK", requested_by=self.maker)
        with self.assertRaises(ValidationError):
            InventoryDocument._base_manager.filter(pk=document.pk).update(status="APPROVED")
        document.refresh_from_db()
        self.assertEqual(document.status, "DRAFT")

    def test_base_manager_cannot_approve_employee_leave(self):
        leave = LeaveRequest.objects.create(employee=self.employee, requested_by=self.employee_user, leave_type="CASUAL", start_date=date(2026,10,8), end_date=date(2026,10,9), reason="Requested time off")
        with self.assertRaises((ValidationError, PermissionDenied)):
            LeaveRequest._base_manager.filter(pk=leave.pk).update(status="APPROVED")
        leave.refresh_from_db()
        self.assertEqual(leave.status, "PENDING")

    def test_base_manager_cannot_rewrite_posted_ledger_entry(self):
        from accounting.models import JournalEntry
        journal = JournalFactory.create_posted_journal(user=self.maker)
        entry = journal.entries.first()
        original = entry.amount
        with self.assertRaises(ValidationError):
            JournalEntry._base_manager.filter(pk=entry.pk).update(amount=Decimal("90000"))
        entry.refresh_from_db()
        self.assertEqual(entry.amount, original)

    def test_base_manager_cannot_rewrite_proposal_currency(self):
        from accounting.utils import post_journal
        from company.models import ActionProposal
        journal = JournalFactory.create_journal_with_entries(user=self.maker)
        request = post_journal(journal, self.maker)
        with self.assertRaises(ValidationError):
            ActionProposal._base_manager.filter(pk=request.object_id).update(currency="USD")
        request.source.refresh_from_db()
        self.assertEqual(request.source.currency, "NGN")

    def test_bulk_conflict_cannot_replace_assigned_salary(self):
        replacement = Payroll(pk=self.salary.pk, company=self.company, basic_salary=Decimal("90000"))
        with self.assertRaises((ValidationError, PermissionDenied)):
            Payroll._base_manager.bulk_create([replacement], update_conflicts=True, update_fields=["basic_salary"], unique_fields=["id"])
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.basic_salary, Decimal("50000"))

    def test_bulk_conflict_cannot_replace_review_narrative(self):
        review = self._review()
        review.status = "SUBMITTED"
        review.save(update_fields=["status"])
        replacement = Review(pk=review.pk, appraisal=review.appraisal, employee=review.employee, reviewer=review.reviewer, self_assessment="Unreviewed replacement")
        with self.assertRaises(ValidationError):
            Review._base_manager.bulk_create([replacement], update_conflicts=True, update_fields=["self_assessment"], unique_fields=["id"])
        review.refresh_from_db()
        self.assertFalse(review.self_assessment)

    def test_bulk_conflict_cannot_change_posted_ledger_using_draft_parent(self):
        from accounting.models import JournalEntry
        posted = JournalFactory.create_posted_journal(user=self.maker)
        draft = JournalFactory.create_journal_with_entries(user=self.maker)
        entry = posted.entries.first()
        original = entry.amount
        replacement = JournalEntry(pk=entry.pk, journal=draft, account=entry.account, entry_type=entry.entry_type, amount=Decimal("90000"))
        with self.assertRaises(ValidationError):
            JournalEntry._base_manager.bulk_create([replacement], update_conflicts=True, update_fields=["amount"], unique_fields=["id"])
        entry.refresh_from_db()
        self.assertEqual(entry.amount, original)

    def test_bulk_new_run_cannot_start_approved_without_workflow(self):
        from payroll.models import PayrollRun
        with self.assertRaises(ValidationError):
            PayrollRun._base_manager.bulk_create([PayrollRun(company=self.company, name="Unreviewed approved run", paydays=date(2026,10,1), status="approved")])
