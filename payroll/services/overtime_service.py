from __future__ import annotations
from typing import Any, Optional
from decimal import Decimal
from django.utils import timezone
from django.db import transaction


def calculate_overtime_for_attendance(*, attendance: Any) -> Optional[Any]:
    from payroll.models.workforce import OvertimePolicy, OvertimeEntry
    from datetime import datetime, date as date_type

    policy = OvertimePolicy.objects.filter(
        company=attendance.company, is_active=True
    ).first()
    if not policy:
        return None

    normal_hours = float(policy.daily_threshold_hours)
    worked = float(attendance.hours_worked or 0)
    if worked <= normal_hours:
        return None

    overtime_hours = Decimal(str(round(worked - normal_hours, 2)))
    max_ot = policy.max_daily_overtime_hours
    if overtime_hours > max_ot:
        overtime_hours = max_ot

    work_date = attendance.work_date
    if isinstance(work_date, str):
        work_date = datetime.strptime(work_date, "%Y-%m-%d").date()
    day = work_date.weekday()
    if day >= 5:
        rate = policy.weekend_rate_multiplier
    else:
        rate = policy.weekday_rate_multiplier

    entry = OvertimeEntry.objects.create(
        company=attendance.company,
        employee=attendance.employee,
        attendance=attendance,
        date=attendance.work_date,
        hours=overtime_hours,
        rate_multiplier=rate,
        status="APPROVED" if not policy.requires_approval else "PENDING",
    )
    return entry


def approve_overtime(*, entry: Any, approved_by: Any) -> Any:
    entry.status = "APPROVED"
    entry.approved_by = approved_by
    entry.approved_at = timezone.now()
    entry.save(update_fields=["status", "approved_by", "approved_at"])
    return entry


def reject_overtime(*, entry: Any, approved_by: Any) -> Any:
    entry.status = "REJECTED"
    entry.approved_by = approved_by
    entry.approved_at = timezone.now()
    entry.save(update_fields=["status", "approved_by", "approved_at"])
    return entry


def get_overtime_allowance(
    employee: Any, pay_period_start: Any, pay_period_end: Any
) -> Decimal:
    from payroll.models.workforce import OvertimeEntry

    entries = OvertimeEntry.objects.filter(
        employee=employee,
        status="APPROVED",
        date__range=(pay_period_start, pay_period_end),
    )
    total_ot_hours = sum(
        float(e.hours) * float(e.rate_multiplier) for e in entries
    )
    if total_ot_hours <= 0:
        return Decimal("0.00")
    hourly_rate = employee.employee_pay.basic / Decimal("176")
    return (Decimal(str(total_ot_hours)) * hourly_rate).quantize(Decimal("0.01"))
