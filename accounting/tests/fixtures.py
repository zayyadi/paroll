"""
Test fixtures for accounting tests.
Provides factory methods for creating test data.
"""

from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from accounting.models import (
    Account,
    AccountingAuditTrail,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    TransactionNumber,
)
from company.models import Company

User = get_user_model()


def get_test_company():
    company, _ = Company.objects.get_or_create(name="Default Company")
    return company


class UserFactory:
    """Factory for creating test users with different roles"""

    @staticmethod
    def _grant_role(user, group_name, permissions):
        group, _ = Group.objects.get_or_create(name=group_name)
        resolved_permissions = []
        for model, codenames in permissions:
            content_type = ContentType.objects.get_for_model(model)
            for codename in codenames:
                permission, _ = Permission.objects.get_or_create(
                    content_type=content_type,
                    codename=codename,
                    defaults={"name": codename.replace("_", " ").title()},
                )
                resolved_permissions.append(permission)
        group.permissions.set(resolved_permissions)
        user.groups.add(group)
        for cache_name in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            if hasattr(user, cache_name):
                delattr(user, cache_name)
        return user

    @staticmethod
    def _create_user(email, password="testpass123", **extra_fields):
        company = extra_fields.setdefault("company", get_test_company())
        extra_fields.setdefault("active_company", company)
        user, created = User.objects.get_or_create(email=email, defaults=extra_fields)
        if created:
            user.set_password(password)
            user.save()
        elif not user.active_company_id:
            user.company = company
            user.active_company = company
            user.save(update_fields=["company", "active_company"])
        return user

    @staticmethod
    def create_auditor(username="test_auditor", email="auditor@test.com"):
        """Create a user with auditor role"""
        user = UserFactory._create_user(
            email=email,
            password="testpass123",
            first_name="Test",
            last_name="Auditor",
        )
        return UserFactory._grant_role(
            user,
            "Auditor",
            [
                (
                    Account,
                    [
                        "view_account",
                        "view_trial_balance",
                        "view_general_ledger",
                        "view_account_activity",
                    ],
                ),
                (Journal, ["view_journal"]),
                (JournalEntry, ["view_journalentry"]),
                (FiscalYear, ["view_fiscalyear"]),
                (AccountingPeriod, ["view_accountingperiod"]),
                (
                    AccountingAuditTrail,
                    [
                        "view_accountingaudittrail",
                        "add_accountingaudittrail",
                        "change_accountingaudittrail",
                    ],
                ),
            ],
        )

    @staticmethod
    def create_accountant(username="test_accountant", email="accountant@test.com"):
        """Create a user with accountant role"""
        user = UserFactory._create_user(
            email=email,
            password="testpass123",
            first_name="Test",
            last_name="Accountant",
        )
        return UserFactory._grant_role(
            user,
            "Accountant",
            [
                (
                    Account,
                    [
                        "view_account",
                        "add_account",
                        "change_account",
                        "view_trial_balance",
                        "view_general_ledger",
                        "view_account_activity",
                    ],
                ),
                (Journal, ["view_journal", "add_journal", "change_journal", "post_journal"]),
                (JournalEntry, ["view_journalentry", "add_journalentry", "change_journalentry"]),
                (FiscalYear, ["view_fiscalyear"]),
                (AccountingPeriod, ["view_accountingperiod", "change_accountingperiod"]),
            ],
        )

    @staticmethod
    def create_payroll_processor(username="test_payroll", email="payroll@test.com"):
        """Create a user with payroll processor role"""
        user = UserFactory._create_user(
            email=email,
            password="testpass123",
            first_name="Test",
            last_name="Payroll",
        )
        return UserFactory._grant_role(
            user,
            "Payroll Processor",
            [
                (Account, ["view_account"]),
                (Journal, ["view_journal"]),
                (JournalEntry, ["view_journalentry", "add_journalentry"]),
                (FiscalYear, ["view_fiscalyear"]),
                (AccountingPeriod, ["view_accountingperiod"]),
            ],
        )

    @staticmethod
    def create_admin(username="test_admin", email="admin@test.com"):
        """Create an admin user"""
        user = UserFactory._create_user(
            email=email,
            password="testpass123",
            first_name="Test",
            last_name="Admin",
            is_staff=True,
            is_superuser=True,
        )
        return user


