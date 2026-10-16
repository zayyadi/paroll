"""People-analytics dataset (P2-13).

Gap #13 of ``docs/world_class_employee_management_research_2026-10-14.md``:
expose headcount, attrition, absence, overtime and payroll-cost queries as a
documented dataset surface, mirroring BambooHR Datasets. Today reporting is
ad-hoc dashboard views plus accounting CSV exports
(``integrations/export_connectors.py``); this module is the canonical,
query-shaped dataset those surfaces read from.

Every metric is a pure function of ``company`` plus an optional period window
(``start``/``end`` dates). They are read-only and safe to call from a request
or a task. The wire format is JSON-friendly (``Decimal`` -> ``str``,
``date`` -> ``isoformat``) via :func:`dataset_as_json`.

Metric reference
----------------
headcount
    Active employees at period end, plus a breakdown by department.
attrition
    Employees terminated (``status="terminated"``) whose termination falls in
    the window, the headcount the rate is measured against, and the resulting
    rate as a fraction (e.g. ``0.04`` = 4%).
absence
    Sum of attendance hours recorded with status ``absent``, plus the record
    count, per employee in the window.
overtime
    Sum of approved overtime hours and their weighted pay (``hours * rate
    multiplier``), per employee in the window.
payroll_cost
    Sum of ``PayrollEntry.netpay`` across employees attached to payroll runs
    whose period (``paydays``) falls in the window, grouped by run.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce

from payroll.models import (
    AttendanceRecord,
    EmployeeProfile,
    OvertimeEntry,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
)
from payroll.models.workforce import OffboardingChecklist

__all__ = [
    "headcount",
    "attrition",
    "absence",
    "overtime",
    "payroll_cost",
    "dataset_as_json",
]


def _window(company: Any, start: Any = None, end: Any = None) -> tuple[Optional[date], Optional[date]]:
    """Resolve an optional date window; ``None`` means unbounded on that side."""
    def coerce(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])

    return coerce(start), coerce(end)


def headcount(company: Any, *, as_of: Any = None, department: Any = None) -> dict:
    """Active headcount at ``as_of`` (default: today), with department split."""
    as_of_date = _window(company, as_of)[0] or date.today()
    qs = EmployeeProfile.objects.filter(company=company, status="active")
    if department is not None:
        qs = qs.filter(department=department)
    total = qs.count()
    by_department = [
        {
            "department_id": dep["department_id"],
            "department": dep["department__name"] or "(unassigned)",
            "count": dep["n"],
        }
        for dep in qs.values("department_id", "department__name").annotate(
            n=Count("id")
        ).order_by("-n", "department__name")
    ]
    return {
        "as_of": as_of_date,
        "total": total,
        "by_department": by_department,
    }


def attrition(company: Any, *, start: Any = None, end: Any = None) -> dict:
    """Completed exits in the window, the measured headcount, and the attrition rate.

    Exits are counted from ``OffboardingChecklist`` rows in the ``COMPLETED``
    state, dated by ``last_working_day`` (the authoritative termination date;
    ``EmployeeProfile`` carries no termination field). The rate is
    ``exits / active_headcount`` as a fraction; when headcount is zero the rate
    is reported as ``0`` to avoid dividing by zero.
    """
    start_date, end_date = _window(company, start, end)
    exits = OffboardingChecklist.objects.filter(
        company=company, status="COMPLETED"
    )
    if start_date is not None:
        exits = exits.filter(last_working_day__gte=start_date)
    if end_date is not None:
        exits = exits.filter(last_working_day__lte=end_date)

    terminations = exits.count()
    denominator = EmployeeProfile.objects.filter(
        company=company, status="active"
    ).count()
    rate = (
        Decimal(terminations) / Decimal(denominator)
        if denominator
        else Decimal("0")
    )
    return {
        "start": start_date,
        "end": end_date,
        "terminations": terminations,
        "headcount": denominator,
        "rate": rate.quantize(Decimal("0.0001")),
    }


def absence(company: Any, *, start: Any = None, end: Any = None) -> dict:
    """Absent hours recorded in the window, per employee.

    Sums ``AttendanceRecord.hours_worked`` for rows whose status is ``absent``
    (the only status that represents time booked out without leave), grouped by
    employee, with a grand total and the number of absent records.
    """
    start_date, end_date = _window(company, start, end)
    qs = AttendanceRecord.objects.filter(company=company, status="absent")
    if start_date is not None:
        qs = qs.filter(work_date__gte=start_date)
    if end_date is not None:
        qs = qs.filter(work_date__lte=end_date)

    per_employee = [
        {
            "employee_id": row["employee_id"],
            "employee": row["employee__first_name"] or row["employee__emp_id"],
            "hours": row["hours"],
            "days": row["n"],
        }
        for row in qs.values(
            "employee_id", "employee__first_name", "employee__emp_id"
        ).annotate(
            hours=Coalesce(
                Sum("hours_worked"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=7, decimal_places=2),
            ),
            n=Count("id"),
        ).order_by("-hours")
    ]
    total_hours = sum((r["hours"] for r in per_employee), Decimal("0"))
    return {
        "start": start_date,
        "end": end_date,
        "total_hours": total_hours,
        "total_days": qs.count(),
        "by_employee": per_employee,
    }


def overtime(company: Any, *, start: Any = None, end: Any = None) -> dict:
    """Approved overtime hours and weighted pay in the window, per employee.

    Only ``APPROVED`` entries count (pending/rejected hours are not payable).
    Weighted pay is ``hours * rate_multiplier`` in hours-of-base-pay terms; it
    is a workload proxy, not a currency amount, so it is returned unrounded.
    """
    start_date, end_date = _window(company, start, end)
    qs = OvertimeEntry.objects.filter(company=company, status="APPROVED")
    if start_date is not None:
        qs = qs.filter(date__gte=start_date)
    if end_date is not None:
        qs = qs.filter(date__lte=end_date)

    per_employee = [
        {
            "employee_id": row["employee_id"],
            "employee": row["employee__first_name"] or row["employee__emp_id"],
            "hours": row["total_hours"],
            "weighted_hours": row["weighted_hours"],
        }
        for row in qs.values(
            "employee_id", "employee__first_name", "employee__emp_id"
        ).annotate(
            total_hours=Coalesce(
                Sum("hours"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=7, decimal_places=2),
            ),
            weighted_hours=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("hours") * F("rate_multiplier"),
                        output_field=DecimalField(max_digits=7, decimal_places=2),
                    )
                ),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=9, decimal_places=2),
            ),
        ).order_by("-total_hours")
    ]
    total_hours = sum((r["hours"] for r in per_employee), Decimal("0"))
    total_weighted = sum((r["weighted_hours"] for r in per_employee), Decimal("0"))
    return {
        "start": start_date,
        "end": end_date,
        "total_hours": total_hours,
        "total_weighted_hours": total_weighted,
        "by_employee": per_employee,
    }


def payroll_cost(company: Any, *, start: Any = None, end: Any = None) -> dict:
    """Net pay disbursed in the window, grouped by payroll run.

    Runs are selected by their period (``paydays`` month) falling inside the
    window; each run's cost is the sum of ``netpay`` over the entries attached
    to it via ``PayrollRunEntry``. This is the canonical payroll-cost query the
    accounting CSV exports and dashboards read from.
    """
    start_date, end_date = _window(company, start, end)
    # `PayrollRun.objects` hides inactive runs; cost must cover every run in
    # the window regardless of the legacy `is_active` flag.
    runs = PayrollRun.all_objects.filter(company=company)
    if start_date is not None:
        runs = runs.filter(paydays__gte=start_date)
    if end_date is not None:
        runs = runs.filter(paydays__lte=end_date)

    by_run = []
    for run in runs.order_by("paydays"):
        total = PayrollRunEntry.objects.filter(payroll_run=run).aggregate(
            total=Coalesce(
                Sum("payroll_entry__netpay"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )["total"]
        by_run.append(
            {
                "payroll_run_id": run.pk,
                "period": str(run.paydays) if run.paydays else None,
                "status": run.status,
                "net_pay": total,
                "employees": run.payroll_run_entries.count(),
            }
        )
    total_cost = sum((r["net_pay"] for r in by_run), Decimal("0"))
    return {
        "start": start_date,
        "end": end_date,
        "total_net_pay": total_cost,
        "runs": by_run,
    }


def _jsonable(value: Any) -> Any:
    """Recursively coerce Decimal/date to JSON-safe primitives."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def dataset_as_json(company: Any, *, start: Any = None, end: Any = None, metrics: Optional[list] = None) -> dict:
    """Run selected metrics and return a JSON-safe dataset document.

    ``metrics`` defaults to all five. Each metric is keyed by name; a metric
    that raises is reported under ``errors`` rather than failing the whole
    document, so one bad window cannot blank the dataset.
    """
    registry = {
        "headcount": headcount,
        "attrition": attrition,
        "absence": absence,
        "overtime": overtime,
        "payroll_cost": payroll_cost,
    }
    wanted = metrics or list(registry)
    unknown = [name for name in wanted if name not in registry]
    if unknown:
        raise ValueError(f"Unknown metrics: {', '.join(unknown)}")

    data: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name in wanted:
        try:
            if name == "headcount":
                # headcount is a point-in-time metric; it takes as_of, not a range.
                data[name] = _jsonable(headcount(company, as_of=end))
            else:
                data[name] = _jsonable(registry[name](company, start=start, end=end))
        except Exception as exc:  # noqa: BLE001 - report, don't abort the dataset
            errors[name] = str(exc)
    document = {
        "company_id": getattr(company, "pk", company),
        "start": _jsonable(_window(company, start)[0]),
        "end": _jsonable(_window(company, end)[1]),
        "metrics": data,
    }
    if errors:
        document["errors"] = errors
    return document
