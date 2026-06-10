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
            status=status,
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
