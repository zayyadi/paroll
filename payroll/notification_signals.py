"""
Signal handlers for creating notifications using EventDispatcher.

This module replaces direct notification creation with event-based architecture.
Events are dispatched and handled by the NotificationService.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.urls import reverse

from payroll.models import (
    LeaveRequest,
    IOU,
    PayT,
    AppraisalAssignment,
    Appraisal,
    Payday,
)
from payroll.models.employee_profile import EmployeeProfile
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


@receiver(post_save, sender=PayT)
def handle_payroll_signal(sender, instance, created, **kwargs):
    """
    Handle payroll signals and dispatch appropriate events.

    Dispatches PayrollEvent when payroll becomes active (processed).
    """
    try:
        # Only notify when payroll becomes active (processed)
        if instance.is_active:
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
    payday_records = Payday.objects.filter(paydays_id=payroll)

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
        employee = payday.payroll_id.pays
        service.send_notification(
            recipient=employee,
            notification_type="PAYSLIP_AVAILABLE",
            title="Payslip Available",
            message=(
                f"Your payslip for {payroll.paydays} is now available. "
                f"Net pay: ₦{payday.payroll_id.netpay:,.2f}"
            ),
            payroll=payroll,
            action_url=reverse("payroll:pay_period_detail", args=[payroll.slug]),
            priority="HIGH",
        )

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
