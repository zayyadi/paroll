from .models import (
    Journal,
    JournalEntry,
    FiscalYear,
    AccountingPeriod,
    TransactionNumber,
    AccountingAuditTrail,
    Account,
)
from .middleware import (
    get_request_user,
    get_request_metadata,
    set_audit_user,
    set_audit_metadata,
)
from .signal_handlers import (
    log_journal_approval,
    log_journal_posting,
    log_journal_reversal,
    log_partial_journal_reversal,
    log_journal_reversal_with_correction,
    log_batch_journal_reversal,
    log_period_closure,
    log_fiscal_year_closure,
)
from .permissions import can_reverse_journal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from datetime import date, timedelta
import json

User = get_user_model()


def get_next_transaction_number(fiscal_year, prefix="TXN"):
    """
    Generate the next transaction number for a given fiscal year.

    Args:
        fiscal_year: The FiscalYear instance
        prefix: Transaction number prefix (default: "TXN")

    Returns:
        Formatted transaction number string
    """
    return TransactionNumber.get_next_number(fiscal_year, prefix)


def get_or_create_fiscal_year(year=None, name=None, start_date=None, end_date=None):
    """
    Get or create a fiscal year for the specified year.

    Args:
        year: Fiscal year (defaults to current year)
        name: Fiscal year name (defaults to "FY {year}")
        start_date: Start date (defaults to Jan 1 of year)
        end_date: End date (defaults to Dec 31 of year)

    Returns:
        FiscalYear instance
    """
    if year is None:
        year = timezone.now().year

    fiscal_year, created = FiscalYear.objects.get_or_create(
        year=year,
        defaults={
            "name": name or f"FY {year}",
            "start_date": start_date or date(year, 1, 1),
            "end_date": end_date or date(year, 12, 31),
            "is_active": True,
        },
    )

    return fiscal_year


def get_or_create_period(
    fiscal_year, period_number=None, name=None, start_date=None, end_date=None
):
    """
    Get or create an accounting period within a fiscal year.

    Args:
        fiscal_year: The FiscalYear instance
        period_number: Period number (defaults to current month)
        name: Period name (defaults to "Month {period_number}")
        start_date: Period start date (defaults to first day of month)
        end_date: Period end date (defaults to last day of month)

    Returns:
        AccountingPeriod instance
    """
    if period_number is None:
        period_number = timezone.now().month

    if start_date is None or end_date is None:
        year = fiscal_year.year
        if start_date is None:
            start_date = date(year, period_number, 1)
        if end_date is None:
            if period_number == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, period_number + 1, 1) - timedelta(days=1)

    period, created = AccountingPeriod.objects.get_or_create(
        fiscal_year=fiscal_year,
        period_number=period_number,
        defaults={
            "name": name or f"Month {period_number}",
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True,
        },
    )

    return period


def validate_journal_entries(entries):
    """
    Validate that debits equal credits in a list of entries.

    Args:
        entries: List of dictionaries with 'entry_type' and 'amount'

    Raises:
        ValidationError: If debits don't equal credits
    """
    debits = sum(
        entry.get("amount", 0)
        for entry in entries
        if entry.get("entry_type") == "DEBIT"
    )
    credits = sum(
        entry.get("amount", 0)
        for entry in entries
        if entry.get("entry_type") == "CREDIT"
    )

    if debits != credits:
        raise ValidationError(
            f"Debits ({debits}) and credits ({credits}) must be equal for a journal."
        )


def validate_period_status(period, status_required=None):
    """
    Validate that an accounting period is in the required status.

    Args:
        period: AccountingPeriod instance
        status_required: Required status (None to just check if closed)

    Raises:
        ValidationError: If period doesn't meet requirements
    """
    if period.is_closed:
        raise ValidationError(f"Cannot post to closed period: {period}")

    if status_required and not period.is_active:
        raise ValidationError(f"Period {period} is not active")


def validate_account_balance(account, amount, entry_type):
    """
    Validate that an account has sufficient balance for the transaction.

    Args:
        account: Account instance
        amount: Transaction amount
        entry_type: 'DEBIT' or 'CREDIT'

    Raises:
        ValidationError: If insufficient balance
    """
    if account.type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE]:
        # For assets and expenses, debits increase balance
        if entry_type == "CREDIT":
            current_balance = account.get_balance()
            if current_balance < amount:
                raise ValidationError(
                    f"Insufficient balance in account {account.name}. "
                    f"Available: {current_balance}, Required: {amount}"
                )


