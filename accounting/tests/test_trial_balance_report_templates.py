from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from accounting.tests.fixtures import AccountFactory, JournalFactory


class TrialBalanceReportTemplateTests(TestCase):
    def setUp(self):
        self.auditor = get_user_model().objects.create_user(
            email="trial-balance-auditor@example.com",
            password="password123",
            first_name="Trial",
            last_name="Auditor",
        )
        auditor_group, _ = Group.objects.get_or_create(name="Auditor")
        self.auditor.groups.add(auditor_group)

        AccountFactory.create_chart_of_accounts()
        self.journal = JournalFactory.create_journal_with_entries(
            "Trial Balance Journal", 1000, user=self.auditor
        )
        self.journal.submit_for_approval()
        self.journal.approve(self.auditor)
        self.journal.post(self.auditor)
        self.period = self.journal.period
        self.client.force_login(self.auditor)

    def test_trial_balance_page_renders_totals_without_template_sum_filter(self):
        response = self.client.get(reverse("accounting:trial_balance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trial Balance")
        self.assertContains(response, "Total Debits")
        self.assertContains(response, "1,000.00")

    def test_period_detail_renders_trial_balance_summary(self):
        response = self.client.get(
            reverse("accounting:period_detail", kwargs={"pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trial Balance Summary")
        self.assertContains(response, "1,000.00")

    def test_trial_balance_pdf_template_renders_totals_without_sum_filter(self):
        response = self.client.get(reverse("accounting:trial_balance"))
        context = response.context

        rendered = render_to_string(
            "accounting/reports/pdf/trial_balance_pdf.html",
            {
                "trial_balance": context["trial_balance"],
                "total_debits": context["total_debits"],
                "total_credits": context["total_credits"],
                "is_balanced": context["is_balanced"],
                "report_title": "Trial Balance - Current",
            },
        )

        self.assertIn("Total Debits", rendered)
        self.assertIn("1,000.00", rendered)

    def test_trial_balance_pdf_endpoint_renders(self):
        response = self.client.get(reverse("accounting:trial_balance_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_balance_sheet_report_renders(self):
        response = self.client.get(reverse("accounting:balance_sheet"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Balance Sheet")
        self.assertContains(response, "Total Assets")

    def test_income_statement_report_renders(self):
        response = self.client.get(reverse("accounting:income_statement"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Income Statement")
        self.assertContains(response, "Net Income")

    def test_general_ledger_report_renders(self):
        response = self.client.get(reverse("accounting:general_ledger"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "General Ledger")
        self.assertContains(response, "Trial Balance Journal")
