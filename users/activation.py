"""Email proof completes a new registration; it does not grant employment access."""
from django.apps import apps


def can_activate_registration(user):
    if (
        user is None
        or user.is_active
        or not user.registration_pending
        or user.last_login is not None
        or user.is_staff
        or user.is_superuser
    ):
        return False
    employee = getattr(user, "employee_user", None)
    if employee is not None:
        if employee.deleted_at is not None or employee.status != "pending":
            return False
        checklist = apps.get_model("payroll", "OffboardingChecklist")
        if checklist.all_objects.filter(employee=employee, status="COMPLETED").exists():
            return False
    sanction = apps.get_model("accounting", "DisciplinarySanction")
    return not sanction.objects.filter(
        case__respondent=user, sanction_type="TERMINATION", status="ACTIVE"
    ).exists()
