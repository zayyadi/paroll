from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models import QuerySet

ESCALATION_AFTER_HOURS: int = getattr(settings, "APPROVAL_ESCALATION_HOURS", 48)


def get_pending_requests_for_escalation() -> list[dict]:
    """Find leave/IOU requests that have been pending beyond the escalation window."""
    from payroll.models import LeaveRequest, IOU

    threshold = timezone.now() - timedelta(hours=ESCALATION_AFTER_HOURS)
    escalatable: list[dict] = []

    for leave in LeaveRequest.objects.filter(
        status="PENDING", created_at__lte=threshold
    ).select_related("employee__user"):
        if not leave.approvals.filter(is_escalated=True).exists():
            escalatable.append({
                "type": "leave",
                "id": leave.pk,
                "employee": leave.employee,
                "created_at": leave.created_at,
            })

    for iou in IOU.objects.filter(
        status="PENDING", created_at__lte=threshold
    ).select_related("employee_id__user"):
        if not iou.approvals.filter(is_escalated=True).exists():
            escalatable.append({
                "type": "iou",
                "id": iou.pk,
                "employee": iou.employee_id,
                "created_at": iou.created_at,
            })

    return escalatable
