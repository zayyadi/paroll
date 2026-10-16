"""Company-configurable leave types (P2-12, gap #12).

Replaces the fixed five-type catalogue that was hard-coded in two places.
Each company gets its own ``LeaveType`` rows; the Nigerian statutory defaults
are seeded on first use. ``get_leave_balance`` reads entitlements from here.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.core.exceptions import ValidationError

from payroll.models import LeaveType

# Nigerian statutory defaults. Values follow the pre-refactor
# ``get_leave_balance`` defaults (20/10/7/90/14), which were the effective
# source of truth on a fresh DB and what the leave views displayed.
DEFAULT_LEAVE_TYPES = (
    {"code": "ANNUAL", "name": "Annual Leave", "default_days": Decimal("20"),
     "is_paid": True, "allows_half_day": True, "encashable": True,
     "encashment_rate": Decimal("1.00"), "carryover_rate": Decimal("1")},
    {"code": "SICK", "name": "Sick Leave", "default_days": Decimal("10"),
     "is_paid": True, "allows_half_day": False, "encashable": False,
     "carryover_rate": Decimal("0")},
    {"code": "CASUAL", "name": "Casual Leave", "default_days": Decimal("7"),
     "is_paid": True, "allows_half_day": True, "encashable": False,
     "carryover_rate": Decimal("0")},
    {"code": "MATERNITY", "name": "Maternity Leave", "default_days": Decimal("90"),
     "is_paid": True, "allows_half_day": False, "encashable": False,
     "carryover_rate": Decimal("0")},
    {"code": "PATERNITY", "name": "Paternity Leave", "default_days": Decimal("14"),
     "is_paid": True, "allows_half_day": False, "encashable": False,
     "carryover_rate": Decimal("0")},
)


def ensure_default_leave_types(company: Any = None) -> list[LeaveType]:
    """Idempotently seed the statutory default leave types for a company.

    Safe to call on every balance read; existing rows are left untouched so
    an admin's customisations survive. Returns the company's active rows.
    """
    for spec in DEFAULT_LEAVE_TYPES:
        LeaveType.objects.get_or_create(
            company=company,
            code=spec["code"],
            defaults={k: v for k, v in spec.items() if k != "code"},
        )
    return list(
        LeaveType.objects.filter(company=company, is_active=True).order_by("code")
    )


def entitlement_days(code: str, company: Any = None) -> Decimal:
    """Annual entitlement, in days, for a leave type.

    Falls back to the legacy ``LeavePolicy``/hard-coded defaults when the type
    has not been seeded yet (company-less contexts, pre-migration data).
    """
    if LeaveType.objects.filter(company=company, code=code, is_active=False).exists():
        return Decimal("0")
    qs = LeaveType.objects.filter(code=code, is_active=True)
    if company is not None:
        row = qs.filter(company=company).first() or qs.filter(
            company__isnull=True
        ).first()
    else:
        row = qs.filter(company__isnull=True).first()
    if row is not None:
        return row.default_days
    # Legacy fallback: the old get_leave_balance() dict.
    return {
        "ANNUAL": Decimal("20"),
        "SICK": Decimal("10"),
        "CASUAL": Decimal("7"),
        "MATERNITY": Decimal("90"),
        "PATERNITY": Decimal("14"),
    }.get(code, Decimal("0"))


def get_leave_type(code: str, company: Any = None) -> Optional[LeaveType]:
    qs = LeaveType.objects.filter(code=code, is_active=True)
    if company is not None:
        return qs.filter(company=company).first() or qs.filter(
            company__isnull=True
        ).first()
    return qs.filter(company__isnull=True).first()


def validate_half_day(code: str, is_half_day: bool, company: Any = None) -> None:
    """Reject a half-day request for a type that does not allow it.

    Falls back to the seeded defaults for types that have not been created
    yet, so the documented behaviour (e.g. SICK disallows half days) holds
    even before a company's catalogue is materialised.
    """
    if not is_half_day:
        return
    row = get_leave_type(code, company)
    if row is not None:
        if not row.allows_half_day:
            raise ValidationError(
                f"{row.name} cannot be taken in half-day increments."
            )
        return
    # Un-seeded type: apply the documented default.
    default = next(
        (spec for spec in DEFAULT_LEAVE_TYPES if spec["code"] == code), None
    )
    if default is not None and not default["allows_half_day"]:
        raise ValidationError(
            f"{default['name']} cannot be taken in half-day increments."
        )


def create_leave_type(*, company: Any, code: str, name: str, default_days: Decimal,
                      is_paid: bool = True, allows_half_day: bool = False,
                      encashable: bool = False, encashment_rate: Decimal = Decimal("1.00"),
                      carryover_rate: Decimal = Decimal("0")) -> LeaveType:
    if LeaveType.objects.filter(company=company, code=code).exists():
        raise ValidationError(f"Leave type {code!r} already exists for this company.")
    return LeaveType.objects.create(
        company=company, code=code, name=name, default_days=Decimal(default_days),
        is_paid=is_paid, allows_half_day=allows_half_day, encashable=encashable,
        encashment_rate=Decimal(encashment_rate), carryover_rate=Decimal(carryover_rate),
    )


__all__ = [
    "DEFAULT_LEAVE_TYPES",
    "ensure_default_leave_types",
    "entitlement_days",
    "get_leave_type",
    "validate_half_day",
    "create_leave_type",
]


def available_leave_balances(employee, year=None):
    """Catalogue balances; legacy counters remain a compatibility read model."""
    from django.db import transaction
    from django.utils import timezone
    from payroll.models import LeaveBalance, LeaveLedgerEntry
    from payroll.models.payroll import get_leave_balance
    from payroll.services.leave_ledger import BALANCE_COLUMNS, ledger_balance, record_accrual
    year = year or timezone.localdate().year
    catalogue = ensure_default_leave_types(employee.company)
    balance = get_leave_balance(employee, year)
    result = {}
    with transaction.atomic():
        LeaveBalance.objects.select_for_update().get(pk=balance.pk)
        for row in catalogue:
            events = LeaveLedgerEntry.objects.filter(employee=employee, leave_type=row.code, year=year)
            if row.code not in BALANCE_COLUMNS and not events.exists() and row.default_days:
                record_accrual(employee, row.code, year, row.default_days)
            if events.exists():
                result[row.code] = ledger_balance(employee, row.code, year)
            else:
                result[row.code] = Decimal(getattr(balance, BALANCE_COLUMNS.get(row.code, ""), 0))
    return result


def leave_balance_cards(employee, year=None):
    balances = available_leave_balances(employee, year)
    return [{"code": row.code, "name": row.name, "days": balances[row.code]}
            for row in ensure_default_leave_types(employee.company)]
