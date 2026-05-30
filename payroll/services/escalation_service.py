from datetime import timedelta

from django.utils import timezone
from django.conf import settings


ESCALATION_AFTER_HOURS = getattr(settings, "APPROVAL_ESCALATION_HOURS", 48)


def get_pending_requests_for_escalation():
    """Find leave/IOU requests that have been pending beyond the escalation window."""
    from payroll.models import LeaveRequest, IOU

    threshold = timezone.now() - timedelta(hours=ESCALATION_AFTER_HOURS)
    escalatable = []

    for leave in LeaveRequest.objects.filter(
        status="PENDING", created_at__lte=threshold
    ).select_related("employee__user"):
        if not leave.approvals.filter(is_escalated=True).exists():
            escalatable.append(("leave", leave))

    for iou in IOU.objects.filter(
        status="PENDING", created_at__lte=threshold
    ).select_related("employee__user"):
        if not hasattr(iou, "_escalation_sent"):
            escalatable.append(("iou", iou))

    return escalatable


def escalate_request(request_type, instance):
    """Escalate a pending request by notifying HR/superusers."""
    from django.contrib.auth import get_user_model
    from payroll.services.notification_service import NotificationService

    User = get_user_model()
    service = NotificationService()

    escalatable_users = User.objects.filter(
        is_superuser=True, is_active=True
    ) | User.objects.filter(
        groups__name="HR", is_active=True
    )
    escalatable_users = escalatable_users.distinct()

    for user in escalatable_users:
        if request_type == "leave":
            service.send_notification(
                recipient=user,
                notification_type="LEAVE_ESCALATED",
                priority="HIGH",
                context={
                    "employee": str(instance.employee),
                    "leave_type": instance.leave_type,
                    "start_date": str(instance.start_date),
                    "end_date": str(instance.end_date),
                    "days": instance.days_requested,
                    "pending_since": str(instance.created_at),
                    "action_url": f"/pay/leave/{instance.pk}/",
                },
            )
        elif request_type == "iou":
            service.send_notification(
                recipient=user,
                notification_type="IOU_ESCALATED",
                priority="HIGH",
                context={
                    "employee": str(instance.employee),
                    "amount": str(instance.amount),
                    "reason": instance.reason or "",
                    "pending_since": str(instance.created_at),
                    "action_url": f"/pay/iou/{instance.pk}/",
                },
            )
