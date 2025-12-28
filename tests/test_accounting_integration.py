#!/usr/bin/env python
"""
Test script to verify payroll accounting integration
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from decimal import Decimal
from django.utils import timezone
from datetime import date
from payroll.models import EmployeeProfile, Payroll, PayT, IOU, Allowance, Deduction
from accounting.models import (
    Account,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
    FiscalYear,
    AccountingPeriod,
)
from accounting.utils import get_account_balance_as_of, get_trial_balance


def test_payroll_accounts():
    """Test that all required payroll accounts exist"""
    print("Testing payroll account creation...")

    required_accounts = [
        ("Salaries and Wages Expense", "6010"),
        ("Allowances Expense", "6015"),
        ("Pension Expense (Employer)", "6020"),
        ("Health Contribution Expense (Employer)", "6030"),
        ("NSITF Expense", "6040"),
        ("Cash and Cash Equivalents", "1010"),
        ("Bank Accounts", "1020"),
        ("Employee Advances", "1400"),
        ("PAYE Tax Payable", "2110"),
        ("Pension Payable", "2120"),
        ("Health Contribution Payable", "2130"),
        ("NSITF Payable", "2140"),
        ("NHF Payable", "2150"),
        ("Other Deductions Payable", "2160"),
    ]

    for name, number in required_accounts:
        account = Account.objects.filter(account_number=number).first()
        if account:
            print(f"✓ Account found: {name} ({number})")
        else:
            print(f"✗ Account missing: {name} ({number})")

    print("Account test completed.\n")


def test_payroll_signals():
    """Test payroll signal handlers"""
    print("Testing payroll signal handlers...")

    # Test 1: Check if we can create a test employee
    try:
        employee = EmployeeProfile.objects.first()
        if not employee:
            print("✗ No employee found for testing")
            return False

        print(f"✓ Found employee: {employee.first_name} {employee.last_name}")

        # Test 2: Check if employee has payroll
        payroll = employee.employee_pay
        if payroll:
            print(f"✓ Found payroll record with basic salary: {payroll.basic_salary}")
        else:
            print("✗ No payroll record found for employee")
            return False

        # Test 3: Check if there are any payroll periods
        pay_periods = PayT.objects.all()[:3]  # Get last 3 periods
        if pay_periods:
            print(f"✓ Found {pay_periods.count()} payroll periods")
            for period in pay_periods:
                print(f"  - Period: {period.save_month_str}, Closed: {period.closed}")
        else:
            print("✗ No payroll periods found")

        # Test 4: Check for any existing journals
        journals = Journal.objects.all()[:5]  # Get last 5 journals
        if journals:
            print(f"✓ Found {journals.count()} journal entries")
            for journal in journals:
                entries_count = journal.entries.count()
                debits = journal.entries.filter(entry_type="DEBIT").count()
                credits = journal.entries.filter(entry_type="CREDIT").count()
                print(
                    f"  - Journal {journal.transaction_number}: {journal.description} ({entries_count} entries, {debits} debits, {credits} credits)"
                )
        else:
            print("✗ No journal entries found")

        # Test 5: Check audit trail
        audit_entries = AccountingAuditTrail.objects.all()[
            :5
        ]  # Get last 5 audit entries
        if audit_entries:
            print(f"✓ Found {audit_entries.count()} audit trail entries")
            for audit in audit_entries:
                print(
                    f"  - {audit.action} on {audit.content_type} by {audit.user} at {audit.timestamp}"
                )
        else:
            print("✗ No audit trail entries found")

        return True
    except Exception as e:
        print(f"✗ Error testing payroll signals: {str(e)}")
        return False


def test_account_balances():
    """Test account balances"""
    print("\nTesting account balances...")

    # Get all payroll accounts
    accounts = Account.objects.filter(
        account_number__in=[
            "1010",
            "1020",
            "1400",
            "2110",
            "2120",
            "2130",
            "2140",
            "2150",
            "2160",
            "6010",
            "6015",
            "6020",
            "6030",
            "6040",
        ]
    )

    if not accounts:
        print("✗ No payroll accounts found")
        return

    for account in accounts:
        balance = account.balance
        print(f"  {account.name}: {balance} ({account.type})")

    # Test trial balance
    trial_balance = get_trial_balance()
    if trial_balance:
        total_debits = sum(item["debit_balance"] for item in trial_balance.values())
        total_credits = sum(item["credit_balance"] for item in trial_balance.values())
        print(f"\nTrial Balance: {total_debits} in debits, {total_credits} in credits")
        print(f"Difference: {total_debits - total_credits}")

        if abs(total_debits - total_credits) < 0.01:  # Allow for rounding
            print("✓ Trial balance is balanced")
        else:
            print("✗ Trial balance is not balanced")
    else:
        print("✗ Could not generate trial balance")


def main():
    """Main test function"""
    print("=" * 60)
    print("PAYROLL ACCOUNTING INTEGRATION TEST")
    print("=" * 60)

    test_payroll_accounts()
    test_payroll_signals()
    test_account_balances()

    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
