"""Thin signal handlers for notification side effects."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch

from payroll.models import AppraisalAssignment, IOU, LeaveRequest, PayrollRun
from payroll.services import notification_signals as notification_signal_services
from payroll.services.notification_service import EventDispatcher, NotificationService
from payroll.services.notification_signals import NotificationSignalService
from users.email_backend import send_mail as custom_send_mail

logger = logging.getLogger(__name__)
User = get_user_model()
event_dispatcher = EventDispatcher()


def _notification_signals_enabled() -> bool:
    return getattr(settings, "NOTIFICATION_SIGNALS_ENABLED", True)


def _safe_reverse(
    view_name: str,
    *,
    args: list[Any] | tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    default: str = "#",
) -> str:
    try:
        return reverse(view_name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        logger.debug("Missing URL name for notification action_url: %s", view_name)
        return default


def _notification_service() -> NotificationSignalService:
    notification_signal_services.custom_send_mail = custom_send_mail
    return NotificationSignalService(
        notification_service=NotificationService(),
        event_dispatcher=event_dispatcher,
    )


@receiver(post_save, sender=LeaveRequest)
def handle_leave_request_signal(
    sender: type[LeaveRequest],
    instance: LeaveRequest,
    created: bool,
    **kwargs: Any,
) -> None:
    if not _notification_signals_enabled():
        return
    try:
        _notification_service().handle_leave_request_saved(instance, created=created)
    except Exception as exc:
        logger.error("Error handling leave request signal: %s", exc)


@receiver(post_save, sender=IOU)
def handle_iou_signal(
    sender: type[IOU],
    instance: IOU,
    created: bool,
    **kwargs: Any,
) -> None:
    if not _notification_signals_enabled():
        return
    try:
        _notification_service().handle_iou_saved(instance, created=created)
    except Exception as exc:
        logger.error("Error handling IOU signal: %s", exc)


@receiver(post_save, sender=PayrollRun)
def handle_payroll_signal(
    sender: type[PayrollRun],
    instance: PayrollRun,
    created: bool,
    **kwargs: Any,
) -> None:
    if not _notification_signals_enabled():
        return
    try:
        _notification_service().handle_payroll_run_saved(instance, created=created)
    except Exception as exc:
        logger.error("Error handling payroll signal: %s", exc)


@receiver(post_save, sender=AppraisalAssignment)
def handle_appraisal_signal(
    sender: type[AppraisalAssignment],
    instance: AppraisalAssignment,
    created: bool,
    **kwargs: Any,
) -> None:
    if not _notification_signals_enabled():
        return
    try:
        _notification_service().handle_appraisal_assignment_saved(
            instance,
            created=created,
        )
    except Exception as exc:
        logger.error("Error handling appraisal signal: %s", exc)


def create_notification(
    recipient: Any,
    notification_type: str,
    title: str,
    message: str,
    **kwargs: Any,
) -> Any:
    logger.warning(
        "create_notification() is deprecated. "
        "Use NotificationService.send_notification() instead."
    )
    return NotificationService().send_notification(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        **kwargs,
    )


def create_bulk_notification(
    recipients: Any,
    notification_type: str,
    title: str,
    message: str,
    **kwargs: Any,
) -> list[Any]:
    logger.warning(
        "create_bulk_notification() is deprecated. "
        "Use NotificationService.send_bulk_notification() instead."
    )
    return NotificationService().send_bulk_notification(
        recipients=recipients,
        notification_type=notification_type,
        title=title,
        message=message,
        **kwargs,
    )


@receiver(pre_save, sender=LeaveRequest)
def track_leave_previous_status(
    sender: type[LeaveRequest],
    instance: LeaveRequest,
    **kwargs: Any,
) -> None:
    if not instance.pk:
        instance._previous_status = None
        return
    try:
        instance._previous_status = LeaveRequest.objects.get(pk=instance.pk).status
    except LeaveRequest.DoesNotExist:
        instance._previous_status = None


@receiver(pre_save, sender=IOU)
def track_iou_previous_status(
    sender: type[IOU],
    instance: IOU,
    **kwargs: Any,
) -> None:
    if not instance.pk:
        instance._previous_status = None
        return
    try:
        instance._previous_status = IOU.objects.get(pk=instance.pk).status
    except IOU.DoesNotExist:
        instance._previous_status = None


@receiver(pre_save, sender=PayrollRun)
def track_payroll_previous_active(
    sender: type[PayrollRun],
    instance: PayrollRun,
    **kwargs: Any,
) -> None:
    if not instance.pk:
        instance._previous_is_active = False
        return
    try:
        instance._previous_is_active = PayrollRun.objects.get(pk=instance.pk).is_active
    except PayrollRun.DoesNotExist:
        instance._previous_is_active = False


def _dispatch_leave_request_created_event(leave_request: LeaveRequest) -> None:
    _notification_service().dispatch_leave_request_created(leave_request)


def _dispatch_leave_request_approved_event(leave_request: LeaveRequest) -> None:
    _notification_service().dispatch_leave_request_approved(leave_request)


def _dispatch_leave_request_rejected_event(leave_request: LeaveRequest) -> None:
    _notification_service().dispatch_leave_request_rejected(leave_request)


def _dispatch_iou_created_event(iou: IOU) -> None:
    _notification_service().dispatch_iou_created(iou)


def _dispatch_iou_approved_event(iou: IOU) -> None:
    _notification_service().dispatch_iou_approved(iou)


def _dispatch_iou_rejected_event(iou: IOU) -> None:
    _notification_service().dispatch_iou_rejected(iou)


def _dispatch_iou_paid_event(iou: IOU) -> None:
    _notification_service().dispatch_iou_paid(iou)


def _dispatch_payroll_processed_event(payroll: PayrollRun) -> None:
    _notification_service().dispatch_payroll_processed(payroll)


def _dispatch_appraisal_assigned_event(
    appraisal_assignment: AppraisalAssignment,
) -> None:
    _notification_service().dispatch_appraisal_assigned(appraisal_assignment)


def _get_employee_email(employee_profile: Any) -> str | None:
    return NotificationSignalService.get_employee_email(employee_profile)


def _get_employee_name(employee_profile: Any) -> str:
    return NotificationSignalService.get_employee_name(employee_profile)


def _send_leave_status_email(leave_request: LeaveRequest) -> None:
    _notification_service().send_leave_status_email(leave_request)


def _send_iou_status_email(iou: IOU) -> None:
    _notification_service().send_iou_status_email(iou)


def _send_salary_created_email(payroll: PayrollRun, payday: Any) -> None:
    _notification_service().send_salary_created_email(payroll, payday)


def _send_appraisal_assignment_emails(
    appraisal_assignment: AppraisalAssignment,
) -> None:
    _notification_service().send_appraisal_assignment_emails(appraisal_assignment)
