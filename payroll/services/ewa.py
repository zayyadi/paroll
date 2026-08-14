"""Self-service Earned Wage Access (EWA) rules engine.

EWA productizes the existing IOU engine: advances are capped against the
employee's earned-but-unpaid wages in the current pay cycle, limited by
per-cycle frequency rules, and guarded so the next run's take-home pay never
drops below a floor.

Policy comes from ``CompanyPayrollSetting`` (``ewa_*`` fields); the rules are
pure and unit-testable. The request flow (``payroll.views.payroll_iou``)
enforces the returned limits before an IOU marked ``is_ewa`` is created.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from django.db.models import QuerySet, Sum
from django.utils import timezone

from payroll.models import CompanyPayrollSetting, EmployeeProfile, IOU

# Statuses that no longer consume advance headroom.
CLOSED_STATUSES = ("REJECTED", "PAID")


def _as_decimal(value: object) -> Decimal:
    return Decimal(value or 0)


def _advance_queryset(employee: EmployeeProfile) -> QuerySet:
    """All EWA advances for an employee, excluding rejected ones."""
    return IOU.objects.filter(
        employee_id=employee,
        is_ewa=True,
    ).exclude(status="REJECTED")


def _outstanding_queryset(employee: EmployeeProfile) -> QuerySet:
    """Unrepaid EWA advances (still owed from net pay)."""
    return _advance_queryset(employee).exclude(status__in=CLOSED_STATUSES)


def _setting_value(
    setting: Optional[CompanyPayrollSetting], field: str, default: Any
) -> Any:
    value = getattr(setting, field, None) if setting else None
    # Nullable policy columns fall back to the rule defaults.
    return value if value is not None else default


def ew_advance_limits(
    employee: EmployeeProfile, as_of: Optional[date] = None
) -> dict:
    """
    Compute the EWA policy surface for one employee on ``as_of``.

    Three guardrails, all enforced here:

    1. **Advance cap** — a new advance (plus what is already outstanding this
       cycle) may not exceed ``ewa_advance_percent``% of the net pay earned
       so far in the current cycle (calendar month).
    2. **Per-cycle frequency** — at most ``ewa_max_per_cycle`` advances per
       cycle, spaced at least ``ewa_min_days_between`` days apart.
    3. **Net-pay guardrail** — total unrepaid advances (this cycle and prior)
       plus the new request may not push the next run's take-home below
       ``ewa_min_take_home_percent``% of net pay.

    ``max_available`` is the amount a new request may be for (the binding
    minimum of the two monetary caps), and ``eligible``/``reasons`` describe
    whether a request can be made at all.
    """
    as_of = as_of or timezone.localdate()
    setting = CompanyPayrollSetting.objects.filter(company=employee.company).first()

    enabled = bool(_setting_value(setting, "ewa_enabled", False))
    cap_percent = Decimal(_setting_value(setting, "ewa_advance_percent", 50))
    max_per_cycle = int(_setting_value(setting, "ewa_max_per_cycle", 2))
    min_days_between = int(_setting_value(setting, "ewa_min_days_between", 7))
    min_take_home_percent = Decimal(
        _setting_value(setting, "ewa_min_take_home_percent", 50)
    )

    net_pay = _as_decimal(employee.net_pay)
    if net_pay <= 0 and employee.employee_pay:
        net_pay = _as_decimal(employee.employee_pay.basic_salary)

    # --- Advance cap: earned-but-unpaid net pay to date in the cycle -------
    days_in_month = calendar.monthrange(as_of.year, as_of.month)[1]
    earned_fraction = min(Decimal(as_of.day) / Decimal(days_in_month), Decimal("1"))
    earned_net = (net_pay * earned_fraction).quantize(Decimal("0.01"))
    cycle_advance_cap = (earned_net * cap_percent / Decimal("100")).quantize(
        Decimal("0.01")
    )

    # --- Per-cycle frequency ----------------------------------------------
    advances_this_cycle = _advance_queryset(employee).filter(
        created_at__year=as_of.year,
        created_at__month=as_of.month,
    )
    advance_count_this_cycle = advances_this_cycle.count()
    outstanding_in_cycle = (
        advances_this_cycle.exclude(status__in=CLOSED_STATUSES).aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )
    last_advance = _advance_queryset(employee).order_by("-created_at", "-id").first()
    days_since_last = (
        (as_of - last_advance.created_at).days if last_advance else None
    )

    # --- Net-pay guardrail -------------------------------------------------
    take_home_floor = (net_pay * min_take_home_percent / Decimal("100")).quantize(
        Decimal("0.01")
    )
    outstanding_total = (
        _outstanding_queryset(employee).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    guardrail_cap = max(
        net_pay - take_home_floor - outstanding_total, Decimal("0.00")
    ).quantize(Decimal("0.01"))

    remaining_cycle_cap = max(
        cycle_advance_cap - outstanding_in_cycle, Decimal("0.00")
    ).quantize(Decimal("0.01"))
    max_available = min(remaining_cycle_cap, guardrail_cap)
    if not enabled:
        # The program is off: no advance is available, whatever the caps say.
        max_available = Decimal("0.00")

    reasons = []
    if not enabled:
        reasons.append("Earned wage access is not enabled for your company.")
    if advance_count_this_cycle >= max_per_cycle:
        reasons.append(
            f"You have used all {max_per_cycle} advance(s) allowed for this pay cycle."
        )
    if days_since_last is not None and days_since_last < min_days_between:
        next_date = last_advance.created_at + timedelta(days=min_days_between)
        reasons.append(
            f"You can request your next advance from {next_date.strftime('%d %b %Y')}."
        )
    if max_available <= 0:
        reasons.append("No advance is available under the current caps.")

    return {
        "enabled": enabled,
        "net_pay": net_pay,
        "earned_net": earned_net,
        "cycle_advance_cap": cycle_advance_cap,
        "outstanding_in_cycle": outstanding_in_cycle,
        "remaining_cycle_cap": remaining_cycle_cap,
        "max_per_cycle": max_per_cycle,
        "advances_this_cycle": advance_count_this_cycle,
        "remaining_this_cycle": max(max_per_cycle - advance_count_this_cycle, 0),
        "min_days_between": min_days_between,
        "last_advance_date": last_advance.created_at if last_advance else None,
        "days_since_last": days_since_last,
        "min_take_home_percent": min_take_home_percent,
        "take_home_floor": take_home_floor,
        "outstanding_total": outstanding_total,
        "guardrail_cap": guardrail_cap,
        "max_available": max_available,
        "eligible": enabled and advance_count_this_cycle < max_per_cycle
        and (days_since_last is None or days_since_last >= min_days_between)
        and max_available > 0,
        "reasons": reasons,
    }
