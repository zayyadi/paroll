"""
Test script to verify auditor role and permissions implementation
"""

import os
import sys
import django

# Setup Django environment
sys.path.append("/opt/usr/devs/payroll/paroll")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth import get_user_model
from accounting.permissions import (
    setup_accounting_groups_and_permissions,
    is_auditor,
    is_accountant,
    is_payroll_processor,
    can_approve_journal,
    can_reverse_journal,
    can_close_period,
    can_view_payroll_data,
    can_modify_payroll_data,
    assign_user_to_auditor_role,
    assign_user_to_accountant_role,
    assign_user_to_payroll_processor_role,
)
from accounting.models import Account, Journal, AccountingPeriod, FiscalYear
from payroll.models import EmployeeProfile, Payroll

User = get_user_model()


def test_permissions_setup():
    """Test setting up accounting groups and permissions"""
    print("Testing accounting permissions setup...")

    # Set up groups and permissions
    setup_accounting_groups_and_permissions()

    # Create test users if they don't exist
    auditor_user, _ = User.objects.get_or_create(
        email="auditor@test.com",
        defaults={"first_name": "Test", "last_name": "Auditor", "is_staff": True},
    )

    accountant_user, _ = User.objects.get_or_create(
        email="accountant@test.com",
        defaults={"first_name": "Test", "last_name": "Accountant", "is_staff": True},
    )

    payroll_user, _ = User.objects.get_or_create(
        email="payroll@test.com",
        defaults={"first_name": "Test", "last_name": "Payroll", "is_staff": True},
    )

    # Assign users to roles
    assign_user_to_auditor_role(auditor_user)
    assign_user_to_accountant_role(accountant_user)
    assign_user_to_payroll_processor_role(payroll_user)

    print("✓ Created test users and assigned roles")
    return auditor_user, accountant_user, payroll_user


def test_role_checks(auditor_user, accountant_user, payroll_user):
    """Test role checking functions"""
    print("\nTesting role checking functions...")

    assert is_auditor(auditor_user), "Auditor role check failed"
    assert not is_auditor(
        accountant_user
    ), "Non-auditor incorrectly identified as auditor"
    assert not is_auditor(payroll_user), "Non-auditor incorrectly identified as auditor"

    assert is_accountant(accountant_user), "Accountant role check failed"
    assert not is_accountant(
        auditor_user
    ), "Non-accountant incorrectly identified as accountant"
    assert not is_accountant(
        payroll_user
    ), "Non-accountant incorrectly identified as accountant"

    assert is_payroll_processor(payroll_user), "Payroll processor role check failed"
    assert not is_payroll_processor(
        auditor_user
    ), "Non-payroll processor incorrectly identified as payroll processor"
    assert not is_payroll_processor(
        accountant_user
    ), "Non-payroll processor incorrectly identified as payroll processor"

    print("✓ All role checks passed")


def test_permission_functions(auditor_user, accountant_user, payroll_user):
    """Test permission checking functions"""
    print("\nTesting permission functions...")

    # Create test objects for permission testing
    test_account, _ = Account.objects.get_or_create(
        name="Test Account", account_number="9999", type="ASSET"
    )

    # Test payroll data access
    assert can_view_payroll_data(
        auditor_user
    ), "Auditor should be able to view payroll data"
    assert can_view_payroll_data(
        accountant_user
    ), "Accountant should be able to view payroll data"
    assert can_view_payroll_data(
        payroll_user
    ), "Payroll processor should be able to view payroll data"

    assert not can_modify_payroll_data(
        auditor_user
    ), "Auditor should not be able to modify payroll data"
    assert not can_modify_payroll_data(
        accountant_user
    ), "Accountant should not be able to modify payroll data"
    assert can_modify_payroll_data(
        payroll_user
    ), "Payroll processor should be able to modify payroll data"

    print("✓ Payroll data access permissions correct")

    # Test journal permissions
    test_journal = Journal.objects.create(
        description="Test Journal", created_by=accountant_user
    )

    assert can_approve_journal(
        auditor_user, test_journal
    ), "Auditor should be able to approve journal"
    assert not can_approve_journal(
        accountant_user, test_journal
    ), "Accountant should not be able to approve their own journal"
    assert can_reverse_journal(
        auditor_user, test_journal
    ), "Auditor should be able to reverse journal"
    assert not can_reverse_journal(
        accountant_user, test_journal
    ), "Accountant should not be able to reverse journal"
    assert not can_reverse_journal(
        payroll_user, test_journal
    ), "Payroll processor should not be able to reverse journal"

    print("✓ Journal permissions correct")

    # Test period closing permissions
    test_period, _ = AccountingPeriod.objects.get_or_create(
        name="Test Period",
        period_number=13,
        fiscal_year=FiscalYear.objects.get_or_create(year=2023)[0],
    )

    assert can_close_period(
        auditor_user, test_period
    ), "Auditor should be able to close period"
    assert not can_close_period(
        accountant_user, test_period
    ), "Accountant should not be able to close period"
    assert not can_close_period(
        payroll_user, test_period
    ), "Payroll processor should not be able to close period"

    print("✓ Period closing permissions correct")


def test_integration():
    """Test integration between accounting and payroll systems"""
    print("\nTesting integration...")

    # Check that accounting models are accessible
    assert Account.objects.count() >= 0, "Account model not accessible"
    assert Journal.objects.count() >= 0, "Journal model not accessible"
    assert (
        AccountingPeriod.objects.count() >= 0
    ), "AccountingPeriod model not accessible"
    assert FiscalYear.objects.count() >= 0, "FiscalYear model not accessible"

    # Check that payroll models are accessible
    assert EmployeeProfile.objects.count() >= 0, "EmployeeProfile model not accessible"
    assert Payroll.objects.count() >= 0, "Payroll model not accessible"

    print("✓ Integration test passed")


def main():
    """Run all tests"""
    print("Starting auditor permissions test...\n")

    try:
        # Test setup
        auditor_user, accountant_user, payroll_user = test_permissions_setup()

        # Test role checks
        test_role_checks(auditor_user, accountant_user, payroll_user)

        # Test permission functions
        test_permission_functions(auditor_user, accountant_user, payroll_user)

        # Test integration
        test_integration()

        print("\n✅ All tests passed successfully!")
        print("\nAuditor role and permissions implementation is working correctly.")

    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
