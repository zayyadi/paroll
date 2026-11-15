"""Clearing payroll liabilities when money actually leaves the bank.

Locking a run posts the accrual (payroll_accounting_service): expense against
Net Salaries Payable and one payable per statutory body. This module posts the
settlements that clear them:

    record_salary_payment   Dr Net Salaries Payable / Cr Bank
                            (from the approved bank-file confirmation)
    record_remittance       Dr <body> Payable / Cr Bank
    reverse_remittance      reverses the remittance journal (undo)

Amounts come from the ledger itself, i.e. what the accrual journals credited,
so payables clear to exactly zero. Every journal carries a posting_key that is
unique among journals still in effect, so a retried action can't post twice.

Remittance journals are not part of any other approval, so they go through the
journal approval like any manual journal: marking a remittance submits the
journal, and it posts once independently approved. Calls go through
``accounting.utils`` at call time because the approvals app wraps those
helpers to turn them into approval requests outside an approved execution.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet, Sum
from django.utils import timezone

from accounting import utils as accounting_utils
from accounting.models import Journal, JournalEntry
from payroll.models import PayrollRun, RemittanceRecord
from payroll.services.payroll_accounting_service import PAYROLL_ACCOUNTS, get_account

logger = logging.getLogger(__name__)

Status = PayrollRun.Status
ZERO = Decimal("0.00")
INACTIVE = [Journal.JournalStatus.REVERSED, Journal.JournalStatus.CANCELLED]

# Remittance obligation -> the payable it clears. Obligations missing here
# (paye_annual) are filings with no money attached.
REMITTANCE_ACCOUNTS = {
    "paye": "paye_payable",
    "pension": "pension_payable",
    "nhf": "nhf_payable",
    "nhia": "health_payable",
    "nsitf": "nsitf_payable",
    "itf": "itf_payable",
}
ANNUAL_OBLIGATIONS = {"itf"}


def _posted_lines(company: Any, account_key: str) -> QuerySet:
    return JournalEntry.objects.filter(
        journal__company=company,
        journal__status=Journal.JournalStatus.POSTED,
        account__account_number=PAYROLL_ACCOUNTS[account_key][2],
    )


def _total(lines: QuerySet, entry_type: str) -> Decimal:
    return Decimal(lines.filter(entry_type=entry_type).aggregate(t=Sum("amount"))["t"] or 0)


def _two_line_entries(company: Any, debit_key: str, amount: Decimal, memo: str) -> list:
    return [
        {"account": get_account(company, debit_key), "entry_type": "DEBIT", "amount": amount, "memo": memo},
        {"account": get_account(company, "bank"), "entry_type": "CREDIT", "amount": amount, "memo": memo},
    ]


# --- salary payment ----------------------------------------------------------


def _payment_key_prefix(run: PayrollRun) -> str:
    return f"payroll_run:{run.pk}:payment:"


def net_salary_outstanding(run: PayrollRun) -> Decimal:
    """Net pay accrued for ``run`` that hasn't been paid out yet."""
    accrued = _posted_lines(run.company, "net_salaries_payable").filter(
        journal__posting_key=f"payroll_run:{run.pk}:accrual"
    )
    paid = _posted_lines(run.company, "net_salaries_payable").filter(
        journal__posting_key__startswith=_payment_key_prefix(run)
    )
    return _total(accrued, "CREDIT") - _total(paid, "DEBIT")


def record_salary_payment(
    run: PayrollRun, user: Any, *, amount: Decimal, source: Any, reference: str
) -> Journal | None:
    """
    Post Dr Net Salaries Payable / Cr Bank for ``amount`` (capped at what is
    outstanding). Called inside the approved bank-payment execution, so the
    journal posts immediately. Runs locked before Net Salaries Payable existed
    (their accrual credited Cash) have nothing outstanding and post nothing.
    """
    outstanding = net_salary_outstanding(run)
    pay = min(Decimal(amount), outstanding)
    if Decimal(amount) > outstanding:
        logger.warning(
            "Payment of %s for payroll run %s exceeds outstanding net pay %s; capped.",
            amount, run.pk, outstanding,
        )
    if pay <= ZERO:
        return None
    on = timezone.localdate()
    fiscal_year = accounting_utils.get_or_create_fiscal_year(on.year, company=run.company)
    return accounting_utils.create_journal_with_entries(
        company=run.company,
        date=on,
        description=f"Salary payment: {run.name}",
        entries=_two_line_entries(run.company, "net_salaries_payable", pay, f"Net salaries paid - {run.name}"),
        fiscal_year=fiscal_year,
        period=accounting_utils.get_or_create_period(fiscal_year, on.month, company=run.company),
        source_object=source,
        user=user,
        auto_post=True,
        validate_balances=False,
        posting_key=f"{_payment_key_prefix(run)}{reference}",
    )


