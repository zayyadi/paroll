"""
Signal handlers for creating notifications using EventDispatcher.

This module replaces direct notification creation with event-based architecture.
Events are dispatched and handled by the NotificationService.
"""

import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings

from payroll.models import (
    LeaveRequest,
    IOU,
    PayrollRun,
    AppraisalAssignment,
    Appraisal,
    PayrollRunEntry,
)
from payroll.models.employee_profile import EmployeeProfile
from users.email_backend import send_mail as custom_send_mail
from payroll.events.notification_events import (
    EventType,
    LeaveRequestEvent,
    IOUEvent,
    PayrollEvent,
    AppraisalEvent,
)
from payroll.services.notification_service import NotificationService, EventDispatcher

logger = logging.getLogger(__name__)

User = get_user_model()

# Initialize global event dispatcher
event_dispatcher = EventDispatcher()


@receiver(post_save, sender=LeaveRequest)
def handle_leave_request_signal(sender, instance, created, **kwargs):
    """
    Handle leave request signals and dispatch appropriate events.

    Dispatches LeaveRequestEvent based on whether it's a new request
    or a status change.
    """
    try:
        if created:
            # New leave request - notify HR/Managers
            _dispatch_leave_request_created_event(instance)
        else:
            # Status change - notify employee
            previous_status = getattr(instance, "_previous_status", None)
            if previous_status == instance.status:
                return
            if instance.status == "APPROVED":
                _dispatch_leave_request_approved_event(instance)
            elif instance.status == "REJECTED":
                _dispatch_leave_request_rejected_event(instance)

    except Exception as e:
        logger.error(f"Error handling leave request signal: {e}")


def _dispatch_leave_request_created_event(leave_request):
    """
    Dispatch event for new leave request.

    Creates notifications for all HR users about the new request.
    """
    # Get all HR users (users with view_employeeprofile permission)
    hr_users = User.objects.filter(
        user_permissions__codename="view_employeeprofile"
    ).distinct()

    # Create event
    event = LeaveRequestEvent(
        leave_request=leave_request,
        event_type=EventType.LEAVE_REQUEST_CREATED,
        actor=leave_request.employee.user if leave_request.employee else None,
    )

    # Dispatch event
    event_dispatcher.dispatch(event_type="leave.pending", event_data=event.to_dict())

    # Create notifications for HR users directly using service
    service = NotificationService()

    message = (
        f"{leave_request.employee.first_name} {leave_request.employee.last_name} "
        f"has requested {leave_request.leave_type.lower()} leave from "
        f"{leave_request.start_date} to {leave_request.end_date}."
    )

    for user in hr_users:
        try:
            employee_profile = user.employee_user
            service.send_notification(
                recipient=employee_profile,
                notification_type="LEAVE_PENDING",
                title="New Leave Request",
                message=message,
                leave_request=leave_request,
                action_url=reverse("payroll:manage_leave_requests"),
                priority="MEDIUM",
            )
        except EmployeeProfile.DoesNotExist:
            continue


def _dispatch_leave_request_approved_event(leave_request):
    """
    Dispatch event for approved leave request.

    Creates notification for the employee who requested the leave.
    """
    event = LeaveRequestEvent(
        leave_request=leave_request,
        event_type=EventType.LEAVE_REQUEST_APPROVED,
    )

    # Dispatch event
    event_dispatcher.dispatch(event_type="leave.approved", event_data=event.to_dict())

    # Create notification using service
    service = NotificationService()

    service.send_notification(
        recipient=leave_request.employee,
        notification_type="LEAVE_APPROVED",
        title="Leave Request Approved",
        message=(
            f"Your {leave_request.leave_type.lower()} leave from "
            f"{leave_request.start_date} to {leave_request.end_date} has been approved."
        ),
        leave_request=leave_request,
        action_url=reverse("payroll:leave_requests"),
        priority="HIGH",
    )
    _send_leave_status_email(leave_request)


def _dispatch_leave_request_rejected_event(leave_request):
    """
    Dispatch event for rejected leave request.

    Creates notification for the employee who requested the leave.
    """
    event = LeaveRequestEvent(
        leave_request=leave_request,
        event_type=EventType.LEAVE_REQUEST_REJECTED,
    )

    # Dispatch event
    event_dispatcher.dispatch(event_type="leave.rejected", event_data=event.to_dict())

    # Create notification using service
    service = NotificationService()

    service.send_notification(
        recipient=leave_request.employee,
        notification_type="LEAVE_REJECTED",
        title="Leave Request Rejected",
        message=(
            f"Your {leave_request.leave_type.lower()} leave from "
            f"{leave_request.start_date} to {leave_request.end_date} has been rejected."
        ),
        leave_request=leave_request,
        action_url=reverse("payroll:leave_requests"),
        priority="HIGH",
    )
    _send_leave_status_email(leave_request)


