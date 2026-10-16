"""Retroactive pay deltas for backdated salary changes (P1-5).

Gap #5 of docs/world_class_employee_management_research_2026-10-14.md: define how
a backdated salary change produces a delta in the current period, with an audit
trail and a matching negative entry if reversed.

The delta is the canonical net-pay difference (``payroll_calc``) between the new
and old salary configs, multiplied by the whole months between the effective
date and the catch-up period. Applying a delta records a ``RetroPayDelta`` and
an ``Allowance`` so it flows into the normal payroll calculation; reversing it
records the matching negative delta and clears the original.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.utils import timezone

from payroll.models import Allowance, Payroll, RetroPayDelta
from payroll.services.payroll_calc import monthly_net_pay

CENTS = Decimal("0.01")


def _month_first(value: date) -> date:
    return value.replace(day=1)


def _months_between(effective: date, period: date) -> int:
    """Whole months from the month containing ``effective`` to ``period``.

    A change effective in the same month as the catch-up period pays zero
    retro months (the new rate already applied that month). Otherwise it is
    the calendar-month difference.
    """
    eff = _month_first(effective)
    per = _month_first(period)
    return max(0, (per.year - eff.year) * 12 + (per.month - eff.month))


def monthly_net_for(config: Payroll) -> Decimal:
    """Canonical monthly net pay for a salary config."""
    return monthly_net_pay(
        gross_annual=config.gross_income,
        employee_health_annual=config.employee_health,
        nhf_annual=config.nhf,
        payee_monthly=config.payee,
        water_monthly=config.water_rate,
    )["net"]


def compute_retro_delta(
    from_config: Payroll,
    to_config: Payroll,
    effective_date: date,
    period: date,
) -> dict:
    """Compute (but do not persist) the retroactive catch-up for a raise.

    Returns a dict with ``months_owed``, ``monthly_delta`` and
    ``total_delta``. A lower (or equal) new net yields a zero delta; retro pay
    only ever pays an underpayment, never claws back an overpayment here (use
    an explicit reversal for that).
    """
    old_monthly = monthly_net_for(from_config)
    new_monthly = monthly_net_for(to_config)
    months = _months_between(effective_date, period)
    monthly_delta = (new_monthly - old_monthly).quantize(CENTS)
    if monthly_delta < 0:
        monthly_delta = Decimal("0.00")
    total_delta = (monthly_delta * months).quantize(CENTS)
    return {
        "months_owed": months,
        "monthly_delta": monthly_delta,
        "total_delta": total_delta,
    }


def apply_retro_delta(
    *,
    employee: Any,
    from_config: Payroll,
    to_config: Payroll,
    effective_date: date,
    period: date,
    actor: Any = None,
    note: str = "",
) -> RetroPayDelta:
    """Record and pay a retroactive catch-up for a backdated raise.

    Creates the ``RetroPayDelta`` audit row and a matching ``Allowance`` so the
    amount enters the payroll calculation for ``period``. Raises when there is
    nothing owed.
    """
    if employee.employee_pay_id != to_config.pk:
        raise ValidationError(
            "The retroactive delta must be computed against the employee's "
            "current salary config."
        )
    computed = compute_retro_delta(from_config, to_config, effective_date, period)
    if computed["total_delta"] <= 0:
        raise ValidationError("No retroactive pay is owed for this change.")

    delta = RetroPayDelta(
        employee=employee,
        from_config=from_config,
        to_config=to_config,
        effective_date=effective_date,
        period=period,
        months_owed=computed["months_owed"],
        monthly_delta=computed["monthly_delta"],
        total_delta=computed["total_delta"],
        note=note,
        created_by=actor,
    )
    allowance = Allowance.objects.create(
        employee=employee,
        allowance_type="Retro",
        amount=computed["total_delta"],
    )
    delta.allowance = allowance
    delta.status = RetroPayDelta.Status.APPLIED
    delta.save()
    return delta


def reverse_retro_delta(
    delta: RetroPayDelta, *, actor: Any = None, note: str = ""
) -> RetroPayDelta:
    """Reverse an applied retro delta with a matching negative adjustment.

    Records a new ``RetroPayDelta`` carrying the negated amount (audit trail is
    append-only) and marks the original ``REVERSED``. The positive allowance is
    zeroed so it no longer inflates the payroll.
    """
    if delta.status != RetroPayDelta.Status.APPLIED:
        raise ValidationError("Only an applied retro pay delta can be reversed.")

    reversal = RetroPayDelta(
        employee=delta.employee,
        from_config=delta.from_config,
        to_config=delta.to_config,
        effective_date=delta.effective_date,
        period=delta.period,
        months_owed=delta.months_owed,
        monthly_delta=-delta.monthly_delta,
        total_delta=-delta.total_delta,
        note=note or f"Reversal of retro delta #{delta.pk}",
        created_by=actor,
        status=RetroPayDelta.Status.REVERSED,
    )
    if delta.allowance_id:
        # Neutralise the original allowance rather than delete it (audit).
        delta.allowance.amount = Decimal("0.00")
        delta.allowance.save(update_fields=["amount"])
    reversal.save()
    delta.status = RetroPayDelta.Status.REVERSED
    delta.save(update_fields=["status", "updated_at"])
    return reversal
