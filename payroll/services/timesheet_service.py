"""Weekly timesheet approval gate (P2-14).

BambooHR time tracking keeps raw clock data and *approved* hours apart: an
``AttendanceRecord`` is evidence that someone clocked in, but only hours an
employee has certified on a timesheet and a manager has approved should reach
gross pay. This module is that gate.

Two invariants hold the design together:

1. ``Timesheet.is_payable`` is the single test for whether hours count. The
   payroll pre-flight check and the attendance-to-gross wiring both read it,
   so raw clock data can never slip into pay through a side door.
2. The approval goes through the shared ``ApprovalRequest`` machinery rather
   than a bespoke status flip, so a timesheet carries the same audit trail and
   policy stages as leave, IOU and overtime approvals.

The week is Monday-anchored and the timesheet is unique per (employee, week),
so re-submitting an existing week updates it instead of forking a second
review of the same hours.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from payroll.models import AttendanceRecord, Timesheet

__all__ = [
    "week_start_for",
    "seed_timesheet_from_attendance",
    "get_or_create_timesheet",
    "submit_timesheet",
    "cancel_timesheet",
    "unapproved_hours_in_period",
]


def week_start_for(day: date) -> date:
    """Monday of the ISO week containing ``day``.

    Timesheets are week-scoped; anchoring to Monday keeps a week's hours in one
    reviewable container regardless of which day the work happened.
    """
    return day - timedelta(days=day.weekday())


def _attendance_hours(employee: Any, week_start: date, week_end: date) -> Decimal:
    """Sum of clocked hours for the week, excluding rows on leave.

    Leave hours are already tracked (and paid) through the leave ledger, so
    including them here would double-count them as worked time.
    """
    rows = AttendanceRecord.objects.filter(
        employee=employee,
        work_date__gte=week_start,
        work_date__lte=week_end,
    ).exclude(status=AttendanceRecord.Status.LEAVE)
    return sum(
        ((row.hours_worked or Decimal("0")) for row in rows), Decimal("0")
    )


def seed_timesheet_from_attendance(
    *, employee: Any, week_start: date, total_hours: Decimal | None = None
) -> Timesheet:
    """Build a draft timesheet for the employee's week.

    ``total_hours`` defaults to the sum of clocked attendance hours; pass an
    explicit value when the employee is correcting a missed clock-out. The
    timesheet starts as a draft, so nothing is payable yet.
    """
    week_start = week_start_for(week_start)
    week_end = week_start + timedelta(days=6)
    hours = (
        total_hours
        if total_hours is not None
        else _attendance_hours(employee, week_start, week_end)
    )
    timesheet, _created = Timesheet.objects.get_or_create(
        employee=employee,
        week_start=week_start,
        defaults={
            "company": employee.company,
            "total_hours": hours,
        },
    )
    return timesheet


def get_or_create_timesheet(*, employee: Any, week_start: date) -> Timesheet:
    """Fetch the employee's timesheet for the week, seeding it if absent.

    An approved or submitted timesheet is returned as-is so a caller cannot
    silently re-seed (and thereby un-certify) hours that already went through
    review.
    """
    week_start = week_start_for(week_start)
    existing = Timesheet.objects.filter(
        employee=employee, week_start=week_start
    ).first()
    if existing is not None:
        return existing
    return seed_timesheet_from_attendance(employee=employee, week_start=week_start)


@transaction.atomic
def submit_timesheet(*, timesheet: Timesheet, actor: Any) -> "ApprovalRequest":
    """Submit a draft timesheet for manager approval.

    Submission routes through the shared approval machinery (the
    ``timesheet.approve`` action), so the request carries the same policy
    stages, audit trail and company scoping as every other HR approval.
    A submitted timesheet must be withdrawn before it can be edited or
    submitted again.
    """
    from approvals.services import submit_approval

    from approvals.permissions import user_in_company
    Timesheet.objects.select_for_update().get(pk=timesheet.pk)
    timesheet.refresh_from_db()
    if actor.pk != timesheet.employee.user_id or not user_in_company(actor, timesheet.company):
        raise ValidationError("Only the employee can submit their own timesheet.")
    timesheet.full_clean()
    if timesheet.status not in (Timesheet.Status.DRAFT, Timesheet.Status.REJECTED):
        raise ValidationError(
            "Only a draft or rejected timesheet can be submitted."
        )
    if timesheet.total_hours is None or timesheet.total_hours <= 0:
        raise ValidationError("A timesheet needs hours before it can be submitted.")

    timesheet.status = Timesheet.Status.SUBMITTED
    timesheet.submitted_by = actor
    timesheet.submitted_at = timezone.now()
    timesheet.save(update_fields=["status", "submitted_by", "submitted_at"])

    request = submit_approval(
        source=timesheet, action="timesheet.approve", requester=actor
    )
    timesheet.approval_request = request
    timesheet.save(update_fields=["approval_request"])
    return request


@transaction.atomic
def cancel_timesheet(*, timesheet: Timesheet, actor: Any) -> Timesheet:
    """Withdraw a submitted-but-not-yet-approved timesheet back to draft."""
    from approvals.services import cancel_approval
    Timesheet.objects.select_for_update().get(pk=timesheet.pk)
    timesheet.refresh_from_db()
    if actor.pk != timesheet.employee.user_id:
        raise ValidationError("Only the employee can withdraw their timesheet.")
    if timesheet.status != Timesheet.Status.SUBMITTED:
        raise ValidationError("Only a submitted timesheet can be withdrawn.")
    cancel_approval(approval=timesheet.approval_request, actor=actor, reason="Employee withdrew timesheet.")
    timesheet.status = Timesheet.Status.DRAFT
    timesheet.save(update_fields=["status"])
    return timesheet


def unapproved_hours_in_period(
    *, employee: Any, period_start: date, period_end: date
) -> Decimal:
    """Hours in the period that are *not* covered by an approved timesheet.

    This is the figure the payroll pre-flight check reports when
    ``require_timesheet_approval`` is on: hours that exist as raw attendance
    but have not been certified. A zero return means every clocked hour in the
    period is covered by an approved timesheet.
    """
    week_start = week_start_for(period_start)
    week_end = period_end
    unapproved = Decimal("0")

    cursor = week_start
    while cursor <= week_end:
        sheet_end = cursor + timedelta(days=6)
        # Hours actually clocked in the overlap of [cursor, sheet_end] and the
        # period; exclude leave rows (not worked time).
        start = max(cursor, period_start)
        end = min(sheet_end, week_end)
        clocked = _attendance_hours(employee, start, end)

        sheet = Timesheet.objects.filter(
            employee=employee, week_start=cursor
        ).first()
        if sheet is not None and sheet.is_payable:
            # Approved for this week: nothing in it is unapproved.
            cursor = sheet_end + timedelta(days=1)
            continue

        # Not approved (missing, draft, submitted or rejected): the clocked
        # hours in the period overlap are unapproved.
        unapproved += clocked
        cursor = sheet_end + timedelta(days=1)

    return unapproved


def payable_week_starts(employee, period_start, period_end):
    """None means approval is optional; otherwise return certified weeks only.

    Fixed salary and absence deductions are not hourly earnings. This filter
    applies to overtime earnings, including manually entered overtime.
    """
    from payroll.models import CompanyPayrollSetting
    if not CompanyPayrollSetting.objects.filter(
        company=employee.company, require_timesheet_approval=True
    ).exists():
        return None
    return {
        sheet.week_start for sheet in Timesheet.objects.filter(
            company=employee.company, employee=employee,
            week_start__gte=week_start_for(period_start),
            week_start__lte=week_start_for(period_end),
        ) if sheet.is_payable
    }