@receiver(post_save, sender=IOU)
def handle_iou_signal(sender, instance, created, **kwargs):
    """
    Handle IOU signals and dispatch appropriate events.

    Dispatches IOUEvent based on whether it's a new request
    or a status change.
    """
    try:
        if created:
            # New IOU request - notify HR/Managers
            _dispatch_iou_created_event(instance)
        else:
            # Status change - notify employee
            previous_status = getattr(instance, "_previous_status", None)
            if previous_status == instance.status:
                return
            if instance.status == "APPROVED":
                _dispatch_iou_approved_event(instance)
            elif instance.status == "REJECTED":
                _dispatch_iou_rejected_event(instance)
            elif instance.status == "PAID":
                _dispatch_iou_paid_event(instance)

    except Exception as e:
        logger.error(f"Error handling IOU signal: {e}")


def _dispatch_iou_created_event(iou):
    """
    Dispatch event for new IOU request.

    Creates notifications for all HR users about the new request.
    """
    # Get all HR users
    hr_users = User.objects.filter(
        user_permissions__codename="view_employeeprofile"
    ).distinct()

    # Create event
    event = IOUEvent(
        iou=iou,
        event_type=EventType.IOU_CREATED,
        actor=iou.employee_id.user if iou.employee_id else None,
    )

    # Dispatch event
    event_dispatcher.dispatch(event_type="iou.pending", event_data=event.to_dict())

    # Create notifications for HR users directly using service
    service = NotificationService()

    message = (
        f"{iou.employee_id.first_name} {iou.employee_id.last_name} "
        f"has requested an IOU of ₦{iou.amount} for {iou.tenor} months."
    )

    for user in hr_users:
        try:
            employee_profile = user.employee_user
            service.send_notification(
                recipient=employee_profile,
                notification_type="IOU_PENDING",
                title="New IOU Request",
                message=message,
                iou=iou,
                action_url=reverse("payroll:manage_iou_requests"),
                priority="MEDIUM",
            )
        except EmployeeProfile.DoesNotExist:
            continue


def _dispatch_iou_approved_event(iou):
    """
    Dispatch event for approved IOU request.

    Creates notification for the employee who requested the IOU.
    """
    event = IOUEvent(
        iou=iou,
        event_type=EventType.IOU_APPROVED,
    )

    # Dispatch event
    event_dispatcher.dispatch(event_type="iou.approved", event_data=event.to_dict())

    # Create notification using service
    service = NotificationService()

    service.send_notification(
        recipient=iou.employee_id,
        notification_type="IOU_APPROVED",
        title="IOU Request Approved",
        message=(
            f"Your IOU request for ₦{iou.amount} has been approved. "
            f"Repayment will be deducted over {iou.tenor} months."
        ),
        iou=iou,
        action_url=reverse("payroll:iou_list"),
        priority="HIGH",
    )
    _send_iou_status_email(iou)


def _dispatch_iou_rejected_event(iou):
    """
    Dispatch event for rejected IOU request.

    Creates notification for the employee who requested the IOU.
    """
    event = IOUEvent(
        iou=iou,
        event_type=EventType.IOU_APPROVED,  # Using same type for rejection
    )

    # Dispatch event
    event_dispatcher.dispatch(event_type="iou.rejected", event_data=event.to_dict())

    # Create notification using service
    service = NotificationService()

    service.send_notification(
        recipient=iou.employee_id,
        notification_type="IOU_REJECTED",
        title="IOU Request Rejected",
        message=f"Your IOU request for ₦{iou.amount} has been rejected.",
        iou=iou,
        action_url=reverse("payroll:iou_list"),
        priority="HIGH",
    )
    _send_iou_status_email(iou)


def _dispatch_iou_paid_event(iou):
    """
    Dispatch event for fully paid IOU.

    Creates notification for the employee who had the IOU.
    """
    event = IOUEvent(
        iou=iou,
        event_type=EventType.IOU_APPROVED,  # Using same type
    )

    # Dispatch event
    event_dispatcher.dispatch(event_type="iou.paid", event_data=event.to_dict())

    # Create notification using service
    service = NotificationService()

    service.send_notification(
        recipient=iou.employee_id,
        notification_type="IOU_APPROVED",
        title="IOU Fully Paid",
        message=f"Your IOU of ₦{iou.amount} has been fully repaid.",
        iou=iou,
        action_url=reverse("payroll:iou_list"),
        priority="MEDIUM",
    )


