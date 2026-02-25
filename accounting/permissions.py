from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from .models import (
    Account,
    Journal,
    JournalEntry,
    FiscalYear,
    AccountingPeriod,
    AccountingAuditTrail,
    TransactionNumber,
)

User = get_user_model()


def setup_accounting_groups_and_permissions():
    """
    Set up accounting-specific groups and permissions including the Auditor role.
    This function creates the necessary groups and assigns appropriate permissions
    to ensure proper segregation of duties.
    """
    print("Setting up accounting groups and permissions...")

    # Create groups
    auditor_group, _ = Group.objects.get_or_create(name="Auditor")
    accountant_group, _ = Group.objects.get_or_create(name="Accountant")
    payroll_processor_group, _ = Group.objects.get_or_create(name="Payroll Processor")

    # Get content types for accounting models
    account_ct = ContentType.objects.get_for_model(Account)
    journal_ct = ContentType.objects.get_for_model(Journal)
    journal_entry_ct = ContentType.objects.get_for_model(JournalEntry)
    fiscal_year_ct = ContentType.objects.get_for_model(FiscalYear)
    period_ct = ContentType.objects.get_for_model(AccountingPeriod)
    audit_trail_ct = ContentType.objects.get_for_model(AccountingAuditTrail)
    transaction_number_ct = ContentType.objects.get_for_model(TransactionNumber)

    # Define permissions for each role

    # AUDITOR PERMISSIONS
    # Auditors can view everything but can only approve/reject and reverse transactions
    auditor_permissions = []

    # Account permissions (view only)
    auditor_permissions.extend(
        Permission.objects.filter(
            content_type=account_ct, codename__in=["view_account"]
        )
    )

    # Journal permissions (view, approve, reverse)
    auditor_permissions.extend(
        Permission.objects.filter(
            content_type=journal_ct,
            codename__in=[
                "view_journal",
                "change_journal",  # For approve/reject
                "add_journal",  # For reversal journals
            ],
        )
    )

    # Journal Entry permissions (view only)
    auditor_permissions.extend(
        Permission.objects.filter(
            content_type=journal_entry_ct, codename__in=["view_journalentry"]
        )
    )

    # Fiscal Year permissions (view only)
    auditor_permissions.extend(
        Permission.objects.filter(
            content_type=fiscal_year_ct, codename__in=["view_fiscalyear"]
        )
    )

    # Accounting Period permissions (view and close)
    auditor_permissions.extend(
        Permission.objects.filter(
            content_type=period_ct,
            codename__in=["view_accountingperiod", "change_accountingperiod"],
        )
    )

    # Audit Trail permissions (full access)
    auditor_permissions.extend(
        Permission.objects.filter(
            content_type=audit_trail_ct,
            codename__in=[
                "view_accountingaudittrail",
                "add_accountingaudittrail",
                "change_accountingaudittrail",
            ],
        )
    )

    # Assign permissions to Auditor group
    auditor_group.permissions.set(auditor_permissions)
    print(f"Configured Auditor group with {len(auditor_permissions)} permissions.")

    # ACCOUNTANT PERMISSIONS
    # Accountants can create and modify journals but cannot approve their own
    accountant_permissions = []

    # Full account management
    accountant_permissions.extend(
        Permission.objects.filter(
            content_type=account_ct,
            codename__in=["view_account", "add_account", "change_account"],
        )
    )

    # Full journal management (except delete)
    accountant_permissions.extend(
        Permission.objects.filter(
            content_type=journal_ct,
            codename__in=["view_journal", "add_journal", "change_journal"],
        )
    )

    # Full journal entry management
    accountant_permissions.extend(
        Permission.objects.filter(
            content_type=journal_entry_ct,
            codename__in=[
                "view_journalentry",
                "add_journalentry",
                "change_journalentry",
            ],
        )
    )

    # Fiscal year view permissions
    accountant_permissions.extend(
        Permission.objects.filter(
            content_type=fiscal_year_ct, codename__in=["view_fiscalyear"]
        )
    )

    # Accounting period view permissions
    accountant_permissions.extend(
        Permission.objects.filter(
            content_type=period_ct, codename__in=["view_accountingperiod"]
        )
    )

    # Read-only audit trail access
    accountant_permissions.extend(
        Permission.objects.filter(
            content_type=audit_trail_ct, codename__in=["view_accountingaudittrail"]
        )
    )

    # Assign permissions to Accountant group
    accountant_group.permissions.set(accountant_permissions)
    print(
        f"Configured Accountant group with {len(accountant_permissions)} permissions."
    )

    # PAYROLL PROCESSOR PERMISSIONS
    # Payroll processors have limited access to accounting for payroll-related transactions
    payroll_processor_permissions = []

    # View-only access to accounts
    payroll_processor_permissions.extend(
        Permission.objects.filter(
            content_type=account_ct, codename__in=["view_account"]
        )
    )

    # Can create journals but cannot modify or approve
    payroll_processor_permissions.extend(
        Permission.objects.filter(
            content_type=journal_ct, codename__in=["view_journal", "add_journal"]
        )
    )

    # Can create journal entries
    payroll_processor_permissions.extend(
        Permission.objects.filter(
            content_type=journal_entry_ct,
            codename__in=["view_journalentry", "add_journalentry"],
        )
    )

    # View-only access to periods and fiscal years
    payroll_processor_permissions.extend(
        Permission.objects.filter(
            content_type=fiscal_year_ct, codename__in=["view_fiscalyear"]
        )
    )
    payroll_processor_permissions.extend(
        Permission.objects.filter(
            content_type=period_ct, codename__in=["view_accountingperiod"]
        )
    )

    # Assign permissions to Payroll Processor group
    payroll_processor_group.permissions.set(payroll_processor_permissions)
    print(
        f"Configured Payroll Processor group with {len(payroll_processor_permissions)} permissions."
    )

    print("Accounting groups and permissions configuration complete.")


