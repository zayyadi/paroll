from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounting.models import Account, AccountingPeriod, FiscalYear
from company.models import Company


User = get_user_model()


class FiscalPeriodCreationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Fiscal Period Co")
        self.user = User.objects.create_superuser(
            email="accountant@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.client.force_login(self.user)

    def test_accountant_can_create_fiscal_year_from_ui(self):
        response = self.client.post(
            reverse("accounting:fiscal_year_create"),
            {
                "year": 2027,
                "name": "FY 2027",
                "start_date": "2027-01-01",
                "end_date": "2027-12-31",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FiscalYear.objects.filter(
                company=self.company,
                year=2027,
                start_date=date(2027, 1, 1),
                end_date=date(2027, 12, 31),
            ).exists()
        )

    def test_accountant_can_create_accounting_period_from_ui(self):
        fiscal_year = FiscalYear.objects.create(
            company=self.company,
            year=2027,
            name="FY 2027",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31),
            is_active=True,
        )

        response = self.client.post(
            reverse("accounting:period_create"),
            {
                "fiscal_year": fiscal_year.pk,
                "period_number": 1,
                "name": "January 2027",
                "start_date": "2027-01-01",
                "end_date": "2027-01-31",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AccountingPeriod.objects.filter(
                company=self.company,
                fiscal_year=fiscal_year,
                period_number=1,
            ).exists()
        )

    def test_fake_accounts_command_creates_fiscal_calendar_for_company(self):
        out = StringIO()

        call_command(
            "create_fake_accounts",
            count=1,
            include_fiscal_year=True,
            company_id=self.company.pk,
            stdout=out,
        )

        self.assertTrue(Account.objects.filter(company=self.company).exists())
        fiscal_year = FiscalYear.objects.get(
            company=self.company,
            year=date.today().year,
        )
        self.assertEqual(
            AccountingPeriod.objects.filter(
                company=self.company,
                fiscal_year=fiscal_year,
            ).count(),
            12,
        )