@receiver(post_save, sender=PayrollRun)
def handle_payroll_signal(sender, instance, created, **kwargs):
    """
    Handle payroll signals and dispatch appropriate events.

    Dispatches PayrollEvent when payroll becomes active (processed).
    """
    try:
        previous_is_active = getattr(instance, "_previous_is_active", False)
        became_active = instance.is_active and (created or not previous_is_active)

        # Notify only when payroll transitions to active
        if became_active:
            _dispatch_payroll_processed_event(instance)

    except Exception as e:
        logger.error(f"Error handling payroll signal: {e}")


def _dispatch_payroll_processed_event(payroll):
    """
    Dispatch event for processed payroll.

    Creates notifications for all employees who have payslips
    in this payroll, and notifies HR that payroll is processed.
    """
    # Get all employees who have payslips in this payroll
    payday_records = PayrollRunEntry.objects.filter(payroll_run=payroll)

    # Create event
    event = PayrollEvent(
        payroll=payroll,
        event_type=EventType.PAYROLL_PROCESSED,
        payday_records=payday_records,
    )

    # Dispatch event
    event_dispatcher.dispatch(
        event_type="payroll.processed", event_data=event.to_dict()
    )

    # Create notifications using service
    service = NotificationService()

    # Notify employees
    for payday in payday_records:
        employee = payday.payroll_entry.pays
        service.send_notification(
            recipient=employee,
            notification_type="PAYSLIP_AVAILABLE",
            title="Payslip Available",
            message=(
                f"Your payslip for {payroll.paydays} is now available. "
                f"Net pay: ₦{payday.payroll_entry.netpay:,.2f}"
            ),
            payroll=payroll,
            action_url=reverse("payroll:pay_period_detail", args=[payroll.slug]),
            priority="HIGH",
        )
        _send_salary_created_email(payroll, payday)

    # Notify HR
    hr_users = User.objects.filter(
        user_permissions__codename="view_employeeprofile"
    ).distinct()

    for user in hr_users:
        try:
            employee_profile = user.employee_user
            service.send_notification(
                recipient=employee_profile,
                notification_type="PAYROLL_PROCESSED",
                title="Payroll Processed",
                message=(
                    f"Payroll for {payroll.paydays} has been processed "
                    f"for {payday_records.count()} employees."
                ),
                payroll=payroll,
                action_url=reverse("payroll:pay_period_detail", args=[payroll.slug]),
                priority="MEDIUM",
            )
        except EmployeeProfile.DoesNotExist:
            continue


@receiver(post_save, sender=AppraisalAssignment)
def handle_appraisal_signal(sender, instance, created, **kwargs):
    """
    Handle appraisal assignment signals and dispatch appropriate events.

    Dispatches AppraisalEvent when an appraisal is assigned.
    """
    try:
        if created:
            _dispatch_appraisal_assigned_event(instance)

    except Exception as e:
        logger.error(f"Error handling appraisal signal: {e}")


def _dispatch_appraisal_assigned_event(appraisal_assignment):
    """
    Dispatch event for assigned appraisal.

    Creates notifications for both the appraisee (employee being reviewed)
    and the appraiser (person doing the review).
    """
    # Create event
    event = AppraisalEvent(
        appraisal_assignment=appraisal_assignment,
        event_type=EventType.APPRAISAL_ASSIGNED,
    )

    # Dispatch event
    event_dispatcher.dispatch(
        event_type="appraisal.assigned", event_data=event.to_dict()
    )

    # Create notifications using service
    service = NotificationService()

    # Notify the appraisee (employee being reviewed)
    service.send_notification(
        recipient=appraisal_assignment.appraisee,
        notification_type="APPRAISAL_ASSIGNED",
        title="Performance Review Assigned",
        message=(
            f"You have been assigned to a performance review: "
            f"{appraisal_assignment.appraisal.name}. "
            f"Please complete your self-assessment."
        ),
        appraisal=appraisal_assignment.appraisal,
        action_url=reverse(
            "payroll:appraisal_detail", args=[appraisal_assignment.appraisal.pk]
        ),
        priority="HIGH",
    )

    # Notify the appraiser (person doing the review)
    try:
        appraiser_profile = appraisal_assignment.appraiser.employee_user
        service.send_notification(
            recipient=appraiser_profile,
            notification_type="APPRAISAL_ASSIGNED",
            title="Review Assignment",
            message=(
                f"You have been assigned to review "
                f"{appraisal_assignment.appraisee.first_name} "
                f"{appraisal_assignment.appraisee.last_name} for the "
                f"{appraisal_assignment.appraisal.name} appraisal."
            ),
            appraisal=appraisal_assignment.appraisal,
            action_url=reverse(
                "payroll:appraisal_detail", args=[appraisal_assignment.appraisal.pk]
            ),
            priority="HIGH",
        )
    except EmployeeProfile.DoesNotExist:
        pass


