#!/usr/bin/env python
"""
Test script to verify that the transaction fix works correctly.
This simulates creating an account through the admin interface.
"""

import os
import sys
import django

# Setup Django
sys.path.append("/opt/usr/devs/payroll/paroll")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth import get_user_model
from accounting.models import Account, AccountingAuditTrail
from django.db import transaction


def test_account_creation():
    """Test creating an account to verify transaction fix"""
    print("Testing account creation...")

    try:
        # Test creating an account within a transaction (similar to admin)
        with transaction.atomic():
            account = Account.objects.create(
                name="Test Account",
                account_number="9999",
                type=Account.AccountType.ASSET,
                description="Test account for transaction fix verification",
            )
            print(f"✓ Account created successfully: {account.name} (ID: {account.id})")

            # Check if audit trail was created
            audit_entries = AccountingAuditTrail.objects.filter(
                object_id=account.id, action=AccountingAuditTrail.ActionType.CREATE
            )
            if audit_entries.exists():
                print(f"✓ Audit trail entry created: {audit_entries.count()} entries")
                for entry in audit_entries:
                    print(f"  - Action: {entry.action}, Reason: {entry.reason}")
            else:
                print("⚠ No audit trail entries found")

    except Exception as e:
        print(f"✗ Error creating account: {str(e)}")
        import traceback

        traceback.print_exc()


def test_transaction_error_scenario():
    """Test a scenario that might cause transaction issues"""
    print("\nTesting transaction error scenario...")

    try:
        # Simulate a broken transaction scenario
        with transaction.atomic():
            # Create an account first
            account = Account.objects.create(
                name="Test Account 2",
                account_number="9998",
                type=Account.AccountType.LIABILITY,
                description="Test account for error scenario",
            )
            print(f"✓ First account created: {account.name}")

            # Try to create another account that might trigger the error
            try:
                # This would normally cause the transaction error
                bad_account = Account.objects.create(
                    name="",  # This might cause validation error
                    account_number="",
                    type=Account.AccountType.ASSET,
                    description="",
                )
            except Exception as validation_error:
                print(f"Expected validation error: {validation_error}")

            # Even with validation error, audit trail should work for the first account
            audit_entries = AccountingAuditTrail.objects.filter(
                object_id=account.id, action=AccountingAuditTrail.ActionType.CREATE
            )
            if audit_entries.exists():
                print(
                    f"✓ Audit trail still works despite error: {audit_entries.count()} entries"
                )
            else:
                print("⚠ No audit trail entries found after error")

    except Exception as e:
        print(f"✗ Error in transaction test: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("Testing Django transaction fix for accounting audit trail...")
    print("=" * 60)

    test_account_creation()
    test_transaction_error_scenario()

    print("\n" + "=" * 60)
    print("Test completed!")