def get_entry_type_for_balance_adjustment(account, direction):
    """
    Determine debit/credit direction for increasing/decreasing an account balance.

    direction: "INCREASE" or "DECREASE"
    """
    if direction not in {"INCREASE", "DECREASE"}:
        raise ValidationError("direction must be INCREASE or DECREASE")

    is_debit_normal = account.type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE]

    if direction == "INCREASE":
        return "DEBIT" if is_debit_normal else "CREDIT"
    return "CREDIT" if is_debit_normal else "DEBIT"


def log_accounting_activity(
    user=None,
    action=None,
    instance=None,
    changes=None,
    reason=None,
    ip_address=None,
    user_agent=None,
    approval_level=None,
):
    """
    Log an accounting activity to the audit trail with enhanced context capture.

    Args:
        user: User performing the action (will be auto-detected if not provided)
        action: Action type from AccountingAuditTrail.ActionType
        instance: The model instance being acted upon
        changes: Dictionary of changes made
        reason: Reason for the action
        ip_address: User's IP address (will be auto-detected if not provided)
        user_agent: User's browser agent (will be auto-detected if not provided)
        approval_level: Approval workflow level

    Returns:
        AccountingAuditTrail instance
    """
    # Auto-detect user and metadata if not provided
    if user is None:
        user = get_request_user()
    if ip_address is None or user_agent is None:
        auto_ip, auto_user_agent = get_request_metadata()
        if ip_address is None:
            ip_address = auto_ip
        if user_agent is None:
            user_agent = auto_user_agent

    return AccountingAuditTrail.log_action(
        user=user,
        action=action,
        instance=instance,
        changes=changes,
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
        approval_level=approval_level,
    )