# ==================== HELPER FUNCTIONS ====================
# These are kept for backward compatibility but delegate to NotificationService


def create_notification(recipient, notification_type, title, message, **kwargs):
    """
    Helper function to create a notification (DEPRECATED).

    This function is kept for backward compatibility but delegates
    to NotificationService.send_notification().

    Args:
        recipient: EmployeeProfile instance
        notification_type: str notification type
        title: str notification title
        message: str notification message
        **kwargs: Additional fields

    Returns:
        Notification instance or None
    """
    logger.warning(
        "create_notification() is deprecated. Use NotificationService.send_notification() instead."
    )

    service = NotificationService()
    return service.send_notification(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        **kwargs,
    )


def create_bulk_notification(recipients, notification_type, title, message, **kwargs):
    """
    Helper function to create notifications for multiple recipients (DEPRECATED).

    This function is kept for backward compatibility but delegates
    to NotificationService.send_bulk_notification().

    Args:
        recipients: QuerySet or list of EmployeeProfile instances
        notification_type: str notification type
        title: str notification title
        message: str notification message
        **kwargs: Additional fields

    Returns:
        List of Notification instances
    """
    logger.warning(
        "create_bulk_notification() is deprecated. Use NotificationService.send_bulk_notification() instead."
    )

    service = NotificationService()
    return service.send_bulk_notification(
        recipients=recipients,
        notification_type=notification_type,
        title=title,
        message=message,
        **kwargs,
    )


@receiver(pre_save, sender=LeaveRequest)
def track_leave_previous_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return
    try:
        instance._previous_status = LeaveRequest.objects.get(pk=instance.pk).status
    except LeaveRequest.DoesNotExist:
        instance._previous_status = None


@receiver(pre_save, sender=IOU)
def track_iou_previous_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return
    try:
        instance._previous_status = IOU.objects.get(pk=instance.pk).status
    except IOU.DoesNotExist:
        instance._previous_status = None


@receiver(pre_save, sender=PayrollRun)
def track_payroll_previous_active(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_is_active = False
        return
    try:
        instance._previous_is_active = PayrollRun.objects.get(pk=instance.pk).is_active
    except PayrollRun.DoesNotExist:
        instance._previous_is_active = False


def _get_employee_email(employee_profile):
    if not employee_profile:
        return None
    if employee_profile.user and employee_profile.user.email:
        return employee_profile.user.email
    if employee_profile.email:
        return employee_profile.email
    return None


def _get_employee_name(employee_profile):
    if not employee_profile:
        return "Employee"
    name = f"{employee_profile.first_name or ''} {employee_profile.last_name or ''}".strip()
    return name or "Employee"


def _send_leave_status_email(leave_request):
    recipient_email = _get_employee_email(leave_request.employee)
    if not recipient_email:
        return

    try:
        custom_send_mail(
            subject=f"Leave Request {leave_request.status.title()}",
            template_name="email/leave_status_email.html",
            context={
                "employee_name": _get_employee_name(leave_request.employee),
                "status": leave_request.status,
                "leave_type": leave_request.get_leave_type_display(),
                "start_date": leave_request.start_date,
                "end_date": leave_request.end_date,
            },
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Failed to send leave status email: %s", exc)


def _send_iou_status_email(iou):
    recipient_email = _get_employee_email(iou.employee_id)
    if not recipient_email:
        return

    try:
        custom_send_mail(
            subject=f"IOU Request {iou.status.title()}",
            template_name="email/iou_status_email.html",
            context={
                "employee_name": _get_employee_name(iou.employee_id),
                "status": iou.status,
                "amount": iou.amount,
                "tenor": iou.tenor,
            },
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Failed to send IOU status email: %s", exc)


def _send_salary_created_email(payroll, payday):
    employee = payday.payroll_entry.pays
    recipient_email = _get_employee_email(employee)
    if not recipient_email:
        return

    try:
        custom_send_mail(
            subject="Monthly Salary Created",
            template_name="email/monthly_salary_created_email.html",
            context={
                "employee_name": _get_employee_name(employee),
                "payday": payroll.paydays,
                "netpay": payday.payroll_entry.netpay,
            },
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Failed to send monthly salary email: %s", exc)
