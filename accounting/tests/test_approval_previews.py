"""Independent checkers review financial values before a business effect occurs."""
from django.test import TestCase
from django.urls import reverse

from approvals.presentation import request_context
from approvals.services import submit_approval
from accounting.tests.fixtures import JournalFactory
from tests.approval_helpers import approval_user


class JournalApprovalPreviewTests(TestCase):
    def setUp(self):
        self.journal = JournalFactory.create_journal_with_entries("Reviewed ledger evidence", amount=1000)
        self.journal.submit_for_approval()
        self.approval = submit_approval(source=self.journal, action="journal.approve", requester=self.journal.created_by)
        self.checker = approval_user(self.journal.company, ["accounting.change_journal"])

    def test_web_checker_sees_bound_journal_lines_before_approval(self):
        self.client.force_login(self.checker)
        response = self.client.get(reverse("approvals:detail", args=[self.approval.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reviewed ledger evidence")
        self.assertContains(response, "1000")
        self.assertContains(response, "DEBIT")
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.status, "PENDING_APPROVAL")

    def test_api_checker_sees_values_without_raw_record_metadata(self):
        self.client.force_login(self.checker)
        response = self.client.get(reverse("approval_api:detail", args=[self.approval.pk]))
        self.assertEqual(response.status_code, 200)
        fields = response.json()["fields"]
        self.assertTrue(any("1000" in item["value"] for item in fields))
        self.assertFalse(any(item["label"] in {"Id", "Company id", "Created by id"} for item in fields))

    def test_no_viewer_context_discloses_no_business_fields(self):
        self.assertEqual(request_context(self.approval)["business_fields"], [])

    def test_partial_reversal_preview_uses_decoded_reviewed_amounts(self):
        from decimal import Decimal
        from approvals.proposals import encode_value
        from approvals.presentation import business_fields
        encoded = encode_value({"amounts": {7: Decimal("40.00")}})
        self.assertEqual(business_fields(encoded, company=self.journal.company), [("Amounts / 7", "40.00")])
