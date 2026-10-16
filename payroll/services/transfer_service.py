from __future__ import annotations
from typing import Any
from decimal import Decimal
from django.utils import timezone
from django.db import transaction


def execute_transfer(*, transfer: Any, performed_by: Any) -> Any:
    from payroll.services.hr_workflow import require_execution
    from approvals.services import execution_authorized, authorize_approved_execution
    if not execution_authorized(transfer, "transfer.approve"):
        from approvals.models import ApprovalRequest
        from django.contrib.contenttypes.models import ContentType
        approval = ApprovalRequest.objects.filter(content_type=ContentType.objects.get_for_model(transfer),
            object_id=str(transfer.pk), action="transfer.approve", status="APPROVED").order_by("-pk").first()
        if not approval:
            raise ValueError("An approved request is required before execution.")
        with authorize_approved_execution(approval, performed_by):
            transfer.refresh_from_db()
            return execute_transfer(transfer=transfer, performed_by=performed_by)
    require_execution(transfer, "transfer.approve")
    if transfer.status != "APPROVED" or transfer.effective_date > timezone.localdate():
        raise ValueError("Only approved changes whose effective date is due can execute.")
    with transaction.atomic():
        employee = transfer.employee
        if transfer.to_department:
            employee.department = transfer.to_department
        if transfer.to_position:
            employee.job_title = transfer.to_position
        employee.save(update_fields=["department", "job_title"])
        transfer.status = "COMPLETED"
        transfer.approved_by = performed_by
        transfer.approved_at = timezone.now()
        transfer.save(update_fields=["status", "approved_by", "approved_at"])
    return transfer


def approve_transfer(*, transfer: Any, approved_by: Any, comment: str = "") -> Any:
    from payroll.services.hr_workflow import decide
    return decide(transfer, "transfer.approve", approved_by, "APPROVE", comment)


def reject_transfer(*, transfer: Any, approved_by: Any, comment: str = "") -> Any:
    from payroll.services.hr_workflow import decide
    return decide(transfer, "transfer.approve", approved_by, "REJECT", comment)


def execute_promotion(*, promotion: Any, performed_by: Any) -> Any:
    from payroll.services.hr_workflow import require_execution
    from approvals.services import execution_authorized, authorize_approved_execution
    if not execution_authorized(promotion, "promotion.approve"):
        from approvals.models import ApprovalRequest
        from django.contrib.contenttypes.models import ContentType
        approval = ApprovalRequest.objects.filter(content_type=ContentType.objects.get_for_model(promotion),
            object_id=str(promotion.pk), action="promotion.approve", status="APPROVED").order_by("-pk").first()
        if not approval:
            raise ValueError("An approved request is required before execution.")
        with authorize_approved_execution(approval, performed_by):
            promotion.refresh_from_db()
            return execute_promotion(promotion=promotion, performed_by=performed_by)
    require_execution(promotion, "promotion.approve")
    if promotion.status != "APPROVED" or promotion.effective_date > timezone.localdate():
        raise ValueError("Only approved changes whose effective date is due can execute.")
    with transaction.atomic():
        employee = promotion.employee
        employee.job_title = promotion.new_title
        if promotion.new_salary_config:
            employee.employee_pay = promotion.new_salary_config
        employee.save(update_fields=["job_title", "employee_pay"])
        promotion.status = "COMPLETED"
        promotion.approved_by = performed_by
        promotion.approved_at = timezone.now()
        promotion.save(update_fields=["status", "approved_by", "approved_at"])
    return promotion


def approve_promotion(*, promotion: Any, approved_by: Any, comment: str = "") -> Any:
    from payroll.services.hr_workflow import decide
    return decide(promotion, "promotion.approve", approved_by, "APPROVE", comment)


def reject_promotion(*, promotion: Any, approved_by: Any, comment: str = "") -> Any:
    from payroll.services.hr_workflow import decide
    return decide(promotion, "promotion.approve", approved_by, "REJECT", comment)
