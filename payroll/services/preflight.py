"""Run-level pre-flight readiness check (Gusto blockers analogue).

Gap #2 of docs/world_class_employee_management_research_2026-10-14.md: before a
payroll run may go CALCULATED → REVIEWED, surface every condition that would
make the run un-payable or un-postable as a *typed, resolvable* blocker rather
than letting it fail deep inside bank-file generation, the accounting close or
a statutory remittance.

Each blocker carries:
- ``code``      — a stable machine code (API/UI can key off it),
- ``message``   — human-readable what is wrong,
- ``resolution``— what the operator must do to clear it,
- optional ``employee_id`` / ``obligation`` / ``period`` context.

This module is deliberately import-light (Django models only) and free of side
effects: it reads state and returns findings. Enforcement lives in
``PayrollRun.transition_to``; callers can also invoke ``run_preflight`` directly
to render a readiness panel.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from django.utils import timezone

# Obligations whose prior-period remittance is checked before a new run opens.
MONTHLY_OBLIGATIONS = ("paye", "pension", "nhf", "nhia", "nsitf")


@dataclass(frozen=True)
class Blocker:
    """A single typed, resolvable readiness failure."""

    code: str
    message: str
    resolution: str
    employee_id: Optional[int] = None
    obligation: Optional[str] = None
    period: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "resolution": self.resolution,
            "employee_id": self.employee_id,
            "obligation": self.obligation,
            "period": self.period,
        }


@dataclass
class PreflightReport:
    """All blockers found for a run; truthy when the run is ready."""

    blockers: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers

    def codes(self) -> list:
        return [b.code for b in self.blockers]

    def raise_if_blocked(self) -> None:
        """Raise a ``ValidationError`` listing every blocker, if any."""
        if self.ok:
            return
        from django.core.exceptions import ValidationError

        detail = "; ".join(f"[{b.code}] {b.message}" for b in self.blockers)
        raise ValidationError(f"Payroll run failed pre-flight: {detail}")

    def __bool__(self) -> bool:
        return self.ok


def _as_date(value: Any) -> Optional[date]:
    """Normalize a Month/date/datetime/str to a ``date`` (period start)."""
    if value is None:
        return None
    first_day = getattr(value, "first_day", None)
    if callable(first_day):
        return first_day()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        from datetime import datetime

        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return None
    return None


def _check_period(run: Any, blockers: list) -> Optional[date]:
    """A run must carry a pay period to anchor every other check."""
    period = _as_date(run.paydays)
    if period is None:
        blockers.append(
            Blocker(
                code="missing_pay_schedule",
                message="The payroll run has no pay period (paydays) set.",
                resolution="Set the run's pay period before reviewing it.",
            )
        )
    return period


def _check_company_settings(run: Any, blockers: list) -> None:
    """Statutory percentages need a CompanyPayrollSetting row."""
    from payroll.models import CompanyPayrollSetting

    if run.company_id and not CompanyPayrollSetting.objects.filter(
        company=run.company
    ).exists():
        blockers.append(
            Blocker(
                code="missing_payroll_settings",
                message=(
                    "The company has no payroll settings, so statutory "
                    "percentages (pension, NHF, NHIA) fall back to defaults."
                ),
                resolution="Create the company payroll settings before review.",
            )
        )


def _check_memberships(run: Any, blockers: list) -> None:
    """The run needs employees, and each needs a salary config and bank data."""
    from payroll.models import PayrollRunEntry

    memberships = list(
        PayrollRunEntry.objects.filter(payroll_run=run)
        .select_related("payroll_entry", "payroll_entry__pays")
        .order_by("pk")
    )
    if not memberships:
        blockers.append(
            Blocker(
                code="no_employees",
                message="The payroll run has no employees in it.",
                resolution="Add the employees to be paid before review.",
            )
        )
        return

    seen = set()
    for membership in memberships:
        entry = membership.payroll_entry
        employee = entry.pays
        if employee is None:
            continue
        if employee.pk in seen:
            continue
        seen.add(employee.pk)

        if not employee.employee_pay_id:
            blockers.append(
                Blocker(
                    code="missing_salary_config",
                    message=(
                        f"{employee} has no salary configuration, so no net "
                        "pay can be computed."
                    ),
                    resolution="Attach a salary config to the employee.",
                    employee_id=employee.pk,
                )
            )
        if not employee.bank_account_number or not employee.bank:
            blockers.append(
                Blocker(
                    code="missing_bank_details",
                    message=(
                        f"{employee} is missing a bank account or supported "
                        "bank, so the NIP payment file cannot include them."
                    ),
                    resolution="Record the employee's bank and account number.",
                    employee_id=employee.pk,
                )
            )
        if entry.netpay is not None and entry.netpay < 0:
            blockers.append(
                Blocker(
                    code="negative_net_pay",
                    message=f"{employee} has a negative net pay for this run.",
                    resolution="Review the employee's deductions and allowances.",
                    employee_id=employee.pk,
                )
            )


def _check_timesheet_approval(
    run: Any, period: Optional[date], blockers: list
) -> None:
    """When the timesheet gate is on, raw clock hours must be certified first.

    ``CompanyPayrollSetting.require_timesheet_approval`` (P2-14) turns every
    unapproved hour in the period into a blocker so a checker cannot sign off
    a run whose attendance has not been reviewed. Employees with no clocked
    attendance in the period never block — there is nothing to certify.
    """
    if period is None:
        return
    from payroll.models import CompanyPayrollSetting, PayrollRunEntry
    from payroll.services.timesheet_service import unapproved_hours_in_period

    setting = CompanyPayrollSetting.objects.filter(company=run.company).first()
    if setting is None or not setting.require_timesheet_approval:
        return

    # The period window is the calendar month containing the payday.
    period_start = date(period.year, period.month, 1)
    last_day = calendar.monthrange(period.year, period.month)[1]
    period_end = date(period.year, period.month, last_day)

    employees = list(
        PayrollRunEntry.objects.filter(payroll_run=run)
        .values_list("payroll_entry__pays", flat=True)
        .distinct()
    )
    for employee_id in employees:
        if not employee_id:
            continue
        from payroll.models import EmployeeProfile

        employee = EmployeeProfile._base_manager.filter(pk=employee_id).first()
        if employee is None:
            continue
        hours = unapproved_hours_in_period(
            employee=employee, period_start=period_start, period_end=period_end
        )
        if hours > 0:
            blockers.append(
                Blocker(
                    code="unapproved_timesheets",
                    message=(
                        f"{employee} has {hours} attendance hours in the period "
                        "that are not covered by an approved timesheet."
                    ),
                    resolution=(
                        "Submit and approve the employee's weekly timesheets "
                        "for the period, or turn off the timesheet approval "
                        "requirement for the company."
                    ),
                    employee_id=employee.pk,
                )
            )


def _check_prior_period(run: Any, period: Optional[date], blockers: list) -> None:
    """The immediately preceding run must be locked/paid before a new one opens."""
    from payroll.models import PayrollRun

    if period is None or not run.company_id:
        return
    # Previous calendar month.
    if period.month == 1:
        prev_year, prev_month = period.year - 1, 12
    else:
        prev_year, prev_month = period.year, period.month - 1
    prior = (
        PayrollRun.objects.filter(
            company=run.company,
            paydays__year=prev_year,
            paydays__month=prev_month,
        )
        .order_by("-pk")
        .first()
    )
    if prior is None:
        return
    if not prior.is_locked:
        blockers.append(
            Blocker(
                code="prior_period_unlocked",
                message=(
                    f"The prior payroll run ({prior.paydays}) is still "
                    f"{prior.status}, not locked or paid."
                ),
                resolution="Close the prior payroll run before reviewing this one.",
                period=str(prior.paydays),
            )
        )


def _check_prior_remittances(run: Any, period: Optional[date], blockers: list) -> None:
    """Statutory remittances for periods before this one should be settled."""
    from payroll.models import RemittanceRecord

    if period is None or not run.company_id:
        return
    overdue = (
        RemittanceRecord.objects.filter(
            company=run.company,
            obligation__in=MONTHLY_OBLIGATIONS,
            remitted_on__isnull=True,
        )
        .exclude(period=period)
        .order_by("period")
    )
    # Only flag rows whose period is actually earlier than this run.
    for record in overdue:
        record_period = _as_date(record.period)
        if record_period is None or record_period >= period:
            continue
        blockers.append(
            Blocker(
                code="unresolved_remittance",
                message=(
                    f"{record.get_obligation_display()} for {record.period} "
                    "has not been remitted."
                ),
                resolution="Remit or record the outstanding statutory obligation.",
                obligation=record.obligation,
                period=str(record.period),
            )
        )


def run_preflight(run: Any, as_of: Optional[date] = None) -> PreflightReport:
    """Evaluate every readiness check for ``run`` and return the findings.

    Read-only and side-effect free. ``as_of`` is accepted for forward
    compatibility (deadline-sensitive checks) but the current checks are
    period-anchored.
    """
    blockers: list = []
    period = _check_period(run, blockers)
    _check_company_settings(run, blockers)
    _check_memberships(run, blockers)
    _check_timesheet_approval(run, period, blockers)
    _check_prior_period(run, period, blockers)
    _check_prior_remittances(run, period, blockers)
    return PreflightReport(blockers=blockers)
