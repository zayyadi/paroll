from django.core.management.base import BaseCommand
from accounting.models import Account, FiscalYear, AccountingPeriod
from django.utils import timezone
from datetime import date
import random


class Command(BaseCommand):
    help = "Creates fake accounts for testing the accounting system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Number of fake accounts to create (default: 20)",
        )
        parser.add_argument(
            "--include-fiscal-year",
            action="store_true",
            help="Also create a fiscal year and periods if they do not exist",
        )

    def handle(self, *args, **options):
        count = options["count"]
        include_fiscal_year = options["include_fiscal_year"]

        # Sample data for generating realistic accounts
        asset_names = [
            "Cash and Cash Equivalents",
            "Accounts Receivable",
            "Inventory",
            "Prepaid Expenses",
            "Office Equipment",
            "Computer Equipment",
            "Furniture and Fixtures",
            "Motor Vehicles",
            "Buildings",
            "Accumulated Depreciation - Equipment",
            "Investments",
            "Petty Cash",
            "Bank Accounts",
            "Short-term Investments",
            "Supplies",
            "Work in Progress",
            "Raw Materials",
        ]

        liability_names = [
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
            "Bonds Payable",
        ]

        equity_names = [
            "Share Capital",
            "Retained Earnings",
            "Share Premium",
            "Treasury Shares",
            "Comprehensive Income",
            "Owner Equity",
            "Partnership Capital",
            "Corporate Capital",
        ]

        revenue_names = [
            "Sales Revenue",
            "Service Revenue",
            "Consulting Revenue",
            "Interest Income",
            "Rental Income",
            "Commission Income",
            "Fee Income",
            "Royalty Income",
            "Dividend Income",
            "Other Operating Income",
            "Non-operating Income",
        ]

        expense_names = [
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
            "Cost of Goods Sold",
            "Research and Development",
        ]

        # Account type mapping
        account_types = {
            "ASSET": (asset_names, 1000, 1999),
            "LIABILITY": (liability_names, 2000, 2999),
            "EQUITY": (equity_names, 3000, 3999),
            "REVENUE": (revenue_names, 4000, 4999),
            "EXPENSE": (expense_names, 5000, 5999),
        }

        created_count = 0
        existing_count = 0

        # Keep track of used account numbers to avoid duplicates
        used_account_numbers = set(
            Account.objects.values_list("account_number", flat=True)
        )

        for _ in range(count):
            # Randomly select account type
            account_type = random.choice(list(account_types.keys()))
            names, start_num, end_num = account_types[account_type]

            # Select random name and generate unique account number
            name = random.choice(names)

            # Check if account name already exists
            if Account.objects.filter(name=name).exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"Account with name '{name}' already exists, skipping..."
                    )
                )
                continue

            # Generate a unique account number
            max_attempts = 100
            for attempt in range(max_attempts):
                account_number = f"{random.randint(start_num, end_num)}"
                if account_number not in used_account_numbers:
                    used_account_numbers.add(account_number)
                    break
            else:
                # If we can't find a unique number, skip this account
                self.stdout.write(
                    self.style.WARNING(
                        f"Could not generate unique account number for {name}, skipping..."
                    )
                )
                continue

            # Create account with unique name and account number
            account, created = Account.objects.get_or_create(
                name=name,
                account_number=account_number,
                defaults={
                    "type": account_type,
                    "description": f"Auto-generated {account_type.lower()} account for {name}",
                },
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created account: {account_number} - {name} ({account_type})"
                    )
                )
            else:
                existing_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Account already exists: {account_number} - {name}"
                    )
                )

        # Create fiscal year and periods if requested
        if include_fiscal_year:
            current_year = timezone.now().year
            fiscal_year, created = FiscalYear.objects.get_or_create(
                year=current_year,
                defaults={
                    "name": f"Fiscal Year {current_year}",
                    "start_date": date(current_year, 1, 1),
                    "end_date": date(current_year, 12, 31),
                    "is_active": True,
                },
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created fiscal year: {fiscal_year.name}")
                )

                # Create monthly periods
                for month in range(1, 13):
                    period, period_created = AccountingPeriod.objects.get_or_create(
                        fiscal_year=fiscal_year,
                        period_number=month,
                        defaults={
                            "name": f"Month {month}",
                            "start_date": date(current_year, month, 1),
                            "end_date": self._get_last_day_of_month(
                                current_year, month
                            ),
                            "is_active": month == timezone.now().month,
                        },
                    )

                    if period_created:
                        self.stdout.write(
                            self.style.SUCCESS(f"Created period: {period.name}")
                        )

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS(f"Summary:"))
        self.stdout.write(f"  Total accounts processed: {count}")
        self.stdout.write(f"  New accounts created: {created_count}")
        self.stdout.write(f"  Accounts already existing: {existing_count}")
        self.stdout.write("=" * 50)

    def _get_last_day_of_month(self, year, month):
        """Get the last day of a month"""
        if month == 12:
            return date(year + 1, 1, 1) - timezone.timedelta(days=1)
        else:
            return date(year, month + 1, 1) - timezone.timedelta(days=1)
