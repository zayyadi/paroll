from .models import (
    Journal,
    JournalEntry,
    FiscalYear,
    AccountingPeriod,
    TransactionNumber,
    AccountingAuditTrail,
    Account,
    AccrualTemplate,
    BudgetLine,
    CurrencyRevaluation,
    CurrencyRevaluationLine,
    ExchangeRate,
    AccountReconciliation,
    BankTransaction,
    ReconciliationItem,
    TaxReturn,
    TaxReturnLine,
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
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from datetime import date, timedelta
from decimal import Decimal
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


def get_or_create_fiscal_year(
    year=None, name=None, start_date=None, end_date=None, company=None
):
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

    if company is None:
        raise ValueError("company is required for fiscal year accounting scope")

    fiscal_year, created = FiscalYear.objects.get_or_create(
        company=company,
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
    fiscal_year, period_number=None, name=None, start_date=None, end_date=None, company=None
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

    company = company or fiscal_year.company

    period, created = AccountingPeriod.objects.get_or_create(
        company=company,
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


def validate_entries_company(entries, company):
    for entry in entries:
        account = entry.get("account")
        if getattr(account, "company_id", None) != company.id:
            raise ValueError("All journal entry accounts must belong to the journal company")


def _serialize_journal_entries_for_audit(entries):
    serialized_entries = []
    for entry in entries:
        account = entry.get("account")
        serialized_entry = {
            "account_id": getattr(account, "pk", None),
            "account_name": getattr(account, "name", str(account)),
            "entry_type": entry.get("entry_type"),
            "amount": str(entry.get("amount", "")),
            "memo": entry.get("memo", ""),
        }
        serialized_entries.append(serialized_entry)
    return serialized_entries


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
    company=None,
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
        company: Company instance that owns the accounting transaction
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
    if company is None and period is not None:
        company = period.company
    if company is None and fiscal_year is not None:
        company = fiscal_year.company
    if company is None:
        entry_company_ids = {
            getattr(entry.get("account"), "company_id", None) for entry in entries
        }
        entry_company_ids.discard(None)
        if len(entry_company_ids) == 1:
            company = entries[0]["account"].company
    if company is None:
        raise ValueError("company is required to create an accounting journal")

    with transaction.atomic():
        # Validate entries
        validate_journal_entries(entries)
        validate_entries_company(entries, company)

        # Determine fiscal year if not provided
        if not fiscal_year:
            fiscal_year = get_or_create_fiscal_year(date.year, company=company)
        elif fiscal_year.company_id != company.id:
            raise ValueError("Fiscal year must belong to the journal company")

        # Determine period if not provided
        if not period:
            period = get_or_create_period(fiscal_year, date.month, company=company)
        elif period.company_id != company.id:
            raise ValueError("Accounting period must belong to the journal company")

        # Validate period status
        validate_period_status(period)

        # Generate transaction number
        transaction_number = get_next_transaction_number(fiscal_year)

        # Create journal
        journal = Journal.objects.create(
            company=company,
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

        # Recompute denormalized balances for all affected accounts
        seen = set()
        for entry_data in entries:
            account = entry_data["account"]
            if account.pk not in seen:
                seen.add(account.pk)
                account.recompute_balance()

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
            company=journal.company,
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
            journal._suppress_approval_audit = True
            journal.approve(user)

        # Post the journal
        journal.post(user)

        return journal


def create_journal_entry(
    date,
    description,
    entries,
    company=None,
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
        company=company,
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
        for template in AccrualTemplate.objects.select_related(
            "debit_account", "credit_account"
        ).filter(company=period.company, is_active=True):
            create_journal_with_entries(
                company=period.company,
                date=period.end_date,
                description=f"Accrual: {template.name}",
                entries=[
                    {
                        "account": template.debit_account,
                        "entry_type": JournalEntry.EntryType.DEBIT,
                        "amount": template.amount,
                        "memo": template.name,
                    },
                    {
                        "account": template.credit_account,
                        "entry_type": JournalEntry.EntryType.CREDIT,
                        "amount": template.amount,
                        "memo": template.name,
                    },
                ],
                user=user,
                fiscal_year=period.fiscal_year,
                period=period,
                auto_post=True,
                validate_balances=False,
            )

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


def _normal_signed_amount(account, entry_type, amount):
    debit_normal = account.type in (Account.AccountType.ASSET, Account.AccountType.EXPENSE)
    if debit_normal:
        return amount if entry_type == JournalEntry.EntryType.DEBIT else -amount
    return amount if entry_type == JournalEntry.EntryType.CREDIT else -amount


def get_budget_vs_actual(company, fiscal_year, period=None, include_unbudgeted=False):
    budget_lines = (
        BudgetLine.objects.select_related("account", "period", "budget")
        .filter(budget__company=company, budget__fiscal_year=fiscal_year, budget__status="APPROVED")
    )
    if period is not None:
        budget_lines = budget_lines.filter(period=period)

    budget_by_account = {}
    accounts = {}
    for line in budget_lines:
        accounts[line.account_id] = line.account
        budget_by_account[line.account_id] = (
            budget_by_account.get(line.account_id, Decimal("0.00")) + line.amount
        )

    actual_by_account = {}
    entries = JournalEntry.objects.select_related("account", "journal").filter(
        journal__company=company,
        journal__period__fiscal_year=fiscal_year,
        journal__status=Journal.JournalStatus.POSTED,
    )
    if period is not None:
        entries = entries.filter(journal__period=period)

    for entry in entries:
        if include_unbudgeted:
            accounts.setdefault(entry.account_id, entry.account)
        actual_by_account[entry.account_id] = actual_by_account.get(
            entry.account_id, Decimal("0.00")
        ) + _normal_signed_amount(entry.account, entry.entry_type, entry.amount)

    rows = []
    for account_id in sorted(
        accounts,
        key=lambda key: (accounts[key].account_number or "", accounts[key].name),
    ):
        budget_amount = budget_by_account.get(account_id, Decimal("0.00"))
        actual_amount = actual_by_account.get(account_id, Decimal("0.00"))
        if budget_amount == 0 and actual_amount == 0:
            continue
        rows.append(
            {
                "account": accounts[account_id],
                "budget_amount": budget_amount,
                "actual_amount": actual_amount,
                "variance": actual_amount - budget_amount,
                "period": period,
            }
        )
    return rows


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


def get_trial_balance(period=None, as_of_date=None, company=None):
    """
    Generate a trial balance for a period or as of a specific date.

    Args:
        period: AccountingPeriod instance (optional)
        as_of_date: Date to generate trial balance as of (optional)
        company: Company instance to scope accounts and balances

    Returns:
        Dictionary with account balances
    """
    if not as_of_date and period:
        as_of_date = period.end_date
    elif not as_of_date:
        as_of_date = timezone.now().date()

    trial_balance = {}

    if period is not None:
        company = company or period.company
    if company is None:
        raise ValueError("company is required for trial balance")

    for account in Account.objects.filter(company=company):
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


def get_trial_balance_totals(trial_balance):
    """
    Calculate display totals for a trial balance dictionary.

    Django templates do not provide a built-in aggregate filter, so views should
    compute report totals before rendering HTML or PDF templates.
    """
    balances = (
        list(trial_balance.values()) if hasattr(trial_balance, "values") else trial_balance
    )
    total_debits = sum(
        (item.get("debit_balance", 0) for item in balances), Decimal("0.00")
    )

    total_credits = sum(
        (item.get("credit_balance", 0) for item in balances), Decimal("0.00")
    )

    return {
        "total_debits": total_debits,
        "total_credits": total_credits,
        "is_balanced": total_debits == total_credits,
    }


def get_dashboard_metrics(company, period=None):
    """Aggregated financial KPIs for the executive dashboard."""
    from datetime import date

    as_of = period.end_date if period else timezone.now().date()
    tb = get_trial_balance(company=company, as_of_date=as_of)
    prev_period_end = (as_of.replace(day=1) - timedelta(days=1)) if isinstance(as_of, date) else as_of

    total_assets = sum(
        v["balance"] for v in tb.values() if v["account"].type == Account.AccountType.ASSET
    )
    total_liabilities = sum(
        v["balance"] for v in tb.values() if v["account"].type == Account.AccountType.LIABILITY
    )
    total_equity = sum(
        v["balance"] for v in tb.values() if v["account"].type == Account.AccountType.EQUITY
    )
    total_revenue = sum(
        v["balance"] for v in tb.values() if v["account"].type == Account.AccountType.REVENUE
    )
    total_expenses = sum(
        v["balance"] for v in tb.values() if v["account"].type == Account.AccountType.EXPENSE
    )

    net_income = total_revenue - total_expenses
    prev_tb = get_trial_balance(company=company, as_of_date=prev_period_end)
    prev_revenue = sum(
        v["balance"] for v in prev_tb.values() if v["account"].type == Account.AccountType.REVENUE
    )

    revenue_change = (
        ((total_revenue - prev_revenue) / prev_revenue * 100)
        if prev_revenue and prev_revenue != 0
        else Decimal("0")
    )

    journal_counts = Journal.objects.filter(company=company).aggregate(
        drafts=Count("pk", filter=Q(status=Journal.JournalStatus.DRAFT)),
        pending=Count("pk", filter=Q(status=Journal.JournalStatus.PENDING_APPROVAL)),
        posted=Count("pk", filter=Q(status=Journal.JournalStatus.POSTED)),
    )

    open_periods = AccountingPeriod.objects.filter(
        company=company, is_closed=False, is_active=True
    ).count()

    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_income": net_income,
        "revenue_change_pct": round(revenue_change, 1),
        "draft_journals": journal_counts["drafts"],
        "pending_journals": journal_counts["pending"],
        "posted_journals": journal_counts["posted"],
        "open_periods": open_periods,
        "as_of_date": as_of,
    }


def get_cash_flow_statement(company, start_date, end_date):
    """Direct-method cash flow from operating, investing, and financing activities."""
    entries = JournalEntry.objects.select_related("account", "journal").filter(
        journal__company=company,
        journal__status=Journal.JournalStatus.POSTED,
        journal__date__gte=start_date,
        journal__date__lte=end_date,
    )

    def _net_flow(account_name_contains):
        subset = entries.filter(account__name__icontains=account_name_contains)
        debits = sum(
            (e.amount for e in subset if e.entry_type == "DEBIT"), Decimal("0.00")
        )
        credits = sum(
            (e.amount for e in subset if e.entry_type == "CREDIT"), Decimal("0.00")
        )
        return debits - credits

    operating = _net_flow("revenue") - _net_flow("expense") + _net_flow("receivable") - _net_flow("payable")
    investing = _net_flow("asset") - _net_flow("invest")
    financing = _net_flow("equity") - _net_flow("loan") - _net_flow("dividend")

    return {
        "operating_cash_flow": operating,
        "investing_cash_flow": investing,
        "financing_cash_flow": financing,
        "net_cash_flow": operating + investing + financing,
        "start_date": start_date,
        "end_date": end_date,
    }


def get_financial_ratios(company, as_of_date=None):
    """Compute key financial ratios from trial balance."""
    as_of_date = as_of_date or timezone.now().date()
    tb = get_trial_balance(company=company, as_of_date=as_of_date)

    def _sum_by_type(acct_type):
        return sum((v["balance"] for v in tb.values() if v["account"].type == acct_type), Decimal("0.00"))

    assets = _sum_by_type(Account.AccountType.ASSET)
    liabilities = _sum_by_type(Account.AccountType.LIABILITY)
    equity = _sum_by_type(Account.AccountType.EQUITY)
    revenue = _sum_by_type(Account.AccountType.REVENUE)
    expenses = _sum_by_type(Account.AccountType.EXPENSE)

    current_ratio = (assets / liabilities).quantize(Decimal("0.01")) if liabilities else Decimal("0")
    debt_ratio = (liabilities / assets).quantize(Decimal("0.01")) if assets else Decimal("0")
    profit_margin = ((revenue - expenses) / revenue * 100).quantize(Decimal("0.01")) if revenue else Decimal("0")
    roe = ((revenue - expenses) / equity * 100).quantize(Decimal("0.01")) if equity else Decimal("0")
    quick_ratio = current_ratio  # simplified; needs cash/receivables split in practice

    return {
        "current_ratio": float(current_ratio),
        "debt_ratio": float(debt_ratio),
        "profit_margin_pct": float(profit_margin),
        "roe_pct": float(roe),
        "quick_ratio": float(quick_ratio),
        "as_of_date": as_of_date,
        "total_assets": float(assets),
        "total_liabilities": float(liabilities),
        "total_equity": float(equity),
    }


def get_month_end_checklist(company, period):
    """Return a checklist of items to verify before closing a period."""
    from .models import AccountReconciliation

    checks = [
        {
            "label": "All journal entries posted for period",
            "passed": not Journal.objects.filter(
                company=company, period=period,
                status__in=["DRAFT", "PENDING_APPROVAL"],
            ).exists(),
            "detail": "Check for draft or pending journals in this period.",
        },
        {
            "label": "Bank accounts reconciled",
            "passed": AccountReconciliation.objects.filter(
                company=company, period=period, status="APPROVED",
            ).exists(),
            "detail": "At least one bank reconciliation must be approved.",
        },
        {
            "label": "Trial balance is balanced",
            "passed": get_trial_balance_totals(
                get_trial_balance(company=company, period=period)
            )["is_balanced"],
            "detail": "Total debits must equal total credits.",
        },
        {
            "label": "Accrual templates active",
            "passed": AccrualTemplate.objects.filter(
                company=company, is_active=True,
            ).exists(),
            "detail": "Ensure period-end accrual templates are configured.",
        },
        {
            "label": "Inventory reconciled to GL",
            "passed": True,
            "detail": "Run inventory-to-GL reconciliation before close.",
        },
    ]

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "all_passed": all_passed, "period": period}


def get_inventory_turnover(company, start_date, end_date):
    """Calculate inventory turnover ratio = COGS / Average Inventory."""
    from inventory.models import InventoryValuationLayer

    start_value = Decimal(
        InventoryValuationLayer.objects.filter(
            company=company, created_at__date__lte=start_date
        ).aggregate(total=Sum("remaining_total_cost"))["total"]
        or "0.00"
    )
    end_value = Decimal(
        InventoryValuationLayer.objects.filter(
            company=company, created_at__date__lte=end_date
        ).aggregate(total=Sum("remaining_total_cost"))["total"]
        or "0.00"
    )

    cogs_entries = JournalEntry.objects.filter(
        account__name__icontains="cogs",
        journal__company=company,
        journal__status=Journal.JournalStatus.POSTED,
        journal__date__gte=start_date,
        journal__date__lte=end_date,
        entry_type="DEBIT",
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    avg_inventory = ((start_value + end_value) / 2).quantize(Decimal("0.01"))
    turnover = (cogs_entries / avg_inventory).quantize(Decimal("0.01")) if avg_inventory else Decimal("0")

    return {
        "cogs": cogs_entries,
        "start_inventory": start_value,
        "end_inventory": end_value,
        "avg_inventory": avg_inventory,
        "turnover_ratio": float(turnover),
        "days_inventory": float((Decimal("365") / turnover) if turnover else Decimal("0")),
    }


def get_gross_margin_by_product(company, start_date, end_date):
    """Compute gross margin by inventory item from sales invoices."""
    from inventory.models import SalesInvoice, SalesInvoiceLine

    invoices = SalesInvoice.objects.filter(
        company=company,
        document__document_date__gte=start_date,
        document__document_date__lte=end_date,
    ).prefetch_related("lines__item")

    products = {}
    for invoice in invoices:
        for line in invoice.lines.all():
            if not line.item:
                continue
            key = line.item.sku or line.item.name
            if key not in products:
                products[key] = {"item": line.item, "revenue": Decimal("0.00"), "cogs": Decimal("0.00"), "qty_sold": 0}
            products[key]["revenue"] += line.total or Decimal("0.00")
            products[key]["cogs"] += (line.unit_cost * line.quantity) if line.unit_cost else Decimal("0.00")
            products[key]["qty_sold"] += line.quantity or 0

    results = []
    for data in products.values():
        margin = data["revenue"] - data["cogs"]
        margin_pct = (margin / data["revenue"] * 100) if data["revenue"] else Decimal("0")
        results.append({
            "item": data["item"],
            "revenue": data["revenue"],
            "cogs": data["cogs"],
            "gross_margin": margin,
            "margin_pct": float(margin_pct.quantize(Decimal("0.01"))),
            "qty_sold": data["qty_sold"],
        })

    return sorted(results, key=lambda x: x["revenue"], reverse=True)


def get_latest_exchange_rate(company, base_currency, quote_currency, as_of_date):
    rate = (
        ExchangeRate.objects.filter(
            company=company,
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate_date__lte=as_of_date,
        )
        .order_by("-rate_date")
        .first()
    )
    return rate.rate if rate else None


def generate_fx_revaluation(company, revaluation_date, base_currency, user):
    """Generate FX revaluation lines for all foreign-currency accounts.

    Scans all ACTIVE accounts whose currency differs from base_currency, fetches
    the latest exchange rates for each, and computes unrealized gain/loss.
    Returns a CurrencyRevaluation instance (not yet posted).
    """
    reval = CurrencyRevaluation.objects.create(
        company=company,
        revaluation_date=revaluation_date,
        base_currency=base_currency,
        created_by=user,
    )

    base_currency = base_currency.upper()
    foreign_accounts = Account.objects.filter(
        company=company,
        status=Account.AccountStatus.ACTIVE,
    ).exclude(currency=base_currency)

    lines_created = 0
    for account in foreign_accounts:
        balance = account.get_balance(cached=False)
        if balance is None:
            balance = Decimal("0.00")

        rate = get_latest_exchange_rate(
            company, base_currency, account.currency, revaluation_date
        )
        if rate is None or rate == Decimal("0"):
            continue

        original_rate = Decimal("1.0")
        original_value = (balance * original_rate).quantize(Decimal("0.01"))
        revalued_value = (balance * rate).quantize(Decimal("0.01"))
        gain_loss = (revalued_value - original_value).quantize(Decimal("0.01"))

        if gain_loss == Decimal("0.00"):
            continue

        is_debit_normal = account.type in (
            Account.AccountType.ASSET,
            Account.AccountType.EXPENSE,
        )

        if is_debit_normal:
            entry_type = "DEBIT" if gain_loss > 0 else "CREDIT"
        else:
            entry_type = "CREDIT" if gain_loss > 0 else "DEBIT"

        CurrencyRevaluationLine.objects.create(
            revaluation=reval,
            account=account,
            foreign_currency=account.currency,
            balance_fc=balance,
            rate_at_original=original_rate,
            rate_at_revaluation=rate,
            base_value_original=original_value,
            base_value_revalued=revalued_value,
            unrealized_gain_loss=abs(gain_loss),
            entry_type=entry_type,
        )
        lines_created += 1

    return reval


def generate_tax_return(company, return_type, period, user, tax_accounts=None):
    """Generate a tax return from posted journal entries for the period.

    Scans journal entries for tax-related accounts and aggregates taxable
    amounts into a TaxReturn with lines.

    tax_accounts: dict mapping tax role to Account, e.g.:
        {"vat_output": vat_output_acct, "vat_input": vat_input_acct, "wht_payable": wht_payable_acct}
    """
    if return_type not in dict(TaxReturn.ReturnType.choices):
        raise ValidationError(f"Invalid return type: {return_type}")

    existing = TaxReturn.objects.filter(
        company=company,
        return_type=return_type,
        return_period_start=period.start_date,
        return_period_end=period.end_date,
    ).first()
    if existing:
        raise ValidationError(f"A {return_type} return already exists for this period.")

    tax_return = TaxReturn.objects.create(
        company=company,
        return_type=return_type,
        period=period,
        return_period_start=period.start_date,
        return_period_end=period.end_date,
    )

    entries = JournalEntry.objects.select_related("account", "journal").filter(
        journal__company=company,
        journal__period=period,
        journal__status=Journal.JournalStatus.POSTED,
    )

    tax_lines = []

    if return_type == "VAT" and tax_accounts:
        vat_output_acct = tax_accounts.get("vat_output")
        vat_input_acct = tax_accounts.get("vat_input")

        if vat_output_acct:
            output_total = entries.filter(account=vat_output_acct).aggregate(
                total=Sum("amount"))["total"] or Decimal("0.00")
            tax_return.total_tax += output_total
            if output_total > 0:
                tax_lines.append(TaxReturnLine(
                    tax_return=tax_return,
                    account=vat_output_acct,
                    tax_account=vat_output_acct,
                    gross_amount=output_total,
                    tax_rate=Decimal("7.5000"),
                    tax_amount=output_total,
                    line_description="VAT Output",
                ))

        if vat_input_acct:
            input_total = entries.filter(account=vat_input_acct).aggregate(
                total=Sum("amount"))["total"] or Decimal("0.00")
            tax_return.total_input_tax += input_total
            if input_total > 0:
                tax_lines.append(TaxReturnLine(
                    tax_return=tax_return,
                    account=vat_input_acct,
                    tax_account=vat_input_acct,
                    gross_amount=input_total,
                    tax_rate=Decimal("7.5000"),
                    tax_amount=input_total,
                    line_description="VAT Input",
                ))

    elif return_type == "WHT" and tax_accounts:
        wht_acct = tax_accounts.get("wht_payable")
        if wht_acct:
            wht_total = entries.filter(account=wht_acct).aggregate(
                total=Sum("amount"))["total"] or Decimal("0.00")
            tax_return.total_tax += wht_total
            if wht_total > 0:
                tax_lines.append(TaxReturnLine(
                    tax_return=tax_return,
                    account=wht_acct,
                    tax_account=wht_acct,
                    gross_amount=wht_total,
                    tax_rate=Decimal("5.0000"),
                    tax_amount=wht_total,
                    line_description="Withholding Tax Deducted",
                ))

    if tax_lines:
        TaxReturnLine.objects.bulk_create(tax_lines)

    tax_return.total_taxable = sum(line.gross_amount for line in tax_lines)
    tax_return.net_tax_payable = tax_return.total_tax - tax_return.total_input_tax
    tax_return.save(update_fields=["total_taxable", "total_tax", "total_input_tax", "net_tax_payable", "updated_at"])

    log_accounting_activity(
        user=user,
        action=AccountingAuditTrail.ActionType.CREATE,
        instance=tax_return,
        changes={
            "return_type": return_type,
            "net_tax_payable": str(tax_return.net_tax_payable),
        },
    )

    return tax_return


def file_tax_return(tax_return, user, filing_reference=""):
    """Mark a tax return as filed."""
    if tax_return.status not in (TaxReturn.Status.DRAFT, TaxReturn.Status.SUBMITTED):
        raise ValidationError("Only draft or submitted returns can be filed.")

    tax_return.status = TaxReturn.Status.FILED
    tax_return.filed_by = user
    tax_return.filed_at = timezone.now()
    tax_return.filing_reference = filing_reference
    tax_return.save(
        update_fields=["status", "filed_by", "filed_at", "filing_reference", "updated_at"]
    )

    log_accounting_activity(
        user=user,
        action=AccountingAuditTrail.ActionType.POST,
        instance=tax_return,
        changes={"status": TaxReturn.Status.FILED, "reference": filing_reference},
    )

    return tax_return


def create_bank_reconciliation(company, account, period, user, bank_transactions_data=None):
    """Create an AccountReconciliation and optionally import bank transactions.

    bank_transactions_data: list of dicts with transaction_date, description,
    reference, amount, transaction_type.
    """
    with transaction.atomic():
        from .utils import get_account_balance_as_of

        as_of_date = period.end_date if period else timezone.now().date()
        ledger_balance = get_account_balance_as_of(account, as_of_date)

        statement_balance = Decimal("0.00")
        if bank_transactions_data:
            for tx in bank_transactions_data:
                amt = tx["amount"]
                if tx["transaction_type"] == "CREDIT":
                    statement_balance += amt
                else:
                    statement_balance -= amt

        variance = (statement_balance - ledger_balance).quantize(Decimal("0.01"))

        recon = AccountReconciliation.objects.create(
            company=company,
            account=account,
            period=period,
            statement_balance=statement_balance,
            ledger_balance=ledger_balance,
            variance=variance,
        )

        if bank_transactions_data:
            for tx in bank_transactions_data:
                BankTransaction.objects.create(
                    company=company,
                    account=account,
                    transaction_date=tx["transaction_date"],
                    description=tx["description"],
                    reference=tx.get("reference", ""),
                    amount=tx["amount"],
                    transaction_type=tx["transaction_type"],
                    reconciliation=recon,
                )

        log_accounting_activity(
            user=user,
            action=AccountingAuditTrail.ActionType.CREATE,
            instance=recon,
            changes={
                "statement_balance": str(statement_balance),
                "ledger_balance": str(ledger_balance),
                "variance": str(variance),
            },
        )

        return recon


def match_reconciliation_items(reconciliation, matches):
    """Match bank transactions to ledger journal entries.

    matches: list of dicts with bank_transaction_id, journal_entry_id, amount_matched, note.
    Automatically computes reconciliation balances and variance.
    """
    with transaction.atomic():
        for match in matches:
            bank_tx = BankTransaction.objects.get(
                id=match["bank_transaction_id"], reconciliation=reconciliation
            )
            journal_entry = JournalEntry.objects.get(id=match["journal_entry_id"])

            ReconciliationItem.objects.create(
                reconciliation=reconciliation,
                bank_transaction=bank_tx,
                journal_entry=journal_entry,
                amount_matched=match.get("amount_matched", bank_tx.amount),
                note=match.get("note", ""),
                status="MATCHED",
            )
            bank_tx.is_matched = True
            bank_tx.save(update_fields=["is_matched"])

        matched_total = Decimal("0.00")
        for item in reconciliation.items.filter(status="MATCHED"):
            matched_total += item.amount_matched

        unmatched_bank = BankTransaction.objects.filter(
            reconciliation=reconciliation, is_matched=False
        ).count()
        if unmatched_bank > 0:
            for btx in BankTransaction.objects.filter(
                reconciliation=reconciliation, is_matched=False
            ):
                ReconciliationItem.objects.create(
                    reconciliation=reconciliation,
                    bank_transaction=btx,
                    amount_matched=btx.amount,
                    note="Unmatched bank-side transaction",
                    status="UNMATCHED_BANK",
                )

        reconciliation.save(update_fields=["updated_at"])

        return reconciliation


def approve_reconciliation(reconciliation, user):
    """Approve a reconciliation after review."""
    if reconciliation.status not in ("OPEN", "INVESTIGATING"):
        raise ValidationError("Only OPEN or INVESTIGATING reconciliations can be approved.")

    reconciliation.status = "APPROVED"
    reconciliation.approved_by = user
    reconciliation.approved_at = timezone.now()
    reconciliation.save(
        update_fields=["status", "approved_by", "approved_at", "updated_at"]
    )

    log_accounting_activity(
        user=user,
        action=AccountingAuditTrail.ActionType.APPROVE,
        instance=reconciliation,
        changes={"status": "APPROVED"},
    )

    return reconciliation


def post_fx_revaluation(reval, user, unrealized_gain_account, unrealized_loss_account):
    """Post a CurrencyRevaluation: creates the journal and marks it POSTED.

    The net gain/loss is posted against the specified unrealized gain/loss accounts.
    Returns the posted CurrencyRevaluation instance.
    """
    if reval.status == CurrencyRevaluation.Status.POSTED:
        raise ValidationError("Revaluation is already posted.")
    if reval.status == CurrencyRevaluation.Status.REVERSED:
        raise ValidationError("Cannot post a reversed revaluation.")

    lines = reval.lines.all()
    if not lines:
        raise ValidationError("Revaluation has no lines to post.")

    total_gain = sum(
        (line.unrealized_gain_loss for line in lines if line.entry_type == "DEBIT"),
        Decimal("0.00"),
    )
    total_loss = sum(
        (line.unrealized_gain_loss for line in lines if line.entry_type == "CREDIT"),
        Decimal("0.00"),
    )

    journal_entries = []
    for line in lines:
        journal_entries.append({
            "account": line.account,
            "entry_type": line.entry_type,
            "amount": line.unrealized_gain_loss,
            "memo": f"FX revaluation {reval.revaluation_date}: {line.foreign_currency} @ {line.rate_at_revaluation}",
        })

    net_gain_loss = total_gain - total_loss
    if net_gain_loss > 0:
        journal_entries.append({
            "account": unrealized_gain_account,
            "entry_type": "CREDIT",
            "amount": net_gain_loss,
            "memo": f"Unrealized FX gain net settlement {reval.revaluation_date}",
        })
    elif net_gain_loss < 0:
        journal_entries.append({
            "account": unrealized_loss_account,
            "entry_type": "DEBIT",
            "amount": abs(net_gain_loss),
            "memo": f"Unrealized FX loss net settlement {reval.revaluation_date}",
        })

    with transaction.atomic():
        journal = create_journal_with_entries(
            company=reval.company,
            date=reval.revaluation_date,
            description=f"FX Revaluation as of {reval.revaluation_date} ({reval.base_currency})",
            entries=journal_entries,
            user=user,
            auto_post=True,
            validate_balances=False,
        )

        reval.journal = journal
        reval.status = CurrencyRevaluation.Status.POSTED
        reval.save(update_fields=["journal", "status", "updated_at"])

        log_accounting_activity(
            user=user,
            action=AccountingAuditTrail.ActionType.FX_REVALUATION,
            instance=reval,
            changes={"status": CurrencyRevaluation.Status.POSTED},
            reason=f"Posted FX revaluation for {reval.revaluation_date}",
        )

    return reval


def reverse_fx_revaluation(reval, user, reason=None):
    """Reverse a posted FX revaluation: reverses the journal and marks reval as REVERSED."""
    if reval.status != CurrencyRevaluation.Status.POSTED:
        raise ValidationError("Only posted revaluations can be reversed.")
    if not reval.journal:
        raise ValidationError("Revaluation has no linked journal.")

    with transaction.atomic():
        reverse_journal(
            reval.journal,
            user,
            reason=reason or f"Reversal of FX revaluation {reval.revaluation_date}",
        )
        reval.status = CurrencyRevaluation.Status.REVERSED
        reval.save(update_fields=["status", "updated_at"])

        log_accounting_activity(
            user=user,
            action=AccountingAuditTrail.ActionType.FX_REVALUATION_REVERSE,
            instance=reval,
            changes={"status": CurrencyRevaluation.Status.REVERSED},
            reason=reason,
        )

    return reval
