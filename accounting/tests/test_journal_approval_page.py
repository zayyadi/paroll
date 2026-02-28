from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounting.models import AccountingPeriod, FiscalYear, Journal, JournalEntry, Account


class JournalApprovalPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="approval-page-admin@test.com",
            password="testpass123",
            first_name="Approval",
            last_name="Admin",
        )
        self.client.force_login(self.user)

        self.fiscal_year = FiscalYear.objects.create(
            year=2026,
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=4,
            name="April 2026",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            is_active=True,
            is_closed=False,
        )
        self.journal = Journal.objects.create(
            description="Approval page render regression",
            date=date(2026, 4, 15),
            period=self.period,
            status=Journal.JournalStatus.PENDING_APPROVAL,
            created_by=self.user,
        )
        debit = Account.objects.create(
            account_number="1000",
            name="Cash",
            type=Account.AccountType.ASSET,
        )
        credit = Account.objects.create(
            account_number="4000",
            name="Revenue",
            type=Account.AccountType.REVENUE,
        )
        JournalEntry.objects.create(
            journal=self.journal,
            account=debit,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=1000,
            memo="Debit entry",
        )
        JournalEntry.objects.create(
            journal=self.journal,
            account=credit,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=1000,
            memo="Credit entry",
        )

    def test_journal_approval_page_renders(self):
        response = self.client.get(
            reverse("accounting:journal_approve", kwargs={"pk": self.journal.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review Journal")
        self.assertContains(response, self.journal.description)

    def test_approve_post_for_non_pending_journal_does_not_500(self):
        self.journal.status = Journal.JournalStatus.APPROVED
        self.journal.save(update_fields=["status"])

        response = self.client.post(
            reverse("accounting:journal_approve", kwargs={"pk": self.journal.pk}),
            {"action": "approve", "reason": "Retry click"},
        )

        self.assertEqual(response.status_code, 302)
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.status, Journal.JournalStatus.APPROVED)