def assign_user_to_auditor_role(user):
    """
    Assign a user to the auditor role
    """
    auditor_group = Group.objects.get(name="Auditor")
    user.groups.add(auditor_group)
    print(f"User {user.email} assigned to Auditor role.")


def assign_user_to_accountant_role(user):
    """
    Assign a user to the accountant role
    """
    accountant_group = Group.objects.get(name="Accountant")
    user.groups.add(accountant_group)
    print(f"User {user.email} assigned to Accountant role.")


def assign_user_to_payroll_processor_role(user):
    """
    Assign a user to the payroll processor role
    """
    payroll_processor_group = Group.objects.get(name="Payroll Processor")
    user.groups.add(payroll_processor_group)
    print(f"User {user.email} assigned to Payroll Processor role.")


def is_auditor(user):
    """
    Check if user has auditor role or is superuser
    """
    return user.is_superuser or user.groups.filter(name="Auditor").exists()


def is_accountant(user):
    """
    Check if user has accountant role or is superuser
    """
    return user.is_superuser or user.groups.filter(name="Accountant").exists()


def is_payroll_processor(user):
    """
    Check if user has payroll processor role or is superuser
    """
    return user.is_superuser or user.groups.filter(name="Payroll Processor").exists()


def is_hr_staff(user):
    """
    Check if user has HR-facing access based on payroll employee management permission.
    """
    return user.is_superuser or user.has_perm("payroll.view_employeeprofile")


def can_access_disciplinary(user):
    """
    Check if user can access disciplinary pages.
    """
    return (
        user.is_superuser
        or is_auditor(user)
        or is_accountant(user)
        or is_payroll_processor(user)
        or is_hr_staff(user)
    )


def can_manage_disciplinary_case(user):
    """
    Check if user can decide, sanction, or review appeals for disciplinary cases.
    """
    return user.is_superuser or is_auditor(user) or is_accountant(user) or is_hr_staff(
        user
    )


def can_approve_journal(user, journal):
    """
    Check if user can approve a journal
    - Superusers can approve any journal
    - Auditors can approve any journal
    - Accountants cannot approve journals they created
    """
    if user.is_superuser:
        return True

    if is_auditor(user):
        return True

    if is_accountant(user):
        # Accountants cannot approve their own journals
        return journal.created_by != user

    return False


def can_reverse_journal(user, journal):
    """
    Check if user can reverse a journal
    - Superusers can reverse any journal
    - Only auditors can reverse journals
    - Journal must be posted
    - Journal must not already be reversed
    - Journal's period must not be closed
    """
    if user.is_superuser:
        return True

    if not is_auditor(user):
        return False

    if journal.status != Journal.JournalStatus.POSTED:
        return False

    if journal.reversed_journal:
        return False

    if journal.period.is_closed:
        return False

    return True


def can_partial_reverse_journal(user, journal):
    """
    Check if user can partially reverse a journal
    - Superusers can partially reverse any journal
    - Only auditors can partially reverse journals
    - Journal must be posted
    - Journal's period must not be closed
    """
    if user.is_superuser:
        return True

    if not is_auditor(user):
        return False

    if journal.status != Journal.JournalStatus.POSTED:
        return False

    if journal.period.is_closed:
        return False

    return True


def can_reverse_with_correction(user, journal):
    """
    Check if user can reverse with correction
    - Superusers can reverse with correction any journal
    - Only auditors can reverse with correction
    - Journal must be posted
    - Journal's period must not be closed
    """
    if user.is_superuser:
        return True

    if not is_auditor(user):
        return False

    if journal.status != Journal.JournalStatus.POSTED:
        return False

    if journal.period.is_closed:
        return False

    return True


def can_batch_reverse_journals(user):
    """
    Check if user can batch reverse journals
    - Superusers can batch reverse journals
    - Only auditors can batch reverse journals
    """
    return user.is_superuser or is_auditor(user)


def can_close_period(user, period):
    """
    Check if user can close an accounting period
    - Superusers can close periods
    - Only auditors can close periods
    """
    return user.is_superuser or is_auditor(user)


def can_view_payroll_data(user):
    """
    Check if user can view payroll data
    - Superusers can view payroll data (full access)
    - Auditors can view payroll data (read-only)
    - Accountants can view payroll data (read-only)
    - Payroll processors have full access to payroll data
    """
    return (
        user.is_superuser
        or is_auditor(user)
        or is_accountant(user)
        or is_payroll_processor(user)
    )


def can_modify_payroll_data(user):
    """
    Check if user can modify payroll data
    - Superusers can modify payroll data
    - Only payroll processors can modify payroll data
    """
    return user.is_superuser or is_payroll_processor(user)
