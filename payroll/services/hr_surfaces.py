"""Shared company-scoped access for the HR product surfaces."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from company.utils import get_user_company
from approvals.permissions import user_in_company, has_company_permission
from payroll import models

RESOURCES = {
    "exit-settlements": (models.ExitSettlement, "company"),
    "leave-ledger": (models.LeaveLedgerEntry, "employee__company"),
    "retro-pay-deltas": (models.RetroPayDelta, "employee__company"),
    "comp-reviews": (models.CompReview, "cycle__company"),
    "salary-bands": (models.SalaryBand, "company"),
}


def active_company(user):
    company = get_user_company(user)
    if not user_in_company(user, company):
        raise PermissionDenied("Select a company you belong to.")
    return company


def require_permission(user, company, permission):
    if not has_company_permission(user, company, permission):
        raise PermissionDenied("You do not have permission for this company resource.")


def timesheets_for(user):
    company = active_company(user)
    rows = models.Timesheet.objects.filter(company=company, employee__company=company)
    if not (has_company_permission(user, company, "payroll.view_timesheet") or
            has_company_permission(user, company, "payroll.change_timesheet")):
        rows = rows.filter(employee__user=user)
    return rows.select_related("employee", "approval_request")


@transaction.atomic
def save_timesheet(*, actor, week_start=None, total_hours=None, notes="", pk=None):
    from payroll.services.timesheet_service import get_or_create_timesheet
    company = active_company(actor)
    if pk:
        sheet = timesheets_for(actor).select_for_update().get(pk=pk)
    else:
        employee = models.EmployeeProfile.objects.get(user=actor, company=company)
        sheet = get_or_create_timesheet(employee=employee, week_start=week_start)
        sheet = models.Timesheet.objects.select_for_update().get(pk=sheet.pk)
    if sheet.employee.user_id != actor.pk:
        raise PermissionDenied("Only the employee can edit their timesheet.")
    if sheet.status not in (sheet.Status.DRAFT, sheet.Status.REJECTED):
        raise ValidationError("Only draft or rejected timesheets can be edited.")
    if total_hours is not None:
        sheet.total_hours = total_hours
    sheet.notes = notes
    sheet.full_clean()
    sheet.save(update_fields=["total_hours", "notes"])
    return sheet
