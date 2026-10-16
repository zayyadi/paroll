"""Ledger-derived leave balances (P1-6).

Gap #6 of docs/world_class_employee_management_research_2026-10-14.md: replace
stored per-year counters with append-only accrual/usage/carry-forward/expiry
events summed at read time (BambooHR history, Frappe leave ledger).

``LeaveBalance`` stays as a read model; :func:`sync_balance_read_model`
materialises it from the ledger so existing counter consumers keep working.
The ledger is the source of truth: every balance question is answered by
summing ``LeaveLedgerEntry`` rows, never by reading a mutable counter.

Conventions:
- accrual / carry_forward / positive adjustment rows are ``+days``
- usage / expiry rows are ``-days``
- a balance is therefore ``Sum(days)`` over ``(employee, leave_type, year)``
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db.models import Sum

from payroll.models import LeaveBalance, LeaveLedgerEntry, LeavePolicy

CENTS = Decimal("0.01")

# LeavePolicy.LEAVE_TYPES code -> LeaveBalance column holding its counter.
BALANCE_COLUMNS = {
    "ANNUAL": "annual_leave",
    "SICK": "sick_leave",
    "CASUAL": "casual_leave",
    "MATERNITY": "maternity_leave",
    "PATERNITY": "paternity_leave",
}


def record_event(
    *,
    employee: Any,
    leave_type: str,
    event_type: str,
    days: Decimal,
    year: int,
    leave_request: Any = None,
    note: str = "",
    actor: Any = None,
) -> LeaveLedgerEntry:
    """Append one signed event to the leave ledger.

    ``days`` must be non-zero; sign convention is enforced by callers (usage
    and expiry append negative days, everything else positive).
    """
    days = Decimal(days)
    if days == 0:
        raise ValidationError("A leave ledger event must move the balance by a non-zero number of days.")
    from payroll.services.leave_type_service import ensure_default_leave_types
    from payroll.models import LeaveType
    ensure_default_leave_types(employee.company)
    valid_types = set(LeaveType.objects.filter(company=employee.company).values_list("code", flat=True))
    if leave_type not in valid_types:
        raise ValidationError(f"Unknown leave type {leave_type!r}.")
    return LeaveLedgerEntry.objects.create(
        employee=employee,
        leave_type=leave_type,
        event_type=event_type,
        days=days,
        year=year,
        leave_request=leave_request,
        note=note,
        created_by=actor,
    )


def record_accrual(
    employee: Any, leave_type: str, year: int, days: Decimal, **kwargs
) -> LeaveLedgerEntry:
    """Grant the annual entitlement for a year."""
    return record_event(
        employee=employee,
        leave_type=leave_type,
        event_type=LeaveLedgerEntry.EventType.ACCRUAL,
        days=Decimal(days),
        year=year,
        **kwargs,
    )


def record_usage(
    leave_request: Any, days: Optional[Decimal] = None, **kwargs
) -> LeaveLedgerEntry:
    """Consume days for an approved leave request (negative)."""
    days = Decimal(days if days is not None else leave_request.duration)
    return record_event(
        employee=leave_request.employee,
        leave_type=leave_request.leave_type,
        event_type=LeaveLedgerEntry.EventType.USAGE,
        days=-days,
        year=leave_request.start_date.year,
        leave_request=leave_request,
        **kwargs,
    )


def record_carry_forward(
    employee: Any, leave_type: str, year: int, days: Decimal, **kwargs
) -> LeaveLedgerEntry:
    """Carry days into ``year`` from the previous year (positive)."""
    return record_event(
        employee=employee,
        leave_type=leave_type,
        event_type=LeaveLedgerEntry.EventType.CARRY_FORWARD,
        days=Decimal(days),
        year=year,
        **kwargs,
    )


def record_expiry(
    employee: Any, leave_type: str, year: int, days: Decimal, **kwargs
) -> LeaveLedgerEntry:
    """Lapse carried-forward days (negative)."""
    return record_event(
        employee=employee,
        leave_type=leave_type,
        event_type=LeaveLedgerEntry.EventType.EXPIRY,
        days=-Decimal(days),
        year=year,
        **kwargs,
    )


def record_adjustment(
    employee: Any,
    leave_type: str,
    year: int,
    days: Decimal,
    **kwargs,
) -> LeaveLedgerEntry:
    """Manual correction; ``days`` may be positive or negative."""
    return record_event(
        employee=employee,
        leave_type=leave_type,
        event_type=LeaveLedgerEntry.EventType.ADJUSTMENT,
        days=Decimal(days),
        year=year,
        **kwargs,
    )


def ledger_balance(employee: Any, leave_type: str, year: int) -> Decimal:
    """Balance for one leave type, summed from the ledger at read time."""
    total = (
        LeaveLedgerEntry.objects.filter(
            employee=employee, leave_type=leave_type, year=year
        )
        .aggregate(total=Sum("days"))["total"]
    )
    return Decimal(total or 0)


def ledger_balances(employee: Any, year: int) -> dict:
    """All leave-type balances for an employee/year, summed from the ledger."""
    rows = (
        LeaveLedgerEntry.objects.filter(employee=employee, year=year)
        .values("leave_type")
        .annotate(total=Sum("days"))
    )
    by_type = {row["leave_type"]: Decimal(row["total"] or 0) for row in rows}
    return {
        code: by_type.get(code, Decimal(0))
        for code in set(BALANCE_COLUMNS) | set(by_type)
    }


def seed_balance_accruals(employee: Any, balance: Any) -> None:
    """Record the entitlement seeded with a brand-new ``LeaveBalance`` row.

    ``get_leave_balance`` creates the yearly row with default entitlements
    (and prior-year carryover); this mirrors that seeding into the ledger so
    counter and ledger always agree. Split into an ACCRUAL for the base
    entitlement plus a CARRY_FORWARD for the carried-over annual days.
    """
    carryover = int(getattr(balance, "carried_over_annual_leave", 0) or 0)
    year = balance.year
    annual_base = max(0, int(balance.annual_leave or 0) - carryover)
    seeded = {
        "ANNUAL": annual_base,
        "SICK": balance.sick_leave,
        "CASUAL": balance.casual_leave,
        "MATERNITY": balance.maternity_leave,
        "PATERNITY": balance.paternity_leave,
    }
    for leave_type, days in seeded.items():
        if days:
            record_accrual(employee, leave_type, year, Decimal(days))
    if carryover:
        record_carry_forward(employee, "ANNUAL", year, Decimal(carryover))


def sync_balance_read_model(employee: Any, year: int) -> LeaveBalance:
    """Materialise the ``LeaveBalance`` read model from the ledger.

    Existing consumers (payslip accrual, offboarding settlement) read counters
    on ``LeaveBalance``; this keeps them in step with the ledger without
    changing their code.

    Only leave types that actually have ledger events are written: legacy rows
    created before the ledger existed keep their counters untouched rather
    than being zeroed.
    """
    balances = ledger_balances(employee, year)
    present = set(
        LeaveLedgerEntry.objects.filter(employee=employee, year=year)
        .values_list("leave_type", flat=True)
        .distinct()
    )
    balance, _ = LeaveBalance.objects.get_or_create(
        employee=employee, year=year
    )
    updates = {}
    for code, column in BALANCE_COLUMNS.items():
        if code not in present:
            continue
        value = balances.get(code, Decimal(0))
        # Counters are whole days today; keep them non-negative integers.
        updates[column] = max(0, int(value))
    if updates:
        for column, value in updates.items():
            setattr(balance, column, value)
        LeaveBalance.objects.filter(pk=balance.pk).update(**updates)
        balance.refresh_from_db()
    return balance
