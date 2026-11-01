"""Project time booking and payroll cost allocation."""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet, Sum

from projects.models import Project, ProjectCostAllocation, Task, TimeEntry

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Time booking
# ---------------------------------------------------------------------------


def timesheet_is_editable(timesheet: Any) -> bool:
    """Project time can change only while the timesheet is a draft or rejected.

    Once submitted, approvers sign off the exact split they reviewed.
    """
    return timesheet.status in (timesheet.Status.DRAFT, timesheet.Status.REJECTED)


def booked_hours(timesheet: Any) -> Decimal:
    return timesheet.project_time.aggregate(total=Sum("hours"))["total"] or ZERO


def _lock_owned_timesheet(actor: Any, timesheet: Any) -> Any:
    from payroll.models import Timesheet

    sheet = Timesheet.objects.select_for_update().get(pk=timesheet.pk)
    if sheet.employee.user_id != actor.pk:
        raise PermissionDenied("Only the employee can book time on their timesheet.")
    if not timesheet_is_editable(sheet):
        raise ValidationError("Project time can only change on a draft or rejected timesheet.")
    return sheet


@transaction.atomic
def add_time_entry(
    *,
    actor: Any,
    timesheet: Any,
    project: Project,
    hours: Decimal,
    task: Task | None = None,
    note: str = "",
) -> TimeEntry:
    sheet = _lock_owned_timesheet(actor, timesheet)
    if project.company_id != sheet.company_id:
        raise ValidationError("Select a project in your company.")
    if not project.is_open:
        raise ValidationError(f"{project.code} is {project.get_status_display().lower()}; time cannot be booked to it.")
    hours = Decimal(hours)
    if booked_hours(sheet) + hours > sheet.total_hours:
        raise ValidationError(
            f"Project time cannot exceed the timesheet's {sheet.total_hours} hours."
        )
    entry = TimeEntry(timesheet=sheet, project=project, task=task, hours=hours, note=note)
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def remove_time_entry(*, actor: Any, entry: TimeEntry) -> None:
    _lock_owned_timesheet(actor, entry.timesheet)
    entry.delete()


def validate_project_time(timesheet: Any) -> None:
    """Called when a timesheet is submitted: bookings must fit its total."""
    if booked_hours(timesheet) > timesheet.total_hours:
        raise ValidationError(
            "Project time booked on this timesheet exceeds its total hours; "
            "remove some project time or raise the total."
        )


# ---------------------------------------------------------------------------
# Cost allocation
# ---------------------------------------------------------------------------


def run_period(run: Any) -> tuple[date, date]:
    """First and last day of the payroll run's month."""
    paydays = run.paydays
    start = date(paydays.year, paydays.month, 1)
    return start, date(paydays.year, paydays.month, monthrange(paydays.year, paydays.month)[1])


def _approved_timesheets(employee: Any, start: date, end: date) -> QuerySet:
    """Approved weeks counted in the period: those starting in the period's weeks.

    Matches ``payroll.services.timesheet_service.payable_week_starts``.
    """
    from payroll.models import Timesheet
    from payroll.services.timesheet_service import week_start_for

    return Timesheet.objects.filter(
        employee=employee,
        status=Timesheet.Status.APPROVED,
        week_start__gte=week_start_for(start),
        week_start__lte=week_start_for(end),
    )


def employee_run_cost(payroll_entry: Any) -> Decimal:
    """Employer cost of one employee for the run: monthly employer cost
    (gross plus employer pension, NHIA, NSITF, ITF) plus the period's allowances."""
    return (payroll_entry.figures["employer_cost"] + payroll_entry.calc_allowance).quantize(CENTS)


@transaction.atomic
def allocate_run_costs(run: Any) -> list[ProjectCostAllocation]:
    """(Re)build the run's project cost allocations. Safe to run repeatedly."""
    from payroll.models import PayrollRun

    run = PayrollRun.all_objects.select_for_update().get(pk=run.pk)
    ProjectCostAllocation.objects.filter(payroll_run=run).delete()
    start, end = run_period(run)
    created = []
    run_entries = run.payroll_run_entries.select_related(
        "payroll_entry", "payroll_entry__pays"
    )
    for run_entry in run_entries:
        payroll_entry = run_entry.payroll_entry
        employee = payroll_entry.pays
        sheets = _approved_timesheets(employee, start, end)
        employee_hours = sheets.aggregate(total=Sum("total_hours"))["total"] or ZERO
        if employee_hours <= 0:
            continue
        project_hours: dict[int, Decimal] = defaultdict(lambda: ZERO)
        for entry in TimeEntry.objects.filter(timesheet__in=sheets):
            project_hours[entry.project_id] += entry.hours
        if not project_hours:
            continue
        cost = employee_run_cost(payroll_entry)
        for project_id, hours in sorted(project_hours.items()):
            created.append(
                ProjectCostAllocation.objects.create(
                    company_id=run.company_id,
                    payroll_run=run,
                    project_id=project_id,
                    employee=employee,
                    hours=hours,
                    employee_hours=employee_hours,
                    employee_cost=cost,
                    amount=(cost * hours / employee_hours).quantize(CENTS),
                )
            )
    return created


def run_cost_summary(run: Any) -> dict:
    """Totals for the run: allocated per project, total employer cost, overhead."""
    allocations = list(
        ProjectCostAllocation.objects.filter(payroll_run=run).select_related("project", "employee")
    )
    by_project: dict[int, dict] = {}
    for row in allocations:
        bucket = by_project.setdefault(
            row.project_id, {"project": row.project, "hours": ZERO, "amount": ZERO, "rows": []}
        )
        bucket["hours"] += row.hours
        bucket["amount"] += row.amount
        bucket["rows"].append(row)
    total_cost = sum(
        (employee_run_cost(run_entry.payroll_entry) for run_entry in run.payroll_run_entries.select_related("payroll_entry")),
        ZERO,
    )
    allocated = sum((row.amount for row in allocations), ZERO)
    return {
        "projects": sorted(by_project.values(), key=lambda b: b["project"].code),
        "allocated": allocated,
        "total_cost": total_cost,
        "unallocated": total_cost - allocated,
        "has_allocations": bool(allocations),
    }


def project_summary(project: Project) -> dict:
    """Approved hours, cost to date and budget use for one project."""
    from payroll.models import Timesheet

    approved = project.time_entries.filter(timesheet__status=Timesheet.Status.APPROVED)
    hours = approved.aggregate(total=Sum("hours"))["total"] or ZERO
    pending = (
        project.time_entries.exclude(timesheet__status=Timesheet.Status.APPROVED).aggregate(
            total=Sum("hours")
        )["total"]
        or ZERO
    )
    cost = project.cost_allocations.aggregate(total=Sum("amount"))["total"] or ZERO
    hours_by_employee = (
        approved.values("timesheet__employee__first_name", "timesheet__employee__last_name")
        .annotate(total=Sum("hours"))
        .order_by("-total")
    )
    budget_used = None
    if project.budget:
        budget_used = (cost / project.budget * 100).quantize(Decimal("0.1"))
    return {
        "approved_hours": hours,
        "pending_hours": pending,
        "cost": cost,
        "budget_remaining": (project.budget - cost) if project.budget is not None else None,
        "budget_used_percent": budget_used,
        "hours_by_employee": hours_by_employee,
    }
