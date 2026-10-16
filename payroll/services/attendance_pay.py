"""Attendance → payroll feed (P1-7).

Gap #7 of docs/world_class_employee_management_research_2026-10-14.md: approved
overtime and hours_worked/absent days must reach the payroll calculation path
(previously attendance was read only by views).

- Overtime is fed through ``PayrollEntry._get_auto_overtime_allowance`` which
  delegates to ``overtime_service.get_overtime_allowance``.
- Unpaid absence is fed through ``PayrollEntry.calc_absence_deduction`` which
  delegates here; it is opt-in per company (``deduct_unpaid_absence``).
  Absence deductions do not pay worked hours and therefore do not depend on
  timesheet certification. Overtime earnings apply the shared timesheet gate.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any


def absent_days_in(employee: Any, month_start: date, month_end: date) -> int:
    """Count attendance rows marked absent for the pay period."""
    from payroll.models.workforce import AttendanceRecord

    return AttendanceRecord.objects.filter(
        employee=employee,
        work_date__range=(month_start, month_end),
        status=AttendanceRecord.Status.ABSENT,
    ).count()


def absence_deduction_for(
    employee: Any, month_start: date, month_end: date
) -> Decimal:
    """Deduction for unpaid absence days in the pay period (0 when opted out).

    Respects the company opt-in flag and returns zero when the employee has no
    salary config or no absent days, so the caller can add it unconditionally.
    """
    from payroll.models import CompanyPayrollSetting
    from payroll.services.payroll_calc import absence_deduction

    company = getattr(employee, "company", None)
    setting = (
        CompanyPayrollSetting.objects.filter(company=company).first()
        if company
        else None
    )
    if setting is None or not setting.deduct_unpaid_absence:
        return Decimal("0.00")
    config = employee.employee_pay
    if config is None:
        return Decimal("0.00")
    days = absent_days_in(employee, month_start, month_end)
    if days <= 0:
        return Decimal("0.00")
    return absence_deduction(config.basic_salary, days)
