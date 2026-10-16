"""
Background tasks for model-signal notification side effects.

Signal handlers in ``payroll.notification_signals`` must never block the
request/response cycle or fail the core DB transaction. They only enqueue
one of the tasks below via ``transaction.on_commit``. The heavy work --
DB fan-out, Notification creation, template rendering, SMTP/Twilio/FCM
network I/O -- happens here in a Celery worker.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _signal_service():
    from payroll.services.notification_signals import NotificationSignalService
    from payroll.services.notification_service import EventDispatcher, NotificationService

    return NotificationSignalService(
        notification_service=NotificationService(),
        event_dispatcher=EventDispatcher(),
    )


@shared_task(
    bind=True,
    name="payroll.handle_leave_request_signal",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def handle_leave_request_signal_task(self, leave_request_id, created, previous_status=None):
    from payroll.models import LeaveRequest

    leave_request = LeaveRequest.objects.select_related("employee__user").filter(
        id=leave_request_id
    ).first()
    if leave_request is None:
        logger.warning("LeaveRequest %s not found, skipping notification", leave_request_id)
        return {"success": False, "message": "LeaveRequest not found"}
    # Restore pre_save snapshot captured in the request thread.
    leave_request._previous_status = previous_status
    _signal_service().handle_leave_request_saved(leave_request, created=created)
    return {"success": True, "leave_request_id": leave_request_id}


@shared_task(
    bind=True,
    name="payroll.handle_iou_signal",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def handle_iou_signal_task(self, iou_id, created, previous_status=None):
    from payroll.models import IOU

    iou = IOU.objects.select_related("employee_id__user").filter(id=iou_id).first()
    if iou is None:
        logger.warning("IOU %s not found, skipping notification", iou_id)
        return {"success": False, "message": "IOU not found"}
    iou._previous_status = previous_status
    _signal_service().handle_iou_saved(iou, created=created)
    return {"success": True, "iou_id": iou_id}


@shared_task(
    bind=True,
    name="payroll.handle_payroll_run_signal",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def handle_payroll_run_signal_task(self, payroll_run_id, created, previous_is_active=False):
    from payroll.models import PayrollRun

    payroll_run = PayrollRun.objects.filter(id=payroll_run_id).first()
    if payroll_run is None:
        logger.warning("PayrollRun %s not found, skipping notification", payroll_run_id)
        return {"success": False, "message": "PayrollRun not found"}
    payroll_run._previous_is_active = previous_is_active
    _signal_service().handle_payroll_run_saved(payroll_run, created=created)
    return {"success": True, "payroll_run_id": payroll_run_id}


@shared_task(
    bind=True,
    name="payroll.handle_appraisal_assignment_signal",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def handle_appraisal_assignment_signal_task(self, assignment_id, created):
    from payroll.models import AppraisalAssignment

    assignment = (
        AppraisalAssignment.objects.select_related(
            "appraisal", "appraisee__user", "appraiser__user"
        )
        .filter(id=assignment_id)
        .first()
    )
    if assignment is None:
        logger.warning("AppraisalAssignment %s not found, skipping notification", assignment_id)
        return {"success": False, "message": "AppraisalAssignment not found"}
    _signal_service().handle_appraisal_assignment_saved(assignment, created=created)
    return {"success": True, "assignment_id": assignment_id}