def create_journal_with_entries(
    date,
    description,
    entries,
    user=None,
    fiscal_year=None,
    period=None,
    auto_post=False,
    source_object=None,
    ip_address=None,
    user_agent=None,
    validate_balances=True,
):
    """
    Create a journal with multiple entries, including validation and audit logging.

    Args:
        date: Journal date
        description: Journal description
        entries: List of dictionaries with 'account', 'entry_type', 'amount', 'memo'
        user: User creating the journal
        fiscal_year: FiscalYear instance (will be determined if not provided)
        period: AccountingPeriod instance (will be determined if not provided)
        auto_post: Whether to automatically post the journal
        source_object: Source object for generic foreign key
        ip_address: User's IP address
        user_agent: User's browser agent
        validate_balances: Whether to enforce account balance validation checks

    Returns:
        Created Journal instance
    """
    with transaction.atomic():
        # Validate entries
        validate_journal_entries(entries)

        # Determine fiscal year if not provided
        if not fiscal_year:
            fiscal_year = get_or_create_fiscal_year(date.year)

        # Determine period if not provided
        if not period:
            period = get_or_create_period(fiscal_year, date.month)

        # Validate period status
        validate_period_status(period)

        # Generate transaction number
        transaction_number = get_next_transaction_number(fiscal_year)

        # Create journal
        journal = Journal.objects.create(
            transaction_number=transaction_number,
            description=description,
            date=date,
            period=period,
            created_by=user,
            status=Journal.JournalStatus.DRAFT,
        )

        # Set source object if provided
        if source_object:
            journal.content_type = ContentType.objects.get_for_model(source_object)
            journal.object_id = source_object.pk
            journal.save()

        # Create entries
        for entry_data in entries:
            account = entry_data["account"]
            entry_type = entry_data["entry_type"]
            amount = entry_data["amount"]
            memo = entry_data.get("memo", "")

            # Validate account balance (optional for system-driven postings)
            if validate_balances:
                validate_account_balance(account, amount, entry_type)

            JournalEntry.objects.create(
                journal=journal,
                account=account,
                entry_type=entry_type,
                amount=amount,
                memo=memo,
                created_by=user,
            )

        # Log creation
        log_accounting_activity(
            user=user,
            action=AccountingAuditTrail.ActionType.CREATE,
            instance=journal,
            changes={"entries": entries},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Auto-post if requested
        if auto_post:
            if user:
                journal.submit_for_approval()
                journal.approve(user)
                journal.post(user)

                # Use enhanced logging functions for posting
                log_journal_posting(
                    journal, user, f"Auto-posted journal: {journal.transaction_number}"
                )
            else:
                # System-generated auto posting path
                journal.status = Journal.JournalStatus.POSTED
                journal.approved_at = timezone.now()
                journal.posted_at = timezone.now()
                journal.save(update_fields=["status", "approved_at", "posted_at"])

        return journal


def reverse_journal(journal, user, reason, ip_address=None, user_agent=None):
    """
    Create a reversal journal for an existing posted journal.

    Args:
        journal: The Journal instance to reverse
        user: User creating the reversal
        reason: Reason for reversal
        ip_address: User's IP address
        user_agent: User's browser agent

    Returns:
        Created reversal Journal instance
    """
    with transaction.atomic():
        # Validate journal status
        if journal.status != Journal.JournalStatus.POSTED:
            raise ValidationError("Only posted journals can be reversed")

        if journal.reversed_journal:
            raise ValidationError("Journal has already been reversed")

        # Validate period is not closed
        if journal.period.is_closed:
            raise ValidationError(
                f"Cannot reverse journal from closed period: {journal.period}"
            )

        # Validate user permissions
        if not can_reverse_journal(user, journal):
            raise ValidationError("You don't have permission to reverse this journal")

        # Create reversal journal using the model method
        reversal_journal = journal.reverse(user, reason)

        # Use enhanced logging function for reversal
        log_journal_reversal(journal, reversal_journal, user, reason)

        return reversal_journal


def reverse_journal_partial(
    journal,
    user,
    reason,
    entry_ids=None,
    amounts=None,
    ip_address=None,
    user_agent=None,
):
    """
    Create a partial reversal journal for specific entries of an existing posted journal.

    Args:
        journal: The Journal instance to partially reverse
        user: User creating the reversal
        reason: Reason for partial reversal
        entry_ids: List of entry IDs to reverse (optional)
        amounts: Dictionary of entry_id -> amount to reverse (optional)
        ip_address: User's IP address
        user_agent: User's browser agent

    Returns:
        Created partial reversal Journal instance
    """
    with transaction.atomic():
        # Validate journal status
        if journal.status != Journal.JournalStatus.POSTED:
            raise ValidationError("Only posted journals can be partially reversed")

        # Validate period is not closed
        if journal.period.is_closed:
            raise ValidationError(
                f"Cannot partially reverse journal from closed period: {journal.period}"
            )

        # Validate user permissions
        if not can_reverse_journal(user, journal):
            raise ValidationError(
                "You don't have permission to partially reverse this journal"
            )

        # Get entries to reverse
        entries_to_reverse = []
        if entry_ids:
            entries_to_reverse = journal.entries.filter(id__in=entry_ids)
        elif amounts:
            entries_to_reverse = journal.entries.filter(id__in=amounts.keys())
        else:
            raise ValidationError(
                "Must provide either entry_ids or amounts for partial reversal"
            )

        if not entries_to_reverse:
            raise ValidationError("No valid entries found for partial reversal")

        # Create partial reversal journal
        reversal_journal = Journal.objects.create(
            description=f"PARTIAL REVERSAL: {journal.description}",
            date=timezone.now().date(),
            period=journal.period,
            status=Journal.JournalStatus.DRAFT,
            created_by=user,
            reversal_reason=reason,
        )

        # Create reversal entries
        for entry in entries_to_reverse:
            reversal_amount = (
                amounts.get(entry.id, entry.amount) if amounts else entry.amount
            )

            # Validate reversal amount
            if reversal_amount <= 0 or reversal_amount > entry.amount:
                raise ValidationError(f"Invalid reversal amount for entry {entry.id}")

            reversal_entry_type = "CREDIT" if entry.entry_type == "DEBIT" else "DEBIT"
            JournalEntry.objects.create(
                journal=reversal_journal,
                account=entry.account,
                entry_type=reversal_entry_type,
                amount=reversal_amount,
                memo=f"Partial reversal of entry {entry.id}: {entry.memo or ''}",
            )

        # Auto-approve and post reversal
        reversal_journal.approve(user)
        reversal_journal.post(user)

        # Log the partial reversal
        entry_ids = [entry.id for entry in entries_to_reverse]
        log_partial_journal_reversal(
            journal, reversal_journal, user, reason, entry_ids, amounts
        )

        return reversal_journal


def reverse_journal_with_correction(
    journal, user, reason, correction_entries, ip_address=None, user_agent=None
):
    """
    Create a reversal journal with correction entries.

    Args:
        journal: The Journal instance to reverse
        user: User creating the reversal
        reason: Reason for reversal with correction
        correction_entries: List of dictionaries with 'account', 'entry_type', 'amount', 'memo'
        ip_address: User's IP address
        user_agent: User's browser agent

    Returns:
        Tuple of (reversal_journal, correction_journal)
    """
    with transaction.atomic():
        # Validate journal status
        if journal.status != Journal.JournalStatus.POSTED:
            raise ValidationError(
                "Only posted journals can be reversed with correction"
            )

        # Validate period is not closed
        if journal.period.is_closed:
            raise ValidationError(
                f"Cannot reverse journal from closed period: {journal.period}"
            )

        # Validate user permissions
        if not can_reverse_journal(user, journal):
            raise ValidationError("You don't have permission to reverse this journal")

        # Validate correction entries
        validate_journal_entries(correction_entries)

        # Create reversal journal
        reversal_journal = reverse_journal(
            journal, user, reason, ip_address, user_agent
        )

        # Create correction journal
        correction_journal = create_journal_with_entries(
            date=timezone.now().date(),
            description=f"CORRECTION: {journal.description}",
            entries=correction_entries,
            user=user,
            period=journal.period,
            auto_post=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Link the correction journal to the original
        correction_journal.content_type = ContentType.objects.get_for_model(Journal)
        correction_journal.object_id = journal.pk
        correction_journal.save()

        # Log the correction
        log_journal_reversal_with_correction(
            journal, reversal_journal, correction_journal, user, reason
        )

        return reversal_journal, correction_journal


def batch_reverse_journals(journals, user, reason, ip_address=None, user_agent=None):
    """
    Reverse multiple journals in a batch operation.

    Args:
        journals: List of Journal instances to reverse
        user: User creating the reversals
        reason: Reason for batch reversal
        ip_address: User's IP address
        user_agent: User's browser agent

    Returns:
        List of created reversal Journal instances
    """
    with transaction.atomic():
        reversal_journals = []
        failed_journals = []

        for journal in journals:
            try:
                # Create reversal for each journal
                reversal_journal = reverse_journal(
                    journal, user, reason, ip_address, user_agent
                )
                reversal_journals.append(reversal_journal)
            except Exception as e:
                failed_journals.append({"journal": journal, "error": str(e)})

        # Log the batch operation
        log_batch_journal_reversal(
            journals, reversal_journals, user, reason, failed_journals
        )

        if failed_journals:
            error_msg = "Some journals could not be reversed:\n"
            for failed in failed_journals:
                error_msg += (
                    f"- {failed['journal'].transaction_number}: {failed['error']}\n"
                )
            raise ValidationError(error_msg)

        return reversal_journals


def post_journal(journal, user, ip_address=None, user_agent=None):
    """
    Post a journal with validation and audit logging.

    Args:
        journal: Journal instance to post
        user: User posting the journal
        ip_address: User's IP address
        user_agent: User's browser agent

    Returns:
        Updated Journal instance
    """
    with transaction.atomic():
        # Validate journal
        if journal.status not in [
            Journal.JournalStatus.DRAFT,
            Journal.JournalStatus.APPROVED,
        ]:
            raise ValidationError(
                f"Cannot post journal with status: {journal.get_status_display()}"
            )

        # Validate period status
        validate_period_status(journal.period)

        # Validate entries balance
        journal.validate_entries()

        # If not approved, approve first
        if journal.status == Journal.JournalStatus.DRAFT:
            journal.submit_for_approval()
            journal.approve(user)

            # Use enhanced logging function for approval
            log_journal_approval(
                journal, user, f"Approved journal: {journal.transaction_number}"
            )

        # Post the journal
        journal.post(user)

        # Use enhanced logging function for posting
        log_journal_posting(
            journal, user, f"Posted journal: {journal.transaction_number}"
        )

        return journal


def create_journal_entry(
    date,
    description,
    entries,
    user=None,
    fiscal_year=None,
    period=None,
    auto_post=False,
    source_object=None,
    ip_address=None,
    user_agent=None,
):
    """
    Enhanced version of the original create_journal_entry function.
    Creates a journal and its corresponding entries with full validation and audit logging.

    Args:
        date: Date of the transaction
        description: Description for the journal
        entries: A list of dictionaries, each with 'account', 'entry_type', and 'amount'
        user: User creating the journal
        fiscal_year: FiscalYear instance (will be determined if not provided)
        period: AccountingPeriod instance (will be determined if not provided)
        auto_post: Whether to automatically post the journal
        source_object: Source object for generic foreign key
        ip_address: User's IP address
        user_agent: User's browser agent

    Returns:
        Created Journal instance
    """
    return create_journal_with_entries(
        date=date,
        description=description,
        entries=entries,
        user=user,
        fiscal_year=fiscal_year,
        period=period,
        auto_post=auto_post,
        source_object=source_object,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def close_accounting_period(
    period, user, reason=None, ip_address=None, user_agent=None
):
    """
    Close an accounting period with audit logging.

    Args:
        period: AccountingPeriod instance to close
        user: User closing the period
        reason: Reason for closing
        ip_address: User's IP address
        user_agent: User's browser agent

    Returns:
        Updated AccountingPeriod instance
    """
    with transaction.atomic():
        # Close the period
        period.close(user)

        # Use enhanced logging function for period closure
        log_period_closure(
            period, user, reason or f"Closed accounting period: {period.name}"
        )

        return period


def close_fiscal_year(fiscal_year, user, reason=None, ip_address=None, user_agent=None):
    """
    Close a fiscal year with audit logging.

    Args:
        fiscal_year: FiscalYear instance to close
        user: User closing the fiscal year
        reason: Reason for closing
        ip_address: User's IP address
        user_agent: User's browser agent

    Returns:
        Updated FiscalYear instance
    """
    with transaction.atomic():
        # Close the fiscal year
        fiscal_year.close(user)

        # Use enhanced logging function for fiscal year closure
        log_fiscal_year_closure(
            fiscal_year, user, reason or f"Closed fiscal year: {fiscal_year.name}"
        )

        return fiscal_year


def get_account_balance_as_of(account, as_of_date):
    """
    Get an account's balance as of a specific date.

    Args:
        account: Account instance
        as_of_date: Date to get balance as of

    Returns:
        Account balance as of the specified date
    """
    debits = (
        account.entries.filter(
            entry_type="DEBIT",
            journal__date__lte=as_of_date,
            journal__status=Journal.JournalStatus.POSTED,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    credits = (
        account.entries.filter(
            entry_type="CREDIT",
            journal__date__lte=as_of_date,
            journal__status=Journal.JournalStatus.POSTED,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    if account.type in [account.AccountType.ASSET, account.AccountType.EXPENSE]:
        return debits - credits
    else:  # Liability, Equity, Revenue
        return credits - debits


def get_trial_balance(period=None, as_of_date=None):
    """
    Generate a trial balance for a period or as of a specific date.

    Args:
        period: AccountingPeriod instance (optional)
        as_of_date: Date to generate trial balance as of (optional)

    Returns:
        Dictionary with account balances
    """
    if not as_of_date and period:
        as_of_date = period.end_date
    elif not as_of_date:
        as_of_date = timezone.now().date()

    trial_balance = {}

    for account in Account.objects.all():
        balance = get_account_balance_as_of(account, as_of_date)
        if balance != 0:
            trial_balance[account.id] = {
                "account": account,
                "balance": balance,
                "debit_balance": (
                    balance
                    if account.type
                    in [account.AccountType.ASSET, account.AccountType.EXPENSE]
                    else 0
                ),
                "credit_balance": (
                    balance
                    if account.type
                    not in [account.AccountType.ASSET, account.AccountType.EXPENSE]
                    else 0
                ),
            }

    return trial_balance
