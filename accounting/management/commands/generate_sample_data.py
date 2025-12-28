from django.core.management.base import BaseCommand
from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    TransactionNumber,
    AccountingAuditTrail,
)
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
import random
from decimal import Decimal

User = get_user_model()


class Command(BaseCommand):
    help = "Generates comprehensive sample accounting data for testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--accounts",
            type=int,
            default=30,
            help="Number of fake accounts to create (default: 30)",
        )
        parser.add_argument(
            "--journals",
            type=int,
            default=50,
            help="Number of sample journals to create (default: 50)",
        )
        parser.add_argument(
            "--fiscal-year",
            type=int,
            default=timezone.now().year,
            help="Fiscal year to generate data for (default: current year)",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear existing sample data before generating new data",
        )

    def handle(self, *args, **options):
        accounts_count = options["accounts"]
        journals_count = options["journals"]
        fiscal_year_num = options["fiscal_year"]
        clear_existing = options["clear_existing"]

        self.stdout.write("Starting sample data generation...")

        # Clear existing data if requested
        if clear_existing:
            self._clear_existing_data()

        # Create fiscal year and periods
        fiscal_year = self._create_fiscal_year(fiscal_year_num)

        # Create accounts
        accounts = self._create_accounts(accounts_count)

        # Create journals with entries
        self._create_journals(journals_count, fiscal_year, accounts)

        self.stdout.write(self.style.SUCCESS("Sample data generation complete!"))

    def _clear_existing_data(self):
        """Clear existing sample data"""
        self.stdout.write("Clearing existing sample data...")
        JournalEntry.objects.all().delete()
        Journal.objects.all().delete()
        TransactionNumber.objects.all().delete()
        AccountingAuditTrail.objects.all().delete()
        Account.objects.all().delete()
        AccountingPeriod.objects.all().delete()
        FiscalYear.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("Existing data cleared"))

    def _create_fiscal_year(self, year):
        """Create fiscal year and monthly periods"""
        self.stdout.write(f"Creating fiscal year {year}...")

        fiscal_year, created = FiscalYear.objects.get_or_create(
            year=year,
            defaults={
                "name": f"Fiscal Year {year}",
                "start_date": date(year, 1, 1),
                "end_date": date(year, 12, 31),
                "is_active": True,
            },
        )

        if created:
            # Create monthly periods
            for month in range(1, 13):
                AccountingPeriod.objects.get_or_create(
                    fiscal_year=fiscal_year,
                    period_number=month,
                    defaults={
                        "name": f"Month {month}",
                        "start_date": date(year, month, 1),
                        "end_date": self._get_last_day_of_month(year, month),
                        "is_active": month == timezone.now().month,
                    },
                )
            self.stdout.write(
                self.style.SUCCESS(f"Created fiscal year and periods for {year}")
            )
        else:
            self.stdout.write(self.style.WARNING(f"Fiscal year {year} already exists"))

        return fiscal_year

    def _create_accounts(self, count):
        """Create fake accounts"""
        self.stdout.write(f"Creating {count} fake accounts...")

        # Sample data
        account_data = {
            "ASSET": {
                "names": [
                    "Cash and Cash Equivalents",
                    "Accounts Receivable",
                    "Inventory",
                    "Prepaid Expenses",
                    "Office Equipment",
                    "Computer Equipment",
                    "Furniture and Fixtures",
                    "Motor Vehicles",
                    "Buildings",
                    "Accumulated Depreciation",
                    "Investments",
                    "Petty Cash",
                    "Bank Accounts",
                    "Short-term Investments",
                    "Supplies",
                ],
                "range": (1000, 1999),
            },
            "LIABILITY": {
                "names": [
                    "Accounts Payable",
                    "Accrued Expenses",
                    "Salaries Payable",
                    "Tax Payable",
                    "Interest Payable",
                    "Notes Payable",
                    "Deferred Revenue",
                    "Customer Deposits",
                    "Pension Payable",
                    "PAYE Tax Payable",
                    "NSITF Payable",
                    "HMO Payable",
                    "Loan Payable",
                    "Mortgage Payable",
                ],
                "range": (2000, 2999),
            },
            "EQUITY": {
                "names": [
                    "Share Capital",
                    "Retained Earnings",
                    "Share Premium",
                    "Treasury Shares",
                    "Comprehensive Income",
                    "Owner Equity",
                ],
                "range": (3000, 3999),
            },
            "REVENUE": {
                "names": [
                    "Sales Revenue",
                    "Service Revenue",
                    "Consulting Revenue",
                    "Interest Income",
                    "Rental Income",
                    "Commission Income",
                    "Fee Income",
                    "Royalty Income",
                    "Dividend Income",
                ],
                "range": (4000, 4999),
            },
            "EXPENSE": {
                "names": [
                    "Salaries and Wages",
                    "Rent Expense",
                    "Utilities Expense",
                    "Office Supplies",
                    "Travel Expense",
                    "Marketing Expense",
                    "Insurance Expense",
                    "Maintenance Expense",
                    "Depreciation Expense",
                    "Interest Expense",
                    "Tax Expense",
                    "Legal Expense",
                    "Accounting Fees",
                    "Bank Charges",
                    "Training Expense",
                    "Pension Expense",
                    "HMO Expense",
                    "NSITF Expense",
                ],
                "range": (5000, 5999),
            },
        }

        accounts = []
        for account_type, data in account_data.items():
            # Determine how many accounts to create for this type
            type_count = max(1, count // len(account_data))

            for _ in range(type_count):
                name = random.choice(data["names"])
                account_number = str(random.randint(*data["range"]))

                account, created = Account.objects.get_or_create(
                    name=name,
                    defaults={
                        "account_number": account_number,
                        "type": account_type,
                        "description": f"Auto-generated {account_type.lower()} account",
                    },
                )

                if created:
                    accounts.append(account)
                    self.stdout.write(
                        self.style.SUCCESS(f"  Created: {account_number} - {name}")
                    )

        return accounts

    def _create_journals(self, count, fiscal_year, accounts):
        """Create sample journals with entries"""
        self.stdout.write(f"Creating {count} sample journals...")

        # Get or create a user for journal entries
        user, _ = User.objects.get_or_create(
            email="accountant@example.com",
            defaults={
                "first_name": "Sample",
                "last_name": "Accountant",
            },
        )

        # Sample journal descriptions
        descriptions = [
            "Monthly salary payments",
            "Office rent payment",
            "Utility bill payment",
            "Equipment purchase",
            "Service revenue received",
            "Consulting fees payment",
            "Insurance premium payment",
            "Marketing campaign expenses",
            "Bank service charges",
            "Tax payment to authorities",
            "Supplier payment",
            "Customer invoice payment received",
            "Petty cash replenishment",
            "Training expenses",
            "Legal fees payment",
            "Software subscription",
            "Maintenance expenses",
            "Travel expenses reimbursement",
            "Office supplies purchase",
            "Vehicle expenses",
        ]

        # Create transaction number counter
        txn_counter, _ = TransactionNumber.objects.get_or_create(
            fiscal_year=fiscal_year, prefix="TXN", defaults={"current_number": 1}
        )

        for i in range(count):
            # Get a random period
            period = (
                AccountingPeriod.objects.filter(fiscal_year=fiscal_year)
                .order_by("?")
                .first()
            )

            # Create journal
            journal = Journal.objects.create(
                transaction_number=f"TXN{str(txn_counter.current_number).zfill(6)}",
                description=random.choice(descriptions),
                date=self._random_date_in_period(period),
                period=period,
                status="POSTED",
                created_by=user,
                posted_by=user,
                posted_at=timezone.now(),
            )

            # Create journal entries (at least 2 for balanced entries)
            self._create_journal_entries(journal, accounts, user)

            # Update transaction number
            txn_counter.current_number += 1
            txn_counter.save()

            if (i + 1) % 10 == 0:
                self.stdout.write(f"  Created {i + 1}/{count} journals")

    def _create_journal_entries(self, journal, accounts, user):
        """Create balanced journal entries for a journal"""
        # Separate accounts by type
        asset_accounts = [a for a in accounts if a.type == "ASSET"]
        liability_accounts = [a for a in accounts if a.type == "LIABILITY"]
        equity_accounts = [a for a in accounts if a.type == "EQUITY"]
        revenue_accounts = [a for a in accounts if a.type == "REVENUE"]
        expense_accounts = [a for a in accounts if a.type == "EXPENSE"]

        # Generate random amount
        total_amount = Decimal(str(round(random.uniform(100, 10000), 2)))

        # Create 2-4 entries
        num_entries = random.randint(2, 4)

        # Decide on entry pattern
        patterns = [
            # Expense/Cash (debit expense, credit cash)
            {
                "debits": [(expense_accounts, total_amount)],
                "credits": [(asset_accounts, total_amount)],
            },
            # Cash/Revenue (debit cash, credit revenue)
            {
                "debits": [(asset_accounts, total_amount)],
                "credits": [(revenue_accounts, total_amount)],
            },
            # Expense/Liability (debit expense, credit liability)
            {
                "debits": [(expense_accounts, total_amount)],
                "credits": [(liability_accounts, total_amount)],
            },
            # Asset/Expense (debit asset, credit expense)
            {
                "debits": [(asset_accounts, total_amount)],
                "credits": [(expense_accounts, total_amount)],
            },
        ]

        pattern = random.choice(patterns)

        # Create debit entries
        for account_list, amount in pattern["debits"]:
            if account_list:
                account = random.choice(account_list)
                JournalEntry.objects.create(
                    journal=journal,
                    account=account,
                    entry_type="DEBIT",
                    amount=amount,
                    memo=f"Debit entry for {journal.description}",
                    created_by=user,
                )

        # Create credit entries
        for account_list, amount in pattern["credits"]:
            if account_list:
                account = random.choice(account_list)
                JournalEntry.objects.create(
                    journal=journal,
                    account=account,
                    entry_type="CREDIT",
                    amount=amount,
                    memo=f"Credit entry for {journal.description}",
                    created_by=user,
                )

    def _random_date_in_period(self, period):
        """Generate a random date within an accounting period"""
        start = period.start_date
        end = period.end_date
        delta = end - start
        random_days = random.randint(0, delta.days)
        return start + timedelta(days=random_days)

    def _get_last_day_of_month(self, year, month):
        """Get last day of a month"""
        if month == 12:
            return date(year + 1, 1, 1) - timedelta(days=1)
        else:
            return date(year, month + 1, 1) - timedelta(days=1)