class AccountFactory:
    """Factory for creating chart of accounts"""

    @staticmethod
    def create_chart_of_accounts():
        """Create a complete chart of accounts for testing"""
        company = get_test_company()
        accounts = []

        # Assets
        accounts.append(
            Account.objects.create(
                company=company,
                name="Cash",
                account_number="1000",
                type=Account.AccountType.ASSET,
                description="Cash and cash equivalents",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Accounts Receivable",
                account_number="1100",
                type=Account.AccountType.ASSET,
                description="Trade receivables",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Inventory",
                account_number="1200",
                type=Account.AccountType.ASSET,
                description="Inventory items",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Equipment",
                account_number="1300",
                type=Account.AccountType.ASSET,
                description="Office equipment",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Accumulated Depreciation",
                account_number="1310",
                type=Account.AccountType.ASSET,
                description="Accumulated depreciation on equipment",
            )
        )

        # Liabilities
        accounts.append(
            Account.objects.create(
                company=company,
                name="Accounts Payable",
                account_number="2000",
                type=Account.AccountType.LIABILITY,
                description="Trade payables",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Accrued Expenses",
                account_number="2100",
                type=Account.AccountType.LIABILITY,
                description="Accrued expenses",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Taxes Payable",
                account_number="2200",
                type=Account.AccountType.LIABILITY,
                description="Taxes payable",
            )
        )

        # Equity
        accounts.append(
            Account.objects.create(
                company=company,
                name="Common Stock",
                account_number="3000",
                type=Account.AccountType.EQUITY,
                description="Common stock",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Retained Earnings",
                account_number="3100",
                type=Account.AccountType.EQUITY,
                description="Retained earnings",
            )
        )

        # Revenue
        accounts.append(
            Account.objects.create(
                company=company,
                name="Sales Revenue",
                account_number="4000",
                type=Account.AccountType.REVENUE,
                description="Sales revenue",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Service Revenue",
                account_number="4100",
                type=Account.AccountType.REVENUE,
                description="Service revenue",
            )
        )

        # Expenses
        accounts.append(
            Account.objects.create(
                company=company,
                name="Salaries Expense",
                account_number="5000",
                type=Account.AccountType.EXPENSE,
                description="Salaries and wages",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Rent Expense",
                account_number="5100",
                type=Account.AccountType.EXPENSE,
                description="Rent expense",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Utilities Expense",
                account_number="5200",
                type=Account.AccountType.EXPENSE,
                description="Utilities expense",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Office Supplies",
                account_number="5300",
                type=Account.AccountType.EXPENSE,
                description="Office supplies expense",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Depreciation Expense",
                account_number="5400",
                type=Account.AccountType.EXPENSE,
                description="Depreciation expense",
            )
        )
        accounts.append(
            Account.objects.create(
                company=company,
                name="Payroll Tax Expense",
                account_number="5500",
                type=Account.AccountType.EXPENSE,
                description="Payroll taxes",
            )
        )

        return accounts

    @staticmethod
    def create_account(name, account_number, account_type, description="", company=None):
        """Create a single account"""
        company = company or get_test_company()
        account, _ = Account.objects.get_or_create(
            company=company,
            account_number=account_number,
            defaults={
                "name": name,
                "type": account_type,
                "description": description,
            },
        )
        return account


class FiscalYearFactory:
    """Factory for creating fiscal years and periods"""

    @staticmethod
    def create_fiscal_year(year=None, is_active=True, company=None):
        """Create a fiscal year with monthly periods"""
        if year is None:
            year = timezone.now().year
        company = company or get_test_company()

        fiscal_year, _ = FiscalYear.objects.get_or_create(
            company=company,
            year=year,
            defaults={
                "name": f"FY {year}",
                "start_date": date(year, 1, 1),
                "end_date": date(year, 12, 31),
                "is_active": is_active,
            },
        )

        # Create monthly periods
        for month in range(1, 13):
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year, 12, 31)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)

            AccountingPeriod.objects.get_or_create(
                company=company,
                fiscal_year=fiscal_year,
                period_number=month,
                defaults={
                    "name": f"Month {month}",
                    "start_date": start_date,
                    "end_date": end_date,
                    "is_active": (month == timezone.now().month),
                },
            )

        return fiscal_year

    @staticmethod
    def create_previous_fiscal_year(year=None):
        """Create a previous fiscal year for testing"""
        if year is None:
            year = timezone.now().year - 1
        return FiscalYearFactory.create_fiscal_year(year=year, is_active=False)


