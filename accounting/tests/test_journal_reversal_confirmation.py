from tests.approval_helpers import (
    approve_journal,
    post_journal as approved_post_journal,
)
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounting.models import Account, AccountingPeriod, FiscalYear, Journal, JournalEntry
from company.models import Company


User = get_user_model()


class JournalReversalConfirmationTests(TestCase):
    def test_confirmation_page_renders_without_created_or_posted_users(self):
        company = Company.objects.create(name="Reversal Confirmation Co")
        user = User.objects.create_superuser(
            email="reversal-admin@example.com",
            password="password123",
            company=company,
            active_company=company,
        )
        fiscal_year = FiscalYear.objects.create(
            company=company,
            year=2026,
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        period = AccountingPeriod.objects.create(
            company=company,
            fiscal_year=fiscal_year,
            period_number=1,
            name="January 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            is_active=True,
        )
        cash = Account.objects.create(
            company=company,
            name="Cash",
            account_number="1000",
            type=Account.AccountType.ASSET,
        )
        revenue = Account.objects.create(
            company=company,
            name="Revenue",
            account_number="4000",
            type=Account.AccountType.REVENUE,
        )
        journal = Journal.objects.create(
            company=company,
            period=period,
            date=date(2026, 1, 15),
            description="Imported posted journal",
            status=Journal.JournalStatus.DRAFT,
        )
        JournalEntry.objects.create(
            journal=journal,
            account=cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount="100.00",
        )
        JournalEntry.objects.create(
            journal=journal,
            account=revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount="100.00",
        )
        journal.submit_for_approval()
        approve_journal(journal)
        approved_post_journal(journal)
        self.client.force_login(user)
        session = self.client.session
        session["reversal_data"] = {
            "journal_id": journal.pk,
            "reversal_type": "full",
            "reason": "Imported journal correction",
        }
        session.save()

        response = self.client.get(
            reverse("accounting:journal_reversal_confirm", kwargs={"pk": journal.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Imported posted journal")
        # Legacy records can omit actors; exercise that rendering state without
        # forging a posted record or bypassing the approval service.
        from django.template.loader import render_to_string
        journal.created_by = None
        journal.posted_by = None
        legacy_content = render_to_string("accounting/journal_reversal_confirmation.html", {"journal": journal, "reversal_data": session["reversal_data"]}, request=response.wsgi_request)
        self.assertIn("Not recorded", legacy_content)
