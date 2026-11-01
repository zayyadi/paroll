from tests.approval_helpers import (
    approve_journal,
)
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounting.models import Account, AccountingPeriod, FiscalYear, Journal, JournalEntry
from company.models import Company


class JournalWorkflowUITests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Journal Workflow UI Co")
        self.user = get_user_model().objects.create_superuser(
            email="journal-ui-admin@test.com",
            password="testpass123",
            first_name="Journal",
            last_name="Admin",
            company=self.company,
            active_company=self.company,
        )
        self.client.force_login(self.user)
        self.fiscal_year = FiscalYear.objects.create(
            company=self.company,
            year=2026,
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            company=self.company,
            fiscal_year=self.fiscal_year,
            period_number=5,
            name="May 2026",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            is_active=True,
            is_closed=False,
        )
        self.cash = Account.objects.create(
            company=self.company,
            account_number="1000",
            name="Cash",
            type=Account.AccountType.ASSET,
        )
        self.revenue = Account.objects.create(
            company=self.company,
            account_number="4000",
            name="Revenue",
            type=Account.AccountType.REVENUE,
        )

    def create_journal(self, status=Journal.JournalStatus.DRAFT, description="Workflow journal"):
        journal = Journal.objects.create(
            company=self.company,
            description=description,
            date=date(2026, 5, 20),
            period=self.period,
            status=Journal.JournalStatus.DRAFT,
            created_by=self.user,
        )
        JournalEntry.objects.create(
            journal=journal,
            account=self.cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=1000,
        )
        JournalEntry.objects.create(
            journal=journal,
            account=self.revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=1000,
        )
        if status != Journal.JournalStatus.DRAFT:
            journal.submit_for_approval()
            if status in (Journal.JournalStatus.APPROVED, Journal.JournalStatus.POSTED):
                approve_journal(journal)
            if status == Journal.JournalStatus.POSTED:
                journal.post(journal.approved_by)
        return journal

    def test_journal_list_exposes_workflow_links(self):
        draft = self.create_journal(description="Editable draft")
        pending = self.create_journal(
            status=Journal.JournalStatus.PENDING_APPROVAL,
            description="Reviewable pending",
        )
        approved = self.create_journal(
            status=Journal.JournalStatus.APPROVED,
            description="Postable approved",
        )
        posted = self.create_journal(
            status=Journal.JournalStatus.POSTED,
            description="Reversible posted",
        )

        response = self.client.get(reverse("accounting:journal_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounting:journal_edit", kwargs={"pk": draft.pk}))
        self.assertContains(response, reverse("accounting:journal_delete", kwargs={"pk": draft.pk}))
        self.assertContains(response, reverse("accounting:journal_submit", kwargs={"pk": draft.pk}))
        self.assertContains(response, reverse("accounting:journal_approve", kwargs={"pk": pending.pk}))
        self.assertContains(response, reverse("accounting:journal_post", kwargs={"pk": approved.pk}))
        self.assertContains(
            response,
            reverse("accounting:journal_reversal_initiation", kwargs={"pk": posted.pk}),
        )

    def test_journal_detail_exposes_delete_for_draft(self):
        journal = self.create_journal()

        response = self.client.get(
            reverse("accounting:journal_detail", kwargs={"pk": journal.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounting:journal_delete", kwargs={"pk": journal.pk}))
        self.assertContains(response, "Delete")
        self.assertContains(response, reverse("accounting:journal_submit", kwargs={"pk": journal.pk}))
        self.assertContains(response, "Submit for Approval")

    def test_journal_edit_page_renders_entry_lines(self):
        journal = self.create_journal(description="Editable line journal")

        response = self.client.get(
            reverse("accounting:journal_edit", kwargs={"pk": journal.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editable line journal")
        self.assertContains(response, "entries-0-account")
        self.assertContains(response, "entries-1-account")

    def test_draft_journal_can_be_deleted(self):
        journal = self.create_journal()

        response = self.client.post(
            reverse("accounting:journal_delete", kwargs={"pk": journal.pk})
        )

        self.assertRedirects(response, reverse("accounting:journal_list"))
        self.assertFalse(Journal.objects.filter(pk=journal.pk).exists())

    def test_draft_journal_can_be_submitted_for_approval(self):
        journal = self.create_journal()

        response = self.client.post(
            reverse("accounting:journal_submit", kwargs={"pk": journal.pk})
        )

        self.assertRedirects(
            response, reverse("accounting:journal_detail", kwargs={"pk": journal.pk})
        )
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.PENDING_APPROVAL)

    def test_non_draft_journal_submit_is_blocked(self):
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)

        response = self.client.post(
            reverse("accounting:journal_submit", kwargs={"pk": journal.pk})
        )

        self.assertRedirects(
            response, reverse("accounting:journal_detail", kwargs={"pk": journal.pk})
        )
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.APPROVED)

    def test_posted_journal_delete_is_blocked(self):
        journal = self.create_journal(status=Journal.JournalStatus.POSTED)

        response = self.client.post(
            reverse("accounting:journal_delete", kwargs={"pk": journal.pk})
        )

        self.assertRedirects(
            response, reverse("accounting:journal_detail", kwargs={"pk": journal.pk})
        )
        self.assertTrue(Journal.objects.filter(pk=journal.pk).exists())

    def test_submission_creates_real_request_and_is_idempotent(self):
        from approvals.models import ApprovalRequest
        journal = self.create_journal()
        url = reverse('accounting:journal_submit', args=[journal.pk])
        self.client.post(url)
        self.client.post(url)
        requests = ApprovalRequest.objects.filter(
            company=self.company, action='journal.approve', object_id=journal.pk)
        self.assertEqual(requests.count(), 1)
        approval = requests.get()
        self.assertEqual(approval.requester_id, self.user.pk)
        self.assertEqual(approval.status, 'PENDING')
        self.assertEqual(approval.events.filter(kind='SUBMITTED').count(), 1)
        response = self.client.get(reverse('accounting:journal_detail', args=[journal.pk]))
        self.assertNotContains(response, 'This is a preview of the current policy.')
        self.assertFalse(response.context['can_submit'])

    def test_pending_journal_without_request_can_be_submitted(self):
        from approvals.models import ApprovalRequest
        journal = self.create_journal(status=Journal.JournalStatus.PENDING_APPROVAL)
        detail_url = reverse('accounting:journal_detail', args=[journal.pk])
        response = self.client.get(detail_url)
        self.assertTrue(response.context['can_submit'])
        self.client.post(reverse('accounting:journal_submit', args=[journal.pk]))
        self.assertTrue(ApprovalRequest.objects.filter(
            action='journal.approve', object_id=journal.pk, requester=self.user,
            status='PENDING').exists())

    def test_submission_failure_rolls_back_draft_status(self):
        from unittest.mock import patch
        from django.core.exceptions import ValidationError
        from approvals.models import ApprovalRequest
        journal = self.create_journal()
        with patch('approvals.services.submit_approval', side_effect=ValidationError('Invalid policy')):
            self.client.post(reverse('accounting:journal_submit', args=[journal.pk]))
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.DRAFT)
        self.assertFalse(ApprovalRequest.objects.filter(action='journal.approve', object_id=journal.pk).exists())

    def test_other_accountant_cannot_submit_as_original_maker(self):
        from approvals.models import ApprovalRequest
        journal = self.create_journal()
        other = get_user_model().objects.create_superuser(
            email='other-journal-ui@test.com', password='x', company=self.company,
            active_company=self.company)
        self.client.force_login(other)
        response = self.client.post(reverse('accounting:journal_submit', args=[journal.pk]))
        self.assertEqual(response.status_code, 403)
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.DRAFT)
        self.assertFalse(ApprovalRequest.objects.filter(action='journal.approve', object_id=journal.pk).exists())

    def test_posting_retry_after_cancellation_creates_new_request(self):
        from accounting.utils import post_journal
        from approvals.models import ApprovalRequest
        from approvals.services import cancel_approval
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)
        original = post_journal(journal, self.user)
        cancel_approval(approval=original, actor=self.user, reason='Revise submission')
        response = self.client.post(reverse('accounting:journal_post', args=[journal.pk]))
        replacement = ApprovalRequest.objects.filter(
            company=self.company, action='accounting.journal.post', status='PENDING').get()
        self.assertNotEqual(replacement.object_id, original.object_id)
        self.assertRedirects(response, reverse('approvals:detail', args=[replacement.pk]))
        self.client.post(reverse('accounting:journal_post', args=[journal.pk]))
        self.assertEqual(ApprovalRequest.objects.filter(
            company=self.company, action='accounting.journal.post', status='PENDING').count(), 1)
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.APPROVED)

    def test_posting_retry_after_rejection_creates_new_request(self):
        from accounting.utils import post_journal
        from approvals.models import ApprovalRequest
        from tests.approval_helpers import reject_request
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)
        original = post_journal(journal, self.user)
        reject_request(original)
        response = self.client.post(reverse('accounting:journal_post', args=[journal.pk]))
        replacement = ApprovalRequest.objects.get(
            company=self.company, action='accounting.journal.post', status='PENDING')
        self.assertNotEqual(replacement.object_id, original.object_id)
        self.assertRedirects(response, reverse('approvals:detail', args=[replacement.pk]))

    def test_explicit_cancelled_posting_key_is_not_silently_replaced(self):
        from accounting.utils import post_journal
        from approvals.models import ApprovalRequest
        from approvals.services import cancel_approval
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)
        original = post_journal(journal, self.user, approval_key='explicit-posting-attempt')
        cancel_approval(approval=original, actor=self.user, reason='Cancel')
        self.client.post(reverse('accounting:journal_post', args=[journal.pk]),
                         {'_approval_key': 'explicit-posting-attempt'})
        self.assertFalse(ApprovalRequest.objects.filter(
            company=self.company, action='accounting.journal.post', status='PENDING').exists())

    def test_posted_journal_cannot_create_another_posting_proposal(self):
        from approvals.models import ApprovalRequest
        journal = self.create_journal(status=Journal.JournalStatus.POSTED)
        self.client.post(reverse('accounting:journal_post', args=[journal.pk]))
        self.assertFalse(ApprovalRequest.objects.filter(
            company=self.company, action='accounting.journal.post', status='PENDING').exists())

    def test_journal_viewer_prioritizes_pending_posting_over_cancelled_attempt(self):
        from accounting.utils import post_journal
        from approvals.services import cancel_approval
        from approvals.workflow import document_workflows
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)
        original = post_journal(journal, self.user)
        cancel_approval(approval=original, actor=self.user, reason='Revise')
        self.client.post(reverse('accounting:journal_post', args=[journal.pk]))
        workflows = document_workflows(journal, self.user)
        self.assertEqual(workflows[0]['approval'].status, 'PENDING')
        self.assertEqual(workflows[0]['approval'].action, 'accounting.journal.post')
        self.assertTrue(any(w['approval'].pk == original.pk for w in workflows))
        response = self.client.get(reverse('accounting:journal_detail', args=[journal.pk]))
        self.assertContains(response, 'This attempt was cancelled.')
        self.assertContains(response, 'Return to journal to submit a new posting request')

    def test_cancelled_posting_view_has_safe_return_path(self):
        from accounting.utils import post_journal
        from approvals.services import cancel_approval
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)
        approval = post_journal(journal, self.user)
        cancel_approval(approval=approval, actor=self.user, reason='Revise')
        response = self.client.get(reverse('approvals:detail', args=[approval.pk]))
        self.assertContains(response, reverse('accounting:journal_detail', args=[journal.pk]))
        self.assertContains(response, 'This attempt was cancelled.')
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.APPROVED)

    def test_revocation_is_independent_and_returns_journal_to_draft(self):
        from approvals.models import ApprovalRequest
        from approvals.services import decide_approval
        from django.core.exceptions import PermissionDenied
        from tests.approval_helpers import approve_request
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)
        original_grant = journal.approval_request_id
        response = self.client.post(reverse('accounting:journal_revoke_approval', args=[journal.pk]),
                                    {'reason': 'Withdraw approval for correction'})
        approval = ApprovalRequest.objects.get(action='journal.revoke_approval', object_id=journal.pk)
        self.assertRedirects(response, reverse('approvals:detail', args=[approval.pk]))
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.APPROVED)
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=approval, actor=self.user)
        approve_request(approval)
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.DRAFT)
        self.assertIsNone(journal.approval_request_id)
        self.assertIsNone(journal.approved_by_id)
        self.assertIsNone(journal.approved_at)
        self.assertEqual(ApprovalRequest.objects.get(pk=original_grant).status, 'APPROVED')
        self.assertEqual(approval.events.filter(kind='APPROVAL_REVOKED').count(), 1)

    def test_revoked_journal_can_be_resubmitted_without_reusing_original_grant(self):
        from approvals.models import ApprovalRequest
        from tests.approval_helpers import approve_request
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)
        original_grant = journal.approval_request_id
        self.client.post(reverse('accounting:journal_revoke_approval', args=[journal.pk]), {'reason': 'Correction'})
        revoke = ApprovalRequest.objects.get(action='journal.revoke_approval', object_id=journal.pk)
        approve_request(revoke)
        self.client.post(reverse('accounting:journal_submit', args=[journal.pk]))
        grant = ApprovalRequest.objects.get(action='journal.approve', object_id=journal.pk, status='PENDING')
        self.assertNotEqual(grant.pk, original_grant)
        approve_request(grant)
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.APPROVED)
        self.assertEqual(journal.approval_request_id, grant.pk)

    def test_revocation_rejects_posted_journal_and_missing_reason(self):
        from approvals.models import ApprovalRequest
        for journal in (self.create_journal(status=Journal.JournalStatus.POSTED),
                        self.create_journal(status=Journal.JournalStatus.APPROVED)):
            payload = {'reason': 'Withdraw'} if journal.status == 'POSTED' else {'reason': ' '}
            self.client.post(reverse('accounting:journal_revoke_approval', args=[journal.pk]), payload)
            self.assertFalse(ApprovalRequest.objects.filter(
                action='journal.revoke_approval', object_id=journal.pk).exists())

    def test_revocation_get_does_not_change_state(self):
        from approvals.models import ApprovalRequest
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)
        self.client.get(reverse('accounting:journal_revoke_approval', args=[journal.pk]))
        self.assertFalse(ApprovalRequest.objects.filter(
            action='journal.revoke_approval', object_id=journal.pk).exists())

    def test_pending_posting_cannot_execute_after_revocation(self):
        from accounting.utils import post_journal
        from approvals.models import ApprovalRequest
        from django.core.exceptions import ValidationError
        from tests.approval_helpers import approve_request
        journal = self.create_journal(status=Journal.JournalStatus.APPROVED)
        posting = post_journal(journal, self.user)
        self.client.post(reverse('accounting:journal_revoke_approval', args=[journal.pk]), {'reason': 'Correction'})
        revoke = ApprovalRequest.objects.get(action='journal.revoke_approval', object_id=journal.pk)
        approve_request(revoke)
        with self.assertRaises(ValidationError):
            approve_request(posting)
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.DRAFT)