class JournalFactory:
    """Factory for creating journals and entries"""

    @staticmethod
    def create_journal(
        description="Test Journal",
        date=None,
        user=None,
        status=Journal.JournalStatus.DRAFT,
    ):
        """Create a journal with balanced entries"""
        if date is None:
            date = timezone.now().date()

        if user is None:
            user = UserFactory.create_accountant(email="journal_creator@test.com")

        # Get current period
        current_year = timezone.now().year
        fiscal_year = FiscalYear.objects.filter(
            year=current_year, is_active=True
        ).first()
        if not fiscal_year:
            fiscal_year = FiscalYearFactory.create_fiscal_year(current_year)

        current_month = timezone.now().month
        period = AccountingPeriod.objects.filter(
            fiscal_year=fiscal_year, period_number=current_month
        ).first()

        journal = Journal.objects.create(
            description=description,
            date=date,
            period=period,
            status=status,
            created_by=user,
        )

        return journal

    @staticmethod
    def create_journal_with_entries(
        description="Test Journal", amount=1000, date=None, user=None
    ):
        """Create a journal with balanced debit and credit entries"""
        journal = JournalFactory.create_journal(description, date, user)
        company = journal.company
        AccountFactory.create_account("Cash", "1000", Account.AccountType.ASSET, company=company)
        AccountFactory.create_account(
            "Sales Revenue", "4000", Account.AccountType.REVENUE, company=company
        )

        # Get accounts
        cash = Account.objects.get(company=company, account_number="1000")  # Cash
        sales_revenue = Account.objects.get(
            company=company, account_number="4000"
        )  # Sales Revenue

        # Create balanced entries
        JournalEntry.objects.create(
            journal=journal,
            account=cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal(str(amount)),
            memo="Cash received",
        )

        JournalEntry.objects.create(
            journal=journal,
            account=sales_revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal(str(amount)),
            memo="Sales revenue",
        )

        return journal

    @staticmethod
    def create_payroll_journal(gross_pay=5000, date=None, user=None):
        """Create a payroll journal with typical payroll entries"""
        journal = JournalFactory.create_journal("Payroll Journal", date, user)

        # Get accounts
        salaries_expense = Account.objects.get(
            account_number="5000"
        )  # Salaries Expense
        payroll_tax_expense = Account.objects.get(
            account_number="5500"
        )  # Payroll Tax Expense
        cash = Account.objects.get(account_number="1000")  # Cash
        taxes_payable = Account.objects.get(account_number="2200")  # Taxes Payable

        # Calculate amounts
        payroll_tax = gross_pay * Decimal("0.15")  # 15% payroll tax
        net_pay = gross_pay - payroll_tax

        # Create expense entries (debits)
        JournalEntry.objects.create(
            journal=journal,
            account=salaries_expense,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal(str(gross_pay)),
            memo="Gross salaries",
        )

        JournalEntry.objects.create(
            journal=journal,
            account=payroll_tax_expense,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal(str(payroll_tax)),
            memo="Payroll taxes",
        )

        # Create liability/asset entries (credits)
        JournalEntry.objects.create(
            journal=journal,
            account=cash,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal(str(net_pay)),
            memo="Net salaries paid",
        )

        JournalEntry.objects.create(
            journal=journal,
            account=taxes_payable,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal(str(payroll_tax)),
            memo="Taxes withheld",
        )

        return journal

    @staticmethod
    def create_approved_journal(description="Test Journal", amount=1000, user=None):
        """Create and approve a journal"""
        accountant = user or UserFactory.create_accountant()
        journal = JournalFactory.create_journal_with_entries(
            description, amount, user=accountant
        )
        journal.submit_for_approval()
        journal.approve(accountant)
        return journal

    @staticmethod
    def create_posted_journal(description="Test Journal", amount=1000, user=None):
        """Create, approve, and post a journal"""
        accountant = user or UserFactory.create_accountant()
        journal = JournalFactory.create_approved_journal(
            description, amount, accountant
        )
        journal.post(accountant)
        return journal


