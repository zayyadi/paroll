from django.test import TestCase
from django.contrib.auth import get_user_model

from accounting.models import FinancialReportJob, Account, FiscalYear, AccountingPeriod
from accounting.utils import get_or_create_fiscal_year, get_or_create_period
from accounting.tests.fixtures import get_test_company

User = get_user_model()


class FinancialReportJobTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(
            email="reportusr@test.com", password="testpass123"
        )
        self.fiscal_year = get_or_create_fiscal_year(year=2026, company=self.company)
        self.period = get_or_create_period(
            fiscal_year=self.fiscal_year, period_number=5, company=self.company
        )

    def test_job_creation(self):
        job = FinancialReportJob.objects.create(
            company=self.company,
            user=self.user,
            report_type=FinancialReportJob.ReportType.TRIAL_BALANCE,
            period=self.period,
        )
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.report_type, "TRIAL_BALANCE")

    def test_job_str(self):
        job = FinancialReportJob.objects.create(
            company=self.company,
            user=self.user,
            report_type=FinancialReportJob.ReportType.BALANCE_SHEET,
        )
        self.assertIn("Balance Sheet", str(job))

    def test_job_ordering(self):
        FinancialReportJob.objects.create(
            company=self.company, user=self.user,
            report_type=FinancialReportJob.ReportType.TRIAL_BALANCE,
        )
        FinancialReportJob.objects.create(
            company=self.company, user=self.user,
            report_type=FinancialReportJob.ReportType.INCOME_STATEMENT,
        )
        jobs = FinancialReportJob.objects.all()
        self.assertGreaterEqual(jobs[0].queued_at, jobs[1].queued_at)
