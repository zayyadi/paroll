"""Shared guards and entry points for consequential HR actions."""
from __future__ import annotations

from typing import Any, Iterable, TYPE_CHECKING
from django.db import transaction
from django.db.models import Model
from django.core.exceptions import PermissionDenied, ValidationError

if TYPE_CHECKING:
    from approvals.models import ApprovalRequest

def guard_state(source: Model, action: str, protected: set[str], fields: tuple[str, ...] = (), update_fields: Iterable[str] | None = None) -> None:
    from approvals.services import execution_authorized
    previous = type(source).objects.filter(pk=source.pk).first() if source.pk else None
    status_written = update_fields is None or "status" in update_fields
    if update_fields is not None:
        fields = tuple(name for name in fields if name in update_fields or source._meta.get_field(name).name in update_fields)
    changed = status_written and (previous is None or previous.status != source.status)
    metadata_changed = (any(getattr(source, name) != getattr(previous, name) for name in fields)
                        if previous else any(getattr(source, name) is not None for name in fields))
    if (changed and (source.status in protected or (previous and previous.status in protected))) or metadata_changed:
        if not execution_authorized(source, action) and not _authorized_payroll_settlement(source, action):
            raise PermissionDenied("Use the approval workflow to change this decision or its terms.")

def require_execution(source: Model, action: str) -> None:
    from approvals.services import execution_authorized
    if not execution_authorized(source, action):
        raise PermissionDenied("An approved workflow execution is required.")

def decide(source: Model, action: str, actor: Any, decision: str = "APPROVE", comment: str = "", payload: dict[str, Any] | None = None) -> ApprovalRequest:
    from approvals.services import request_or_decide
    return request_or_decide(source=source, action=action, actor=actor,
                             decision=decision, comment=comment, payload=payload)

def decide_leave(*, leave: Model, actor: Any, decision: str = "APPROVE", comment: str = "") -> ApprovalRequest:
    return decide(leave, "leave.approve", actor, decision, comment)

@transaction.atomic
def decide_iou(*, iou: Model, actor: Any, decision: str = "APPROVE", comment: str = "", payload: dict[str, Any] | None = None) -> ApprovalRequest:
    if decision == "SETTLE":
        from approvals.models import ApprovalRequest
        from approvals.permissions import require_company_authority
        from approvals.services import submit_approval
        from django.contrib.contenttypes.models import ContentType
        require_company_authority(actor, iou.employee_id.company, "payroll.change_iou")
        pending = ApprovalRequest.objects.select_for_update().filter(
            company=iou.employee_id.company, action="iou.settle",
            content_type=ContentType.objects.get_for_model(iou), object_id=iou.pk,
            status="PENDING",
        ).first()
        if pending is None:
            return submit_approval(source=iou, action="iou.settle", requester=actor, payload=payload)
        return decide(iou, "iou.settle", actor, "APPROVE", comment, payload)
    return decide(iou, "iou.approve", actor, decision, comment, payload)


def _authorized_payroll_settlement(source: Model, action: str) -> bool:
    from approvals.services import current_execution
    from django.db.models import Q, Sum
    request = current_execution()
    if action != "iou.settle" or source._meta.model_name != "iou" or source.status != "PAID":
        return False
    if not request or request.action != "payroll.lock" or request.content_type.model != "payrollrun":
        return False
    if request.company_id != source.employee_id.company_id:
        return False
    if not source.deductions.filter(payday_id=request.object_id, employee_id=source.employee_id_id).exists():
        return False
    actual_paid = (source.deductions
        .filter(Q(payday__closed=True) | Q(payday__status__in=["locked", "paid"]))
        .aggregate(total=Sum("amount"))["total"] or 0)
    return actual_paid >= source.total_amount


def guard_delete(source: Model) -> None:
    from approvals.models import ApprovalRequest
    from django.contrib.contenttypes.models import ContentType
    if getattr(source, "status", "") in {"APPROVED", "COMPLETED", "PAID", "sent", "accepted"}:
        raise PermissionDenied("Reviewed business records must be retained for their audit history.")
    if source.pk and ApprovalRequest.objects.filter(content_type=ContentType.objects.get_for_model(source), object_id=source.pk).exists():
        raise PermissionDenied("A record with approval history cannot be deleted through ordinary CRUD.")


def guard_requester(source: Model, update_fields: Iterable[str] | None = None) -> None:
    if update_fields is not None and not {"requested_by", "requested_by_id"}.intersection(update_fields):
        return
    old = type(source).all_objects.filter(pk=source.pk).first() if source.pk else None
    if old and old.requested_by_id != source.requested_by_id:
        raise PermissionDenied("The original requester is immutable.")


def submit_hr_request(source: Model, requester: Any) -> ApprovalRequest:
    from approvals.services import submit_approval
    keys = {"leaverequest":"leave.approve", "iou":"iou.approve", "overtimeentry":"overtime.approve"}
    return submit_approval(source=source, action=keys[source._meta.model_name], requester=requester)
