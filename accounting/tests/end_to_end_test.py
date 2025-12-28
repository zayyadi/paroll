"""
End-to-end test script for the complete accounting system.
Tests the entire system from setup to reporting.
"""

import os
import sys
import django
from decimal import Decimal
from datetime import date, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from accounting.utils import (
    get_trial_balance,
    get_account_balance,
    get_general_ledger,
    close_period,
    close_fiscal_year,
)
from accounting.tests.fixtures import (
    UserFactory,
    AccountFactory,
    FiscalYearFactory,
    JournalFactory,
    CompleteTestDataFactory,
)

User = get_user_model()


class EndToEndTestRunner:
    """End-to-end test runner for accounting system"""

    def __init__(self):
        self.results = []
        self.errors = []
        self.warnings = []

    def log_result(self, test_name, success, message=None):
        """Log test result"""
        status = "PASS" if success else "FAIL"
        self.results.append({
            'test': test_name,
            'status': status,
        self.warnings = []

    def log_result(self, test_name, passed, message=""):
        """Log a test result."""
        status = "PASS" if passed else "FAIL"
        self.results.append((test_name, status, message))
        print(f"[{status}] {test_name}: {message}")

    def log_warning(self, message):
        """Log a warning."""
        self.warnings.append(message)
        print(f"[WARNING] {message}")

    def log_error(self, message):
        """Log an error."""
        self.errors.append(message)
        print(f"[ERROR] {message}")

    def setup_complete_accounting_system(self):
        """Set up a complete accounting system."""
        print("\n=== Setting up Complete Accounting System ===")
        
        try:
            # Create users with different roles
            self.admin = AccountingTestDataFactory.create_user("admin", is_superuser=True)
            self.accountant = AccountingTestDataFactory.create_accountant("accountant")
            self.auditor = AccountingTestDataFactory.create_auditor("auditor")
            self.payroll_processor = AccountingTestDataFactory.create_payroll_processor("payroll_processor")
            self.regular_user = AccountingTestDataFactory.create_user("regular_user")
            self.log_result("User Creation", True, "Created users with all required roles")
            
            # Create fiscal year and periods
            self.fiscal_year = AccountingTestDataFactory.create_fiscal_year(2023)
            self.periods = AccountingTestDataFactory.create_accounting_periods(self.fiscal_year)
            self.log_result("Fiscal Year Setup", True, f"Created FY {self.fiscal_year.year} with {len(self.periods)} periods")
            
            # Create comprehensive chart of accounts
            self.accounts = AccountingTestDataFactory.create_chart_of_accounts()
            
            # Create additional payroll-specific accounts
            self.salary_expense = Account.objects.create(
                name="Salary Expense",
                account_number="5001",
                type=Account.AccountType.EXPENSE,
            )
            self.tax_payable = Account.objects.create(
                name="Tax Payable",
                account_number="2001",
                type=Account.AccountType.LIABILITY,
            )
            self.insurance_payable = Account.objects.create(
                name="Insurance Payable",
                account_number="2002",
                type=Account.AccountType.LIABILITY,
            )
            self.cash_account = Account.objects.create(
                name="Cash Account",
                account_number="1001",
                type=Account.AccountType.ASSET,
            )
            
            self.all_accounts = list(self.accounts) + [self.salary_expense, self.tax_payable, self.insurance_payable, self.cash_account]
            self.log_result("Chart of Accounts", True, f"Created {len(self.all_accounts)} accounts including payroll accounts")
            
            return True
            
        except Exception as e:
            self.log_error(f"Failed to set up accounting system: {str(e)}")
            return False

    def test_double_entry_bookkeeping(self):
        """Test double-entry bookkeeping principles."""
        print("\n=== Testing Double-Entry Bookkeeping ===")
        
        try:
            with patch('accounting.utils.get_audit_user_and_metadata') as mock_get_metadata:
                mock_get_metadata.return_value = (self.accountant, "192.168.1.1", "Test Browser")
                
                # Create a balanced journal entry
                journal = create_journal(
                    description="Double-Entry Test",
                    date=date.today(),
                    period=self.periods[0],
                    entries=[
                        {"account": self.cash_account, "entry_type": "DEBIT", "amount": 5000},
                        {"account": self.all_accounts[1], "entry_type": "CREDIT", "amount": 5000},
                    ],
                    created_by=self.accountant,
                )
                
                # Verify journal is created with draft status
                assert journal.status == Journal.JournalStatus.DRAFT
                self.log_result("Journal Creation", True, "Journal created with draft status")
                
                # Approve and post journal
                journal.approve(self.accountant)
                assert journal.status == Journal.JournalStatus.APPROVED
                self.log_result("Journal Approval", True, "Journal approved successfully")
                
                post_journal(journal, self.accountant)
                journal.refresh_from_db()
                assert journal.status == Journal.JournalStatus.POSTED
                self.log_result("Journal Posting", True, "Journal posted successfully")
                
                # Verify double-entry balance
                entries = JournalEntry.objects.filter(journal=journal)
                total_debits = sum(entry.amount for entry in entries if entry.entry_type == "DEBIT")
                total_credits = sum(entry.amount for entry in entries if entry.entry_type == "CREDIT")
                
                assert total_debits == total_credits == Decimal('5000.00')
                self.log_result("Double-Entry Balance", True, f"Debits and credits balance: {total_debits}")
                
                # Test unbalanced journal rejection
                try:
                    unbalanced_journal = create_journal(
                        description="Unbalanced Test",
                        date=date.today(),
                        period=self.periods[0],
                        entries=[
                            {"account": self.cash_account, "entry_type": "DEBIT", "amount": 3000},
                            {"account": self.all_accounts[1], "entry_type": "CREDIT", "amount": 2000},  # Unbalanced
                        ],
                        created_by=self.accountant,
                    )
                    self.log_result("Unbalanced Journal Rejection", False, "Unbalanced journal was created")
                except Exception:
                    self.log_result("Unbalanced Journal Rejection", True, "Unbalanced journal correctly rejected")
                
                return True
                
        except Exception as e:
            self.log_error(f"Double-entry bookkeeping test failed: {str(e)}")
            return False

    def test_payroll_integration(self):
        """Test payroll transaction integration with accounting."""
        print("\n=== Testing Payroll Integration ===")
        
        if not PAYROLL_AVAILABLE:
            self.log_warning("Payroll models not available, skipping payroll integration tests")
            return True
        
        try:
            with patch('accounting.utils.get_audit_user_and_metadata') as mock_get_metadata:
                mock_get_metadata.return_value = (self.accountant, "192.168.1.1", "Test Browser")
                
                # Create employee profile
                employee = EmployeeProfile.objects.create(
                    user=self.regular_user,
                    employee_number="EMP001",
                    first_name="John",
                    last_name="Doe",
                )
                self.log_result("Employee Creation", True, f"Created employee: {employee.first_name} {employee.last_name}")
                
                # Create payroll transaction
                payroll = PayrollTransaction.objects.create(
                    employee=employee,
                    pay_period=self.periods[0],
                    gross_salary=Decimal('5000.00'),
                    tax_deduction=Decimal('500.00'),
                    insurance_deduction=Decimal('200.00'),
                    net_salary=Decimal('4300.00'),
                    status=PayrollTransaction.Status.POSTED,
                    created_by=self.payroll_processor,
                )
                self.log_result("Payroll Transaction", True, f"Created payroll transaction with gross salary: {payroll.gross_salary}")
                
                # Verify accounting journal was created
                journal = Journal.objects.filter(
                    description__contains=f"Payroll for {employee.first_name} {employee.last_name}",
                    period=self.periods[0],
                ).first()
                
                assert journal is not None
                assert journal.status == Journal.JournalStatus.POSTED
                self.log_result("Payroll Journal Creation", True, "Payroll journal created and posted")
                
                # Verify journal entries
                entries = JournalEntry.objects.filter(journal=journal)
                assert entries.count() == 4  # Salary expense, tax payable, insurance payable, cash
                
                # Verify debit and credit amounts
                total_debits = sum(entry.amount for entry in entries if entry.entry_type == "DEBIT")
                total_credits = sum(entry.amount for entry in entries if entry.entry_type == "CREDIT")
                assert total_debits == total_credits == Decimal('5000.00')  # Gross salary
                self.log_result("Payroll Entry Balance", True, f"Payroll entries balance: {total_debits}")
                
                # Test payroll reversal
                payroll.status = PayrollTransaction.Status.REVERSED
                payroll.reversal_reason = "Employee overpayment"
                payroll.reversed_by = self.auditor
                payroll.reversed_at = timezone.now()
                payroll.save()
                
                # Verify reversal journal was created
                reversal_journal = Journal.objects.filter(
                    description__contains="REVERSAL: Payroll for John Doe",
                    period=self.periods[0],
                ).first()
                
                assert reversal_journal is not None
                assert reversal_journal.status == Journal.JournalStatus.POSTED
                self.log_result("Payroll Reversal", True, "Payroll reversal journal created")
                
                return True
                
        except Exception as e:
            self.log_error(f"Payroll integration test failed: {str(e)}")
            return False

    def test_audit_trail_functionality(self):
        """Test audit trail logging and retrieval."""
        print("\n=== Testing Audit Trail Functionality ===")
        
        try:
            with patch('accounting.utils.get_audit_user_and_metadata') as mock_get_metadata:
                mock_get_metadata.return_value = (self.accountant, "192.168.1.1", "Test Browser")
                
                # Create a journal and track audit trail
                journal = create_journal(
                    description="Audit Trail Test",
                    date=date.today(),
                    period=self.periods[0],
                    entries=[
                        {"account": self.cash_account, "entry_type": "DEBIT", "amount": 2000},
                        {"account": self.all_accounts[1], "entry_type": "CREDIT", "amount": 2000},
                    ],
                    created_by=self.accountant,
                )
                
                # Approve and post journal
                journal.approve(self.accountant)
                post_journal(journal, self.accountant)
                
                # Check audit trail entries
                audit_entries = AccountingAuditTrail.objects.filter(
                    content_type=ContentType.objects.get_for_model(Journal),
                    object_id=journal.pk,
                ).order_by('timestamp')
                
                # Should have entries for create, approve, and post
                assert audit_entries.count() >= 3
                self.log_result("Audit Trail Logging", True, f"Found {audit_entries.count()} audit trail entries")
                
                # Verify specific actions are logged
                actions = [entry.action for entry in audit_entries]
                assert AccountingAuditTrail.ActionType.CREATE in actions
                assert AccountingAuditTrail.ActionType.APPROVE in actions
                assert AccountingAuditTrail.ActionType.POST in actions
                self.log_result("Audit Trail Actions", True, "All required actions are logged")
                
                # Verify user information is captured
                for entry in audit_entries:
                    assert entry.user == self.accountant
                    assert entry.ip_address == "192.168.1.1"
                    assert entry.user_agent == "Test Browser"
                
                self.log_result("Audit Trail Metadata", True, "User metadata correctly captured")
                
                # Test audit trail retrieval
                recent_entries = AccountingAuditTrail.objects.filter(
                    timestamp__gte=timezone.now() - timedelta(hours=1),
                ).order_by('-timestamp')[:10]
                
                assert len(recent_entries) > 0
                self.log_result("Audit Trail Retrieval", True, f"Retrieved {len(recent_entries)} recent audit entries")
                
                return True
                
        except Exception as e:
            self.log_error(f"Audit trail functionality test failed: {str(e)}")
            return False

    def test_reporting_capabilities(self):
        """Test reporting functionality."""
        print("\n=== Testing Reporting Capabilities ===")
        
        try:
            with patch('accounting.utils.get_audit_user_and_metadata') as mock_get_metadata:
                mock_get_metadata.return_value = (self.accountant, "192.168.1.1", "Test Browser")
                
                # Create multiple journals for reporting
                journals_data = [
                    {"debit_account": self.cash_account, "credit_account": self.all_accounts[1], "amount": 3000},
                    {"debit_account": self.all_accounts[2], "credit_account": self.all_accounts[3], "amount": 1500},
                    {"debit_account": self.all_accounts[4], "credit_account": self.cash_account, "amount": 750},
                ]
                
                for i, journal_data in enumerate(journals_data):
                    journal = create_journal(
                        description=f"Reporting Test Journal {i+1}",
                        date=date.today(),
                        period=self.periods[0],
                        entries=[
                            {"account": journal_data["debit_account"], "entry_type": "DEBIT", "amount": journal_data["amount"]},
                            {"account": journal_data["credit_account"], "entry_type": "CREDIT", "amount": journal_data["amount"]},
                        ],
                        created_by=self.accountant,
                    )
                    journal.approve(self.accountant)
                    post_journal(journal, self.accountant)
                
                # Generate trial balance
                trial_balance = generate_trial_balance(self.periods[0])
                
                # Verify trial balance structure
                assert "period" in trial_balance
                assert "accounts" in trial_balance
                assert "total_debits" in trial_balance
                assert "total_credits" in trial_balance
                assert "is_balanced" in trial_balance
                self.log_result("Trial Balance Structure", True, "Trial balance has required structure")
                
                # Verify trial balance balances
                assert trial_balance["total_debits"] == trial_balance["total_credits"]
                assert trial_balance["is_balanced"] == True
                expected_total = sum(jd["amount"] for jd in journals_data)
                assert trial_balance["total_debits"] == expected_total
                self.log_result("Trial Balance Balance", True, f"Trial balance balances: {trial_balance['total_debits']}")
                
                # Generate account activity report
                activity = generate_account_activity(self.cash_account, self.periods[0])
                
                # Verify account activity structure
                assert "account" in activity
                assert "period" in activity
                assert "opening_balance" in activity
                assert "closing_balance" in activity
                assert "entries" in activity
                assert "total_debits" in activity
                assert "total_credits" in activity
                self.log_result("Account Activity Structure", True, "Account activity has required structure")
                
                # Verify account information
                assert activity["account"]["id"] == self.cash_account.pk
                assert activity["account"]["name"] == self.cash_account.name
                self.log_result("Account Activity Info", True, "Account information correctly displayed")
                
                return True
                
        except Exception as e:
            self.log_error(f"Reporting capabilities test failed: {str(e)}")
            return False

    def test_transaction_reversals(self):
        """Test transaction reversal mechanisms."""
        print("\n=== Testing Transaction Reversals ===")
        
        try:
            with patch('accounting.utils.get_audit_user_and_metadata') as mock_get_metadata:
                mock_get_metadata.return_value = (self.accountant, "192.168.1.1", "Test Browser")
                
                # Create a journal for reversal tests
                journal = create_journal(
                    description="Reversal Test Journal",
                    date=date.today(),
                    period=self.periods[0],
                    entries=[
                        {"account": self.cash_account, "entry_type": "DEBIT", "amount": 4000},
                        {"account": self.all_accounts[1], "entry_type": "CREDIT", "amount": 3000},
                        {"account": self.all_accounts[2], "entry_type": "CREDIT", "amount": 1000},
                    ],
                    created_by=self.accountant,
                )
                journal.approve(self.accountant)
                post_journal(journal, self.accountant)
                
                # Test full reversal
                reversal_journal = reverse_journal(journal, self.accountant, "Full reversal test")
                
                assert reversal_journal.status == Journal.JournalStatus.POSTED
                assert reversal_journal.description.startswith("REVERSAL:")
                self.log_result("Full Reversal", True, "Full reversal journal created")
                
                # Verify reversal entries are opposite of original
                original_entries = JournalEntry.objects.filter(journal=journal)
                reversal_entries = JournalEntry.objects.filter(journal=reversal_journal)
                
                assert original_entries.count() == reversal_entries.count()
                for orig_entry in original_entries:
                    rev_entry = reversal_entries.get(account=orig_entry.account)
                    assert orig_entry.amount == rev_entry.amount
                    assert orig_entry.entry_type != rev_entry.entry_type
                
                self.log_result("Reversal Entry Validation", True, "Reversal entries correctly opposite to original")
                
                # Create another journal for partial reversal
                journal2 = create_journal(
                    description="Partial Reversal Test",
                    date=date.today(),
                    period=self.periods[1],
                    entries=[
                        {"account": self.cash_account, "entry_type": "DEBIT", "amount": 5000},
                        {"account": self.all_accounts[1], "entry_type": "CREDIT", "amount": 3000},
                        {"account": self.all_accounts[2], "entry_type": "CREDIT", "amount": 2000},
                    ],
                    created_by=self.accountant,
                )
                journal2.approve(self.accountant)
                post_journal(journal2, self.accountant)
                
                # Test partial reversal
                partial_reversal = reverse_journal_partial(
                    journal2,
                    [self.all_accounts[1]],  # Reverse only the 3000 credit entry
                    self.accountant,
                    "Partial reversal test"
                )
                
                assert partial_reversal.status == Journal.JournalStatus.POSTED
                self.log_result("Partial Reversal", True, "Partial reversal journal created")
                
                # Verify partial reversal entries
                partial_entries = JournalEntry.objects.filter(journal=partial_reversal)
                assert partial_entries.count() == 2  # One debit, one credit entry
                
                total_debits = sum(entry.amount for entry in partial_entries if entry.entry_type == "DEBIT")
                total_credits = sum(entry.amount for entry in partial_entries if entry.entry_type == "CREDIT")
                assert total_debits == total_credits == Decimal('3000.00')
                self.log_result("Partial Reversal Balance", True, f"Partial reversal balances: {total_debits}")
                
                # Create another journal for reversal with correction
                journal3 = create_journal(
                    description="Reversal with Correction Test",
                    date=date.today(),
                    period=self.periods[2],
                    entries=[
                        {"account": self.cash_account, "entry_type": "DEBIT", "amount": 2000},
                        {"account": self.all_accounts[1], "entry_type": "CREDIT", "amount": 2000},
                    ],
                    created_by=self.accountant,
                )
                journal3.approve(self.accountant)
                post_journal(journal3, self.accountant)
                
                # Test reversal with correction
                correction_entries = [
                    {"account": self.cash_account, "entry_type": "DEBIT", "amount": 2500},  # Corrected amount
                    {"account": self.all_accounts[1], "entry_type": "CREDIT", "amount": 2500},
                ]
                
                reversal_journal3, correction_journal = reverse_journal_with_correction(
                    journal3,
                    correction_entries,
                    self.accountant,
                    "Correction of amount from 2000 to 2500"
                )
                
                assert reversal_journal3.status == Journal.JournalStatus.POSTED
                assert correction_journal.status == Journal.JournalStatus.POSTED
                self.log_result("Reversal with Correction", True, "Reversal with correction created")
                
                # Verify correction entries
                correction_entry_list = JournalEntry.objects.filter(journal=correction_journal)
                assert correction_entry_list.count() == 2
                
                for entry_data in correction_entries:
                    entry = correction_entry_list.get(account=entry_data["account"])
                    assert entry.amount == entry_data["amount"]
                    assert entry.entry_type == entry_data["entry_type"]
                
                self.log_result("Correction Entry Validation", True, "Correction entries correctly created")
                
                # Test batch reversal
                journals = [journal, journal2, journal3]
                batch_reversals = reverse_batch_journals(
                    journals,
                    self.accountant,
                    "Batch reversal test"
                )
                
                assert len(batch_reversals) == len(journals)
                for reversal in batch_reversals:
                    assert reversal.status == Journal.JournalStatus.POSTED
                
                self.log_result("Batch Reversal", True, f"Batch reversal created for {len(journals)} journals")
                
                return True
                
        except Exception as e:
            self.log_error(f"Transaction reversals test failed: {str(e)}")
            return False

    def test_data_integrity(self):
        """Test data integrity throughout the system."""
        print("\n=== Testing Data Integrity ===")
        
        try:
            with patch('accounting.utils.get_audit_user_and_metadata') as mock_get_metadata:
                mock_get_metadata.return_value = (self.accountant, "192.168.1.1", "Test Browser")
                
                # Create a comprehensive set of journals
                total_amount = Decimal('0')
                for i in range(10):
                    amount = Decimal('1000') * (i + 1)
                    total_amount += amount
                    
                    journal = create_journal(
                        description=f"Data Integrity Test {i+1}",
                        date=date.today(),
                        period=self.periods[0],
                        entries=[
                            {"account": self.cash_account, "entry_type": "DEBIT", "amount": amount},
                            {"account": self.all_accounts[i % len(self.all_accounts)], "entry_type": "CREDIT", "amount": amount},
                        ],
                        created_by=self.accountant,
                    )
                    journal.approve(self.accountant)
                    post_journal(journal, self.accountant)
                
                # Generate trial balance and verify it balances
                trial_balance = generate_trial_balance(self.periods[0])
                assert trial_balance["is_balanced"] == True
                assert trial_balance["total_debits"] == trial_balance["total_credits"] == total_amount
                self.log_result("Trial Balance Integrity", True, f"Trial balance balances with total: {total_amount}")
                
                # Verify account balances are correct
                cash_activity = generate_account_activity(self.cash_account, self.periods[0])
                assert cash_activity["total_debits"] == total_amount
                assert cash_activity["total_credits"] == Decimal('0')
                assert cash_activity["closing_balance"] == total_amount
                self.log_result("Account Balance Integrity", True, f"Cash account balance: {cash_activity['closing_balance']}")
                
                # Test period closure maintains integrity
                close_accounting_period(self.periods[0], self.accountant)
                self.periods[0].refresh_from_db()
                assert self.periods[0].is_closed == True
                self.log_result("Period Closure Integrity", True, "Period closed successfully")
                
                # Verify audit trail integrity
                audit_entries = AccountingAuditTrail.objects.filter(
                    content_type=ContentType.objects.get_for_model(Journal),
                )
                assert len(audit_entries) > 0
                self.log_result("Audit Trail Integrity", True, f"Found {len(audit_entries)} audit entries")
                
                # Test that closed period prevents modifications
                try:
                    new_journal = create_journal(
                        description="Should Fail",
                        date=date.today(),
                        period=self.periods[0],  # Closed period
                        entries=[
                            {"account": self.cash_account, "entry_type": "DEBIT", "amount": 1000},
                            {"account": self.all_accounts[0], "entry_type": "CREDIT", "amount": 1000},
                        ],
                        created_by=self.accountant,
                    )
                    self.log_result("Closed Period Protection", False, "Journal created in closed period")
                except Exception:
                    self.log_result("Closed Period Protection", True, "Journal creation in closed period correctly prevented")
                
                return True
                
        except Exception as e:
            self.log_error(f"Data integrity test failed: {str(e)}")
            return False

    def test_role_based_permissions(self):
        """Test role-based access controls."""
        print("\n=== Testing Role-Based Permissions ===")
        
        try:
            with patch('accounting.utils.get_audit_user_and_metadata') as mock_get_metadata:
                mock_get_metadata.return_value = (self.accountant, "192.168.1.1", "Test Browser")
                
                # Create a journal as accountant
                journal = create_journal(
                    description="Permission Test Journal",
                    date=date.today(),
                    period=self.periods[1],
                    entries=[
                        {"account": self.cash_account, "entry_type": "DEBIT", "amount": 1000},
                        {"account": self.all_accounts[1], "entry_type": "CREDIT", "amount": 1000},
                    ],
                    created_by=self.accountant,
                )
                
                # Test accountant permissions
                assert journal.can_approve(self.accountant) == True
                self.log_result("Accountant Approve Permission", True, "Accountant can approve journal")
                
                # Test auditor permissions
                assert journal.can_view(self.auditor) == True
                self.log_result("Auditor View Permission", True, "Auditor can view journal")
                
                # Test regular user permissions
                assert journal.can_approve(self.regular_user) == False
                self.log_result("Regular User Restricted", True, "Regular user cannot approve journal")
                
                # Approve and post journal
                journal.approve(self.accountant)
                post_journal(journal, self.accountant)
                
                # Test reversal permissions
                reversal_journal = reverse_journal(journal, self.auditor, "Auditor reversal")
                assert reversal_journal is not None
                self.log_result("Auditor Reversal Permission", True, "Auditor can reverse journal")
                
                # Test period closing permissions
                close_accounting_period(self.periods[1], self.accountant)
                self.log_result("Accountant Period Close", True, "Accountant can close period")
                
                close_accounting_period(self.periods[2], self.auditor)
                self.log_result("Auditor Period Close", True, "Auditor can close period")
                
                # Test fiscal year closing
                close_fiscal_year(self.fiscal_year, self.accountant)
                self.log_result("Accountant FY Close", True, "Accountant can close fiscal year")
                
                return True
                
        except Exception as e:
            self.log_error(f"Role-based permissions test failed: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all end-to-end tests."""
        print("=" * 80)
        print("ACCOUNTING SYSTEM END-TO-END TEST SUITE")
        print("=" * 80)
        
        # Setup the system
        if not self.setup_complete_accounting_system():
            return False
        
        # Run all test suites
        test_suites = [
            self.test_double_entry_bookkeeping,
            self.test_payroll_integration,
            self.test_audit_trail_functionality,
            self.test_reporting_capabilities,
            self.test_transaction_reversals,
            self.test_data_integrity,
            self.test_role_based_permissions,
        ]
        
        for test_suite in test_suites:
            try:
                test_suite()
            except Exception as e:
                self.log_error(f"Test suite {test_suite.__name__} failed with exception: {str(e)}")
        
        # Print summary
        self.print_summary()
        
        # Return True if all tests passed
        failed_tests = [result for result in self.results if result[1] == "FAIL"]
        return len(failed_tests) == 0

    def print_summary(self):
        """Print a summary of all test results."""
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        passed = len([result for result in self.results if result[1] == "PASS"])
        failed = len([result for result in self.results if result[1] == "FAIL"])
        total = len(self.results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "0%")
        
        if self.warnings:
            print(f"\nWarnings: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        if self.errors:
            print(f"\nErrors: {len(self.errors)}")
            for error in self.errors:
                print(f"  - {error}")
        
        if failed > 0:
            print(f"\nFailed Tests:")
            for test_name, status, message in self.results:
                if status == "FAIL":
                    print(f"  - {test_name}: {message}")
        
        print("\n" + "=" * 80)


def main():
    """Main function to run the end-to-end tests."""
    runner = EndToEndTestRunner()
    success = runner.run_all_tests()
    
    if success:
        print("\n🎉 All end-to-end tests passed! The accounting system is working correctly.")
        return 0
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())