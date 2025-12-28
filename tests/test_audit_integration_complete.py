"""
Complete integration test for audit trail functionality.
This test verifies that all components of the audit trail system work together correctly.
"""

import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
from django.test import TestCase, TransactionTestCase
from django.core.management import call_command
from io import StringIO

from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from accounting.utils import (
    create_journal_with_entries,
    post_journal,
    reverse_journal,
    close_accounting_period,
    close_fiscal_year,
)
from accounting.middleware import set_audit_user, set_audit_metadata

User = get_user_model()


def test_complete_audit_trail_integration():
    """Test complete audit trail integration."""
    print("Starting complete audit trail integration test...")

    # Create test user
    user = User.objects.create_user(
        username="audit_test_user",
        email="audit_test@example.com",
        password="testpass123",
        first_name="Test",
        last_name="User",
    )

    # Set audit context
    set_audit_user(user)
    set_audit_metadata("192.168.1.100", "Integration Test Browser")

    print(f"✓ Created test user: {user}")

    # Test 1: Account Creation and Modification
    print("\n=== Test 1: Account Operations ===")

    account = Account.objects.create(
        name="Integration Test Account",
        account_number="9999",
        type=Account.AccountType.ASSET,
        description="Test account for integration",
    )
    print(f"✓ Created account: {account}")

    # Verify audit entry for account creation
    account_audit = AccountingAuditTrail.objects.filter(
        content_type__model="account",
        object_id=account.pk,
        action=AccountingAuditTrail.ActionType.CREATE,
    ).first()

    assert account_audit is not None, "Account creation audit entry missing"
    assert account_audit.user == user, "Account creation audit entry has wrong user"
    print(f"✓ Account creation audit entry verified: {account_audit}")

    # Modify account
    account.description = "Updated description for integration test"
    account.save()
    print(f"✓ Updated account: {account}")

    # Verify audit entry for account update
    account_update_audit = AccountingAuditTrail.objects.filter(
        content_type__model="account",
        object_id=account.pk,
        action=AccountingAuditTrail.ActionType.UPDATE,
    ).first()

    assert account_update_audit is not None, "Account update audit entry missing"
    print(f"✓ Account update audit entry verified: {account_update_audit}")

    # Test 2: Fiscal Year Operations
    print("\n=== Test 2: Fiscal Year Operations ===")

    fiscal_year = FiscalYear.objects.create(
        year=2024,
        name="Integration Test FY",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        is_active=True,
    )
    print(f"✓ Created fiscal year: {fiscal_year}")

    # Verify audit entry for fiscal year creation
    fy_audit = AccountingAuditTrail.objects.filter(
        content_type__model="fiscalyear",
        object_id=fiscal_year.pk,
        action=AccountingAuditTrail.ActionType.CREATE,
    ).first()

    assert fy_audit is not None, "Fiscal year creation audit entry missing"
    print(f"✓ Fiscal year creation audit entry verified: {fy_audit}")

    # Create accounting period
    period = AccountingPeriod.objects.create(
        fiscal_year=fiscal_year,
        period_number=6,
        name="June",
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
        is_active=True,
    )
    print(f"✓ Created accounting period: {period}")

    # Verify audit entry for period creation
    period_audit = AccountingAuditTrail.objects.filter(
        content_type__model="accountingperiod",
        object_id=period.pk,
        action=AccountingAuditTrail.ActionType.CREATE,
    ).first()

    assert period_audit is not None, "Period creation audit entry missing"
    print(f"✓ Period creation audit entry verified: {period_audit}")

    # Test 3: Complete Journal Workflow
    print("\n=== Test 3: Complete Journal Workflow ===")

    # Create additional accounts for journal entries
    cash_account = Account.objects.create(
        name="Integration Cash", account_number="1002", type=Account.AccountType.ASSET
    )
    revenue_account = Account.objects.create(
        name="Integration Revenue",
        account_number="4002",
        type=Account.AccountType.REVENUE,
    )
    print(f"✓ Created additional accounts for journal testing")

    # Create journal with entries
    entries = [
        {
            "account": cash_account,
            "entry_type": "DEBIT",
            "amount": 5000.00,
            "memo": "Cash received for integration test",
        },
        {
            "account": revenue_account,
            "entry_type": "CREDIT",
            "amount": 5000.00,
            "memo": "Revenue earned for integration test",
        },
    ]

    journal = create_journal_with_entries(
        date=date(2024, 6, 15),
        description="Integration Test Journal",
        entries=entries,
        fiscal_year=fiscal_year,
        period=period,
        user=user,
    )
    print(f"✓ Created journal: {journal}")

    # Verify audit entry for journal creation
    journal_audit = AccountingAuditTrail.objects.filter(
        content_type__model="journal",
        object_id=journal.pk,
        action=AccountingAuditTrail.ActionType.CREATE,
    ).first()

    assert journal_audit is not None, "Journal creation audit entry missing"
    print(f"✓ Journal creation audit entry verified: {journal_audit}")

    # Post the journal
    post_journal(journal, user)
    print(f"✓ Posted journal: {journal}")

    # Verify audit entry for journal posting
    journal_post_audit = AccountingAuditTrail.objects.filter(
        content_type__model="journal",
        object_id=journal.pk,
        action=AccountingAuditTrail.ActionType.POST,
    ).first()

    assert journal_post_audit is not None, "Journal posting audit entry missing"
    print(f"✓ Journal posting audit entry verified: {journal_post_audit}")

    # Test 4: Journal Reversal
    print("\n=== Test 4: Journal Reversal ===")

    reversal_journal = reverse_journal(journal, user, "Integration test reversal")
    print(f"✓ Reversed journal: {journal}")
    print(f"✓ Created reversal journal: {reversal_journal}")

    # Verify audit entry for journal reversal
    journal_reverse_audit = AccountingAuditTrail.objects.filter(
        content_type__model="journal",
        object_id=journal.pk,
        action=AccountingAuditTrail.ActionType.REVERSE,
    ).first()

    assert journal_reverse_audit is not None, "Journal reversal audit entry missing"
    print(f"✓ Journal reversal audit entry verified: {journal_reverse_audit}")

    # Verify audit entry for reversal journal creation
    reversal_create_audit = AccountingAuditTrail.objects.filter(
        content_type__model="journal",
        object_id=reversal_journal.pk,
        action=AccountingAuditTrail.ActionType.CREATE,
    ).first()

    assert (
        reversal_create_audit is not None
    ), "Reversal journal creation audit entry missing"
    print(f"✓ Reversal journal creation audit entry verified: {reversal_create_audit}")

    # Test 5: Period and Fiscal Year Closure
    print("\n=== Test 5: Period and Fiscal Year Closure ===")

    # Close the period
    close_accounting_period(period, user, "Integration test period closure")
    print(f"✓ Closed period: {period}")

    # Verify audit entry for period closure
    period_close_audit = AccountingAuditTrail.objects.filter(
        content_type__model="accountingperiod",
        object_id=period.pk,
        action=AccountingAuditTrail.ActionType.CLOSE_PERIOD,
    ).first()

    assert period_close_audit is not None, "Period closure audit entry missing"
    print(f"✓ Period closure audit entry verified: {period_close_audit}")

    # Close the fiscal year
    close_fiscal_year(fiscal_year, user, "Integration test fiscal year closure")
    print(f"✓ Closed fiscal year: {fiscal_year}")

    # Verify audit entry for fiscal year closure
    fy_close_audit = AccountingAuditTrail.objects.filter(
        content_type__model="fiscalyear",
        object_id=fiscal_year.pk,
        action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
    ).first()

    assert fy_close_audit is not None, "Fiscal year closure audit entry missing"
    print(f"✓ Fiscal year closure audit entry verified: {fy_close_audit}")

    # Test 6: Management Commands
    print("\n=== Test 6: Management Commands ===")

    # Test audit trail statistics command
    out = StringIO()
    call_command("audit_trail_management", "stats", stdout=out)
    stats_output = out.getvalue()

    assert "Audit Trail Statistics" in stats_output, "Stats command output missing"
    print("✓ Audit trail statistics command working")

    # Test audit trail verification command
    out = StringIO()
    call_command("audit_trail_management", "verify", stdout=out)
    verify_output = out.getvalue()

    assert "No integrity issues found" in verify_output, "Verify command found issues"
    print("✓ Audit trail verification command working")

    # Test 7: Data Integrity
    print("\n=== Test 7: Data Integrity ===")

    # Count total audit entries created
    total_audit_entries = AccountingAuditTrail.objects.count()
    print(f"✓ Total audit entries created: {total_audit_entries}")

    # Verify all audit entries have correct user attribution
    entries_with_wrong_user = AccountingAuditTrail.objects.exclude(user=user).count()
    assert (
        entries_with_wrong_user == 0
    ), f"Found {entries_with_wrong_user} entries with wrong user"
    print(f"✓ All audit entries have correct user attribution")

    # Verify all audit entries have IP address and user agent
    entries_without_ip = AccountingAuditTrail.objects.filter(
        ip_address__isnull=True
    ).count()
    assert (
        entries_without_ip == 0
    ), f"Found {entries_without_ip} entries without IP address"
    print(f"✓ All audit entries have IP address")

    entries_without_ua = AccountingAuditTrail.objects.filter(user_agent="").count()
    assert (
        entries_without_ua == 0
    ), f"Found {entries_without_ua} entries without user agent"
    print(f"✓ All audit entries have user agent")

    # Verify audit trail changes are properly serialized
    for audit_entry in AccountingAuditTrail.objects.all():
        assert isinstance(
            audit_entry.changes, dict
        ), f"Audit entry {audit_entry.id} has invalid changes format"

    print("✓ All audit trail changes are properly serialized")

    print("\n" + "=" * 60)
    print("🎉 ALL AUDIT TRAIL INTEGRATION TESTS PASSED! 🎉")
    print("=" * 60)

    # Summary
    print(f"\nSummary:")
    print(f"- Total audit entries: {total_audit_entries}")
    print(
        f"- Account operations: {AccountingAuditTrail.objects.filter(content_type__model='account').count()}"
    )
    print(
        f"- Fiscal year operations: {AccountingAuditTrail.objects.filter(content_type__model='fiscalyear').count()}"
    )
    print(
        f"- Period operations: {AccountingAuditTrail.objects.filter(content_type__model='accountingperiod').count()}"
    )
    print(
        f"- Journal operations: {AccountingAuditTrail.objects.filter(content_type__model='journal').count()}"
    )
    print(f"- All entries properly attributed to user: ✓")
    print(f"- All entries have IP address and user agent: ✓")
    print(f"- Data integrity maintained: ✓")

    return True


