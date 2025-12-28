"""
Simple test to verify auditor role and permissions implementation
"""

import os
import sys

# Add the project directory to Python path
sys.path.insert(0, "/opt/usr/devs/payroll/paroll")

# Test imports
try:
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
    )

    print("✓ Successfully imported accounting permissions")
except ImportError as e:
    print(f"✗ Failed to import accounting permissions: {e}")
    sys.exit(1)

try:
    from accounting.models import Account, Journal, AccountingPeriod, FiscalYear

    print("✓ Successfully imported accounting models")
except ImportError as e:
    print(f"✗ Failed to import accounting models: {e}")
    sys.exit(1)

try:
    from payroll.models import EmployeeProfile, Payroll

    print("✓ Successfully imported payroll models")
except ImportError as e:
    print(f"✗ Failed to import payroll models: {e}")
    sys.exit(1)

# Test permission functions
print("\nTesting permission functions...")


# Create mock user objects
class MockUser:
    def __init__(self, groups):
        self.groups = groups


class MockGroup:
    def __init__(self, name):
        self.name = name


# Test role checking
auditor_groups = [MockGroup("Auditor")]
accountant_groups = [MockGroup("Accountant")]
payroll_groups = [MockGroup("Payroll Processor")]

auditor_user = MockUser(auditor_groups)
accountant_user = MockUser(accountant_groups)
payroll_user = MockUser(payroll_groups)

# Test auditor role
assert is_auditor(auditor_user), "Auditor role check failed"
assert not is_auditor(accountant_user), "Non-auditor incorrectly identified as auditor"
assert not is_auditor(payroll_user), "Non-auditor incorrectly identified as auditor"

# Test accountant role
assert is_accountant(accountant_user), "Accountant role check failed"
assert not is_accountant(
    auditor_user
), "Non-accountant incorrectly identified as accountant"
assert not is_accountant(
    payroll_user
), "Non-accountant incorrectly identified as accountant"

# Test payroll processor role
assert is_payroll_processor(payroll_user), "Payroll processor role check failed"
assert not is_payroll_processor(
    auditor_user
), "Non-payroll processor incorrectly identified as payroll processor"
assert not is_payroll_processor(
    accountant_user
), "Non-payroll processor incorrectly identified as payroll processor"

print("✓ All role checks passed")

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

print("\n✅ All tests passed successfully!")
print("\nAuditor role and permissions implementation is working correctly.")
