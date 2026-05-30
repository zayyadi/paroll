from django.db.models import Q

from company.utils import get_user_company
from payroll.models import EmployeeProfile


def visible_employee_profiles_for(user):
    company = get_user_company(user)
    qs = EmployeeProfile.objects.select_related("user", "department").filter(company=company)
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser or user.has_perm("payroll.view_all_employeeprofile"):
        return qs

    employee = getattr(user, "employee_user", None)
    if employee is None:
        return qs.none()

    if getattr(user, "is_manager", False):
        visibility = Q(pk=employee.pk)
        if employee.department_id:
            visibility |= Q(department_id=employee.department_id)
        return qs.filter(visibility)

    return qs.filter(pk=employee.pk)