# --- statutory remittances ---------------------------------------------------


def locked_runs_for(company: Any, obligation: str, period: Any) -> QuerySet:
    """Locked/paid runs whose accruals an obligation-period remits."""
    runs = PayrollRun.all_objects.filter(
        company=company, status__in=[Status.LOCKED, Status.PAID]
    )
    if obligation in ANNUAL_OBLIGATIONS:
        return runs.filter(paydays__year=period.year)
    return runs.filter(paydays__year=period.year, paydays__month=period.month)


def accrued_amount(company: Any, obligation: str, period: Any) -> Decimal:
    """What the period's accrual journals credited to this obligation's payable."""
    account_key = REMITTANCE_ACCOUNTS.get(obligation)
    if account_key is None or period is None:
        return ZERO
    keys = [
        f"payroll_run:{pk}:accrual"
        for pk in locked_runs_for(company, obligation, period).values_list("pk", flat=True)
    ]
    lines = _posted_lines(company, account_key).filter(journal__posting_key__in=keys)
    return _total(lines, "CREDIT")


def _remittance_key(record: RemittanceRecord) -> str:
    return f"remittance:{record.pk}"


def _active_remittance_journal(record: RemittanceRecord) -> Journal | None:
    return (
        Journal.objects.filter(company=record.company, posting_key=_remittance_key(record))
        .exclude(status__in=INACTIVE)
        .first()
    )


def _generation(record: RemittanceRecord) -> int:
    """How many times this remittance has been posted and undone; keys new requests."""
    return Journal.objects.filter(
        company=record.company,
        posting_key=_remittance_key(record),
        status=Journal.JournalStatus.REVERSED,
    ).count()


def record_remittance(record: RemittanceRecord, user: Any) -> Any:
    """
    Submit Dr <body> Payable / Cr Bank for the period's accrued amount. Returns
    the approval request (or the existing journal if one is already in
    effect, or None when there is nothing to post).
    """
    account_key = REMITTANCE_ACCOUNTS.get(record.obligation)
    if account_key is None:
        return None
    existing = _active_remittance_journal(record)
    if existing is not None:
        return existing
    amount = accrued_amount(record.company, record.obligation, record.period)
    if amount <= ZERO:
        return None

    on = record.remitted_on or timezone.localdate()
    fiscal_year = accounting_utils.get_or_create_fiscal_year(on.year, company=record.company)
    label = f"{record.get_obligation_display()} remittance {record.period}"
    return accounting_utils.create_journal_with_entries(
        company=record.company,
        date=on,
        description=label,
        entries=_two_line_entries(record.company, account_key, amount, label),
        fiscal_year=fiscal_year,
        period=accounting_utils.get_or_create_period(fiscal_year, on.month, company=record.company),
        source_object=record,
        user=user,
        auto_post=True,
        validate_balances=False,
        posting_key=_remittance_key(record),
        approval_key=f"{_remittance_key(record)}:{_generation(record)}",
    )


def reverse_remittance(record: RemittanceRecord, user: Any) -> Any:
    """Undo a remittance: request reversal of its posted journal."""
    journal = (
        Journal.objects.filter(
            company=record.company,
            posting_key=_remittance_key(record),
            status=Journal.JournalStatus.POSTED,
        ).first()
    )
    if journal is None:
        return None
    return accounting_utils.reverse_journal(
        journal,
        user,
        "Remittance marked as not done",
        approval_key=f"{_remittance_key(record)}:{_generation(record)}:reverse",
    )
