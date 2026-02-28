from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase

from accounting.models import Account, Journal
from accounting.utils import create_journal_with_entries
from company.models import Company
from payroll.models import EmployeeProfile, Payroll, PayrollEntry, PayrollRun, PayrollRunEntry
from users.models import CustomUser


class BackfillPayrollStatutoryCorrectionsCommandTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Backfill Co")
        self._ensure_accounts()

    def _q(self, value):
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _ensure_accounts(self):
        for account_number, name, account_type in [
            ("6010", "Salaries and Wages Expense", Account.AccountType.EXPENSE),
            ("6030", "Health Contribution Expense (Employer)", Account.AccountType.EXPENSE),
            ("2130", "Health Contribution Payable", Account.AccountType.LIABILITY),
            ("2150", "NHF Payable", Account.AccountType.LIABILITY),
        ]:
            Account.objects.get_or_create(
                account_number=account_number,
                defaults={"name": name, "type": account_type},
            )

    def _build_buggy_payroll_journal(self):
        user = CustomUser.objects.create_user(
            email=f"backfill-{CustomUser.objects.count()+1}@example.com",
            password="secret123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )
        payroll = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("60000.00"),
            is_housing=True,
            is_nhif=True,
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = self.company
        employee.first_name = "Ada"
        employee.last_name = "Lovelace"
        employee.slug = f"ada-backfill-{employee.pk}"
        employee.employee_pay = payroll
        employee.status = "active"
        employee.save()

        payroll_entry = PayrollEntry.objects.create(
            company=self.company,
            pays=employee,
            status="active",
        )

        payroll_run = PayrollRun.objects.create(
            company=self.company,
            name=f"Backfill {date.today():%Y-%m}",
            paydays=date.today().replace(day=1),
            is_active=True,
        )
        PayrollRunEntry.objects.create(payroll_run=payroll_run, payroll_entry=payroll_entry)

        annual_nhf = Decimal(payroll.nhf or 0)
        annual_employee_health = Decimal(payroll.employee_health or 0)
        annual_employer_health = Decimal(payroll.emplyr_health or 0)

        journal = create_journal_with_entries(
            date=date.today().replace(day=1),
            description=f"Payroll for period: {payroll_run.save_month_str}",
            entries=[
                {
                    "account": Account.objects.get(account_number="6010"),
                    "entry_type": "DEBIT",
                    "amount": annual_nhf + annual_employee_health,
                    "memo": "Buggy annual employee statutory expense",
                },
                {
                    "account": Account.objects.get(account_number="6030"),
                    "entry_type": "DEBIT",
                    "amount": annual_employer_health,
                    "memo": "Buggy annual employer health expense",
                },
                {
                    "account": Account.objects.get(account_number="2150"),
                    "entry_type": "CREDIT",
                    "amount": annual_nhf,
                    "memo": "Buggy annual NHF payable",
                },
                {
                    "account": Account.objects.get(account_number="2130"),
                    "entry_type": "CREDIT",
                    "amount": annual_employee_health + annual_employer_health,
                    "memo": "Buggy annual health payable",
                },
            ],
            source_object=payroll_run,
            auto_post=True,
            validate_balances=False,
        )

        return {
            "journal": journal,
            "payroll": payroll,
            "annual_nhf": annual_nhf,
            "annual_employee_health": annual_employee_health,
            "annual_employer_health": annual_employer_health,
        }

    def _run_command(self, *args):
        out = StringIO()
        call_command("backfill_payroll_statutory_corrections", *args, stdout=out)
        return out.getvalue()

    def _get_correction_journals(self, original_journal):
        journal_ct = ContentType.objects.get_for_model(Journal)
        return Journal.objects.filter(
            content_type=journal_ct,
            object_id=original_journal.pk,
            description__startswith="Payroll statutory correction:",
        )

    def test_dry_run_reports_candidates_without_creating_adjustment(self):
        fixture = self._build_buggy_payroll_journal()

        output = self._run_command()

        self.assertIn("DRY RUN", output)
        self.assertIn(fixture["journal"].transaction_number, output)
        self.assertEqual(self._get_correction_journals(fixture["journal"]).count(), 0)

    def test_apply_creates_posted_balanced_adjustment_with_expected_amounts(self):
        fixture = self._build_buggy_payroll_journal()

        self._run_command("--apply")

        correction = self._get_correction_journals(fixture["journal"]).get()
        self.assertEqual(correction.status, Journal.JournalStatus.POSTED)

        over_nhf = fixture["annual_nhf"] - (fixture["annual_nhf"] / Decimal("12"))
        over_employee_health = fixture["annual_employee_health"] - (
            fixture["annual_employee_health"] / Decimal("12")
        )
        over_employer_health = fixture["annual_employer_health"] - (
            fixture["annual_employer_health"] / Decimal("12")
        )

        nhf_debit = correction.entries.get(
            account__account_number="2150",
            entry_type="DEBIT",
        )
        health_payable_debit = correction.entries.get(
            account__account_number="2130",
            entry_type="DEBIT",
        )
        salary_credit = correction.entries.get(
            account__account_number="6010",
            entry_type="CREDIT",
        )
        health_expense_credit = correction.entries.get(
            account__account_number="6030",
            entry_type="CREDIT",
        )

        self.assertEqual(self._q(nhf_debit.amount), self._q(over_nhf))
        self.assertEqual(
            self._q(health_payable_debit.amount),
            self._q(over_employee_health + over_employer_health),
        )
        self.assertEqual(
            self._q(salary_credit.amount),
            self._q(over_nhf + over_employee_health),
        )
        self.assertEqual(self._q(health_expense_credit.amount), self._q(over_employer_health))

    def test_apply_is_idempotent_and_skips_existing_corrections(self):
        fixture = self._build_buggy_payroll_journal()

        first_output = self._run_command("--apply")
        second_output = self._run_command("--apply")

        self.assertIn("created=1", first_output)
        self.assertIn("already_corrected=1", second_output)
        self.assertEqual(self._get_correction_journals(fixture["journal"]).count(), 1)
