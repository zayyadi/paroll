"""Employment effects retain their approved cause and prior state."""
from __future__ import annotations
from typing import Any
from django.apps import apps
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from approvals.services import current_execution, authorize_approved_execution
from accounting.models import DisciplinarySanction, DisciplinaryCase


def apply_termination(sanction: DisciplinarySanction) -> None:
    if sanction.status != sanction.Status.ACTIVE or sanction.sanction_type != sanction.SanctionType.TERMINATION:
        return
    if sanction.effective_date > timezone.localdate():
        return
    execution = current_execution()
    if not execution or execution.action != "discipline.sanction" or execution.object_id != sanction.pk:
        return
    if sanction.employment_effect_snapshot:
        return
    respondent = sanction.case.respondent
    if respondent is None:
        return
    EmployeeProfile = apps.get_model("payroll", "EmployeeProfile")
    employee = EmployeeProfile.objects.filter(user=respondent, company=sanction.case.company).first()
    sanction.employment_effect_snapshot = {
        "user_id": respondent.pk, "user_was_active": respondent.is_active,
        "employee_id": employee.pk if employee else None,
        "employee_previous_status": employee.status if employee else None,
        "applied_at": timezone.now().isoformat(), "approval_id": execution.pk,
    }
    # Avoid re-entering sanction employment callbacks while persisting provenance.
    from accounting.models import BaseModel
    BaseModel.save(sanction, update_fields=["employment_effect_snapshot", "updated_at"])
    if respondent.is_active:
        respondent.is_active = False
        respondent.save(update_fields=["is_active"])
    if employee and employee.status != "terminated":
        employee.status = "terminated"
        employee.save(update_fields=["status"])


def execute_approved_sanction(*, sanction: DisciplinarySanction, actor: Any) -> None:
    from approvals.models import ApprovalRequest
    from django.contrib.contenttypes.models import ContentType
    approval = ApprovalRequest.objects.filter(action="discipline.sanction", content_type=ContentType.objects.get_for_model(sanction),
        object_id=sanction.pk, status="APPROVED").order_by("-pk").first()
    if approval is None:
        raise PermissionDenied("Approved sanction execution is required.")
    with authorize_approved_execution(approval, actor):
        sanction.refresh_from_db()
        apply_termination(sanction)


def revoke_sanctions_for_overturn(*, case: DisciplinaryCase, actor: Any) -> None:
    EmployeeProfile = apps.get_model("payroll", "EmployeeProfile")
    OffboardingChecklist = apps.get_model("payroll", "OffboardingChecklist")
    for sanction in case.sanctions.filter(status=DisciplinarySanction.Status.ACTIVE):
        snapshot = sanction.employment_effect_snapshot
        sanction.status = sanction.Status.REVOKED
        sanction.save(update_fields=["status", "updated_at"])
        if sanction.sanction_type != sanction.SanctionType.TERMINATION or not snapshot:
            continue
        respondent = case.respondent
        employee = EmployeeProfile.objects.filter(pk=snapshot.get("employee_id"), user=respondent).first()
        another = DisciplinarySanction.objects.filter(case__respondent=respondent, status=DisciplinarySanction.Status.ACTIVE,
            sanction_type=DisciplinarySanction.SanctionType.TERMINATION).exists()
        exited = employee and OffboardingChecklist.objects.filter(employee=employee, status="COMPLETED").exists()
        if another or exited or not employee or employee.status != "terminated":
            continue
        employee.status = snapshot.get("employee_previous_status") or "active"
        employee.save(update_fields=["status"])
        if snapshot.get("user_was_active") and not respondent.is_active:
            respondent.is_active = True
            respondent.save(update_fields=["is_active"])