def test_middleware_integration():
    """Test middleware integration separately."""
    print("\n=== Testing Middleware Integration ===")

    from accounting.middleware import (
        get_request_user,
        get_request_metadata,
        set_audit_user,
        set_audit_metadata,
        get_audit_context,
    )

    # Test setting and getting audit context
    test_user = User.objects.first()
    set_audit_user(test_user)
    set_audit_metadata("10.0.0.1", "Test Agent")

    # Verify context retrieval
    retrieved_user = get_request_user()
    ip, ua = get_request_metadata()
    context = get_audit_context()

    assert retrieved_user == test_user, "User context not properly set/retrieved"
    assert ip == "10.0.0.1", "IP address not properly set/retrieved"
    assert ua == "Test Agent", "User agent not properly set/retrieved"
    assert context["user"] == test_user, "Context user not properly set"
    assert context["ip_address"] == "10.0.0.1", "Context IP not properly set"
    assert context["user_agent"] == "Test Agent", "Context user agent not properly set"

    print("✓ Middleware integration working correctly")
    return True


if __name__ == "__main__":
    try:
        # Run middleware integration test
        test_middleware_integration()

        # Run complete integration test
        test_complete_audit_trail_integration()

        print("\n🎉 ALL INTEGRATION TESTS COMPLETED SUCCESSFULLY! 🎉")
        print("\nThe audit trail system is fully integrated and working correctly.")
        print(
            "All accounting operations are being tracked with proper user attribution."
        )

    except Exception as e:
        print(f"\n❌ INTEGRATION TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
