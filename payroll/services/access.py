"""Row-level access control for HR views.

Provides scoping helpers so regular employees see only their own data,
managers see their team/department, and HR/superusers see everything.
"""

from __future__ import annotations

from typing import Any, Optional

from django.db.models import Q, QuerySet

from company.utils import get_user_company


def _employee_of(user: Any) -> Optional["EmployeeProfile"]:  # noqa: F821
    """Resolve the EmployeeProfile (if any) linked to *user*."""
    return getattr(user, "employee_user", None)


def visible_employee_profiles_for(user: Any) -> QuerySet:
    """Employee profiles the *user* is allowed to see.

    - Superusers / ``view_all_employeeprofile`` holders → all company employees.
    - Managers → themselves + same-department colleagues.
    - Regular employees → only their own profile.
    - Unauthenticated → empty queryset.
    """
    from payroll.models import EmployeeProfile

    company = get_user_company(user)
    qs = EmployeeProfile.objects.select_related("user", "department").filter(
        company=company
    )
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser or user.has_perm("payroll.view_all_employeeprofile"):
        return qs

    employee = _employee_of(user)
    if employee is None:
        return qs.none()

    if getattr(user, "is_manager", False):
        visibility = Q(pk=employee.pk)
        if employee.department_id:
            visibility |= Q(department_id=employee.department_id)
        return qs.filter(visibility)

    return qs.filter(pk=employee.pk)


def visible_documents_for(user: Any) -> QuerySet:
    """Documents the *user* is allowed to see."""
    from payroll.models import EmployeeDocument

    company = get_user_company(user)
    qs = EmployeeDocument.objects.filter(company=company).select_related(
        "employee", "employee__user"
    )
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser or user.has_perm("payroll.view_all_employeeprofile"):
        return qs

    employee = _employee_of(user)
    if employee is None:
        return qs.none()

    if getattr(user, "is_manager", False):
        return qs.filter(
            Q(employee=employee)
            | Q(employee__department_id=employee.department_id)
        )
    return qs.filter(employee=employee)


def visible_assets_for(user: Any) -> QuerySet:
    """Assets the *user* is allowed to see."""
    from payroll.models import EmployeeAsset

    company = get_user_company(user)
    qs = EmployeeAsset.objects.filter(company=company).select_related(
        "employee", "category"
    )
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser or user.has_perm("payroll.view_all_employeeprofile"):
        return qs

    employee = _employee_of(user)
    if employee is None:
        return qs.none()

    if getattr(user, "is_manager", False):
        return qs.filter(
            Q(employee=employee)
            | Q(employee__department_id=employee.department_id)
        )
    return qs.filter(employee=employee)


def visible_attendance_for(user: Any) -> QuerySet:
    """Attendance records the *user* is allowed to see."""
    from payroll.models import AttendanceRecord

    company = get_user_company(user)
    qs = AttendanceRecord.objects.filter(company=company).select_related(
        "employee", "employee__user"
    )
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser or user.has_perm("payroll.view_all_employeeprofile"):
        return qs

    employee = _employee_of(user)
    if employee is None:
        return qs.none()

    if getattr(user, "is_manager", False):
        return qs.filter(
            Q(employee=employee)
            | Q(employee__department_id=employee.department_id)
        )
    return qs.filter(employee=employee)


def visible_goals_for(user: Any) -> QuerySet:
    """Performance goals the *user* is allowed to see."""
    from payroll.models import Goal

    company = get_user_company(user)
    qs = Goal.objects.filter(company=company).select_related(
        "employee", "manager"
    )
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser or user.has_perm("payroll.view_all_employeeprofile"):
        return qs

    employee = _employee_of(user)
    if employee is None:
        return qs.none()

    if getattr(user, "is_manager", False):
        return qs.filter(
            Q(employee=employee)
            | Q(employee__department_id=employee.department_id)
        )
    return qs.filter(employee=employee)