class LargeDatasetFactory:
    """Factory for creating large datasets for performance testing"""

    @staticmethod
    def create_large_dataset(num_journals=100, entries_per_journal=4):
        """Create a large dataset of journals and entries"""
        journals = []
        user = UserFactory.create_accountant()

        # Get a variety of accounts
        accounts = list(Account.objects.all())
        if len(accounts) < 10:
            accounts = AccountFactory.create_chart_of_accounts()

        for i in range(num_journals):
            journal = JournalFactory.create_journal(
                description=f"Performance Test Journal {i+1}", user=user
            )

            # Create balanced entries
            total_debits = Decimal("0")
            total_credits = Decimal("0")

            for j in range(entries_per_journal - 1):
                amount = Decimal(str((j + 1) * 100))
                if j % 2 == 0:
                    # Debit entry
                    JournalEntry.objects.create(
                        journal=journal,
                        account=accounts[j % len(accounts)],
                        entry_type=JournalEntry.EntryType.DEBIT,
                        amount=amount,
                        memo=f"Debit entry {j+1}",
                    )
                    total_debits += amount
                else:
                    # Credit entry
                    JournalEntry.objects.create(
                        journal=journal,
                        account=accounts[j % len(accounts)],
                        entry_type=JournalEntry.EntryType.CREDIT,
                        amount=amount,
                        memo=f"Credit entry {j+1}",
                    )
                    total_credits += amount

            # Create balancing entry
            if total_debits > total_credits:
                # Need credit entry
                JournalEntry.objects.create(
                    journal=journal,
                    account=accounts[-1],
                    entry_type=JournalEntry.EntryType.CREDIT,
                    amount=total_debits - total_credits,
                    memo="Balancing credit entry",
                )
            elif total_credits > total_debits:
                # Need debit entry
                JournalEntry.objects.create(
                    journal=journal,
                    account=accounts[-1],
                    entry_type=JournalEntry.EntryType.DEBIT,
                    amount=total_credits - total_debits,
                    memo="Balancing debit entry",
                )

            journals.append(journal)

        return journals

    @staticmethod
    def create_large_account_chart(num_accounts=500):
        """Create a large chart of accounts"""
        accounts = []
        account_types = [
            Account.AccountType.ASSET,
            Account.AccountType.LIABILITY,
            Account.AccountType.EQUITY,
            Account.AccountType.REVENUE,
            Account.AccountType.EXPENSE,
        ]

        for i in range(num_accounts):
            account_type = account_types[i % len(account_types)]
            account = Account.objects.create(
                company=get_test_company(),
                name=f"Test Account {i+1}",
                account_number=f"{9000 + i}",
                type=account_type,
                description=f"Test account number {i+1} for performance testing",
            )
            accounts.append(account)

        return accounts


class CompleteTestDataFactory:
    """Factory for creating complete test datasets"""

    @staticmethod
    def create_complete_test_dataset():
        """Create a complete dataset for comprehensive testing"""
        # Create users
        auditor = UserFactory.create_auditor()
        accountant = UserFactory.create_accountant()
        payroll_processor = UserFactory.create_payroll_processor()
        admin = UserFactory.create_admin()

        # Create chart of accounts
        accounts = AccountFactory.create_chart_of_accounts()

        # Create fiscal years and periods
        current_fiscal_year = FiscalYearFactory.create_fiscal_year()
        previous_fiscal_year = FiscalYearFactory.create_previous_fiscal_year()

        # Create various journals
        cash_sale_journal = JournalFactory.create_journal_with_entries(
            "Cash Sale", 5000, user=accountant
        )

        payroll_journal = JournalFactory.create_payroll_journal(
            8000, user=payroll_processor
        )

        expense_journal = JournalFactory.create_journal_with_entries(
            "Office Rent", 2000, user=accountant
        )

        # Approve and post some journals
        posted_journal = JournalFactory.create_posted_journal(
            "Posted Entry", 3000, user=accountant
        )

        # Create a reversal
        reversal_journal = posted_journal.reverse(
            accountant, "Test reversal for audit trail"
        )

        return {
            "users": {
                "auditor": auditor,
                "accountant": accountant,
                "payroll_processor": payroll_processor,
                "admin": admin,
            },
            "accounts": accounts,
            "fiscal_years": {
                "current": current_fiscal_year,
                "previous": previous_fiscal_year,
            },
            "journals": {
                "cash_sale": cash_sale_journal,
                "payroll": payroll_journal,
                "expense": expense_journal,
                "posted": posted_journal,
                "reversal": reversal_journal,
            },
        }
