from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounting.models import Account, FinancialReportDefinition, FinancialReportLine
from accounting.reporting import build_financial_report
from accounting.utils import create_journal_with_entries
from company.models import Company, CompanyMembership


User = get_user_model()


class FinancialReportDesignerTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Report Design Co")
        self.other_company = Company.objects.create(name="Other Report Co")
        self.user = User.objects.create_superuser(
            email="report-designer@example.com",
            password="password123",
            first_name="Report",
            last_name="Designer",
            company=self.company,
            active_company=self.company,
        )
        CompanyMembership.objects.get_or_create(
            user=self.user,
            company=self.company,
            defaults={"role": CompanyMembership.ROLE_OWNER, "is_default": True},
        )
        self.client.force_login(self.user)

        self.cash = self._account("Bank", "1000", Account.AccountType.ASSET)
        self.inventory = self._account("Inventory", "1200", Account.AccountType.ASSET)
        self.sales = self._account("Wholesale Sales", "4100", Account.AccountType.REVENUE)
        self.cogs = self._account("Cost of Goods Sold", "5100", Account.AccountType.EXPENSE)
        self.other_sales = Account.objects.create(
            company=self.other_company,
            name="Other Sales",
            account_number="4100",
            type=Account.AccountType.REVENUE,
        )

    def _account(self, name, number, account_type):
        return Account.objects.create(
            company=self.company,
            name=name,
            account_number=number,
            type=account_type,
        )

    def test_report_builder_sums_selected_company_accounts_into_designed_lines(self):
        create_journal_with_entries(
            company=self.company,
            date=date(2026, 5, 15),
            description="Wholesale sale",
            entries=[
                {"account": self.cash, "entry_type": "DEBIT", "amount": Decimal("1075.00")},
                {"account": self.sales, "entry_type": "CREDIT", "amount": Decimal("1000.00")},
                {"account": self.inventory, "entry_type": "CREDIT", "amount": Decimal("400.00")},
                {"account": self.cogs, "entry_type": "DEBIT", "amount": Decimal("400.00")},
                {"account": self.cash, "entry_type": "CREDIT", "amount": Decimal("75.00")},
            ],
            auto_post=True,
            validate_balances=False,
        )
        definition = FinancialReportDefinition.objects.create(
            company=self.company,
            name="Wholesale P&L",
            code="WH-PNL",
            report_type=FinancialReportDefinition.ReportType.PROFIT_LOSS,
        )
        revenue_line = FinancialReportLine.objects.create(
            report=definition,
            line_number=100,
            row_code="REV",
            label="Revenue",
        )
        revenue_line.accounts.add(self.sales, self.other_sales)
        cogs_line = FinancialReportLine.objects.create(
            report=definition,
            line_number=200,
            row_code="COGS",
            label="Cost of Goods Sold",
        )
        cogs_line.accounts.add(self.cogs)
        gross_profit_line = FinancialReportLine.objects.create(
            report=definition,
            line_number=300,
            row_code="GROSS",
            label="Gross Profit",
            line_type=FinancialReportLine.LineType.FORMULA,
            formula="REV-COGS",
        )

        report = build_financial_report(definition)

        self.assertEqual(report["rows"][0]["amount"], Decimal("1000.00"))
        self.assertEqual(report["rows"][1]["amount"], Decimal("400.00"))
        self.assertEqual(report["rows"][2]["line"], gross_profit_line)
        self.assertEqual(report["rows"][2]["amount"], Decimal("600.00"))
        self.assertEqual(report["total"], Decimal("2000.00"))

    def test_report_designer_views_create_definition_and_line(self):
        response = self.client.post(
            reverse("accounting:financial_report_create"),
            {
                "name": "Management P&L",
                "code": "MGMT-PNL",
                "report_type": FinancialReportDefinition.ReportType.PROFIT_LOSS,
                "is_active": "on",
            },
        )
        definition = FinancialReportDefinition.objects.get(
            company=self.company, code="MGMT-PNL"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounting:financial_report_detail", kwargs={"pk": definition.pk}))

        response = self.client.post(
            reverse("accounting:financial_report_line_create", kwargs={"pk": definition.pk}),
            {
                "line_number": "100",
                "row_code": "REV",
                "label": "Revenue",
                "line_type": FinancialReportLine.LineType.ACCOUNT_SUM,
                "accounts": [str(self.sales.pk)],
                "show_zero": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        line = definition.lines.get(row_code="REV")
        self.assertEqual(list(line.accounts.all()), [self.sales])
