from django.contrib.auth.models import Group, Permission
from django.http import HttpResponseForbidden
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
    Budget,
    TaxReturn,
    AccountReconciliation,
)

User = get_user_model()


def _split_user_and_object(first, second):
    if hasattr(first, "is_authenticated"):
        return first, second
    return second, first


def _view_permissions_for(*models):
    """Return the view_<model> permissions for the given models."""
    permissions = []
    for model in models:
        content_type = ContentType.objects.get_for_model(model)
        permissions.extend(
            Permission.objects.filter(
                content_type=content_type,
                codename__in=[f"view_{content_type.model}"],
            )
        )
    return permissions


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

    # Payroll model permissions so the role can actually run payroll:
    # pay periods, salary config, allowances/deductions, and payment files.
    # Delete is intentionally withheld for Payroll/PayrollRun (audit-sensitive).
    from payroll.models import Payroll, PayrollRun, Allowance, Deduction

    payroll_processor_payroll_models = {
        Payroll: ["view_payroll", "add_payroll", "change_payroll"],
        PayrollRun: ["view_payrollrun", "add_payrollrun", "change_payrollrun"],
        Allowance: [
            "view_allowance",
            "add_allowance",
            "change_allowance",
            "delete_allowance",
        ],
        Deduction: [
            "view_deduction",
            "add_deduction",
            "change_deduction",
            "delete_deduction",
        ],
    }
    for model, codenames in payroll_processor_payroll_models.items():
        content_type = ContentType.objects.get_for_model(model)
        payroll_processor_permissions.extend(
            Permission.objects.filter(
                content_type=content_type, codename__in=codenames
            )
        )

    # Assign permissions to Payroll Processor group
    payroll_processor_group.permissions.set(payroll_processor_permissions)
    print(
        f"Configured Payroll Processor group with {len(payroll_processor_permissions)} permissions."
    )

    # FINANCE PERMISSIONS
    # Finance is a view-only cross-cutting role (accounting + payroll reporting).
    # It intentionally excludes people-management (payroll.view_employeeprofile)
    # and any add/change/delete permissions (segregation of duties).
    finance_group, _ = Group.objects.get_or_create(name="Finance")
    finance_permissions = []

    # View-only access to accounting records
    finance_permissions.extend(
        Permission.objects.filter(
            content_type=account_ct,
            codename__in=["view_account"],
        )
    )
    finance_permissions.extend(
        Permission.objects.filter(
            content_type=journal_ct,
            codename__in=["view_journal"],
        )
    )
    finance_permissions.extend(
        Permission.objects.filter(
            content_type=journal_entry_ct,
            codename__in=["view_journalentry"],
        )
    )
    finance_permissions.extend(
        Permission.objects.filter(
            content_type=fiscal_year_ct,
            codename__in=["view_fiscalyear"],
        )
    )
    finance_permissions.extend(
        Permission.objects.filter(
            content_type=period_ct,
            codename__in=["view_accountingperiod"],
        )
    )
    finance_permissions.extend(
        Permission.objects.filter(
            content_type=audit_trail_ct,
            codename__in=["view_accountingaudittrail"],
        )
    )

    # View-only perms for the other accounting pages linked in the Finance nav.
    finance_permissions.extend(_view_permissions_for(Budget, TaxReturn, AccountReconciliation))

    # View-only access to payroll records for payroll reporting.
    from payroll.models import PayrollEntry

    finance_permissions.extend(
        _view_permissions_for(Payroll, PayrollRun, PayrollEntry)
    )

    finance_group.permissions.set(finance_permissions)
    print(
        f"Configured Finance group with {len(finance_permissions)} permissions."
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


def assign_user_to_finance_role(user):
    """
    Assign a user to the finance role
    """
    finance_group = Group.objects.get(name="Finance")
    user.groups.add(finance_group)
    print(f"User {user.email} assigned to Finance role.")


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


def is_finance_user(user):
    """
    Check if user has the finance role or is superuser.
    Finance is a view-only, cross-cutting role (accounting + payroll reporting).
    """
    return user.is_superuser or user.groups.filter(name="Finance").exists()


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


def can_approve_journal(first, second):
    """
    Check if user can approve a journal
    - Superusers can approve any journal
    - Auditors can approve any journal
    - Accountants cannot approve journals they created
    """
    user, journal = _split_user_and_object(first, second)

    if journal.status not in [
        Journal.JournalStatus.DRAFT,
        Journal.JournalStatus.PENDING_APPROVAL,
    ]:
        return False

    if user.is_superuser:
        return True

    if is_auditor(user):
        return False

    if is_accountant(user):
        return True

    if is_payroll_processor(user):
        return journal.created_by == user

    return False


def can_reverse_journal(first, second):
    """
    Check if user can reverse a journal
    - Superusers can reverse any journal
    - Only auditors can reverse journals
    - Journal must be posted
    - Journal must not already be reversed
    - Journal's period must not be closed
    """
    user, journal = _split_user_and_object(first, second)

    if user.is_superuser:
        return True

    if journal.status == Journal.JournalStatus.POSTED:
        if journal.reversed_journal:
            return False
        if journal.period and journal.period.is_closed:
            return False
        return is_auditor(user) or is_accountant(user) or journal.created_by == user

    return journal.created_by == user or (
        is_accountant(user) and journal.created_by and is_payroll_processor(journal.created_by)
    )


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
    return user.is_superuser or is_auditor(user) or is_accountant(user)


def can_close_period(first, second):
    """
    Check if user can close an accounting period
    - Superusers can close periods
    - Only auditors can close periods
    """
    user, period = _split_user_and_object(first, second)
    return user.is_superuser or is_accountant(user)


def _role_required(test_func):
    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            if test_func(request.user):
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden()

        return wrapped

    return decorator


auditor_required = _role_required(is_auditor)
accountant_required = _role_required(is_accountant)
payroll_processor_required = _role_required(is_payroll_processor)


def can_view_payroll_data(user):
    """
    Check if user can view payroll data
    - Superusers can view payroll data (full access)
    - Auditors can view payroll data (read-only)
    - Accountants can view payroll data (read-only)
    - Payroll processors have full access to payroll data
    - Finance users can view payroll data (read-only)
    """
    return (
        user.is_superuser
        or is_auditor(user)
        or is_accountant(user)
        or is_payroll_processor(user)
        or is_finance_user(user)
    )


def can_modify_payroll_data(user):
    """
    Check if user can modify payroll data
    - Superusers can modify payroll data
    - Only payroll processors can modify payroll data
    """
    return user.is_superuser or is_payroll_processor(user)
