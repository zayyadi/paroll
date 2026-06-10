"""Notification signal orchestration services."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch

from payroll.events.notification_events import (
    AppraisalEvent,
    EventType,
    IOUEvent,
    LeaveRequestEvent,
    PayrollEvent,
)
from payroll.models import PayrollRunEntry
from payroll.models.employee_profile import EmployeeProfile
from payroll.services.notification_service import EventDispatcher, NotificationService
from users.email_backend import send_mail as custom_send_mail

logger = logging.getLogger(__name__)
User = get_user_model()


def notification_signals_enabled() -> bool:
    return getattr(settings, "NOTIFICATION_SIGNALS_ENABLED", True)


def safe_reverse(
    view_name: str,
    *,
    args: Iterable[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    default: str = "#",
) -> str:
    try:
        return reverse(view_name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        logger.debug("Missing URL name for notification action_url: %s", view_name)
        return default


class NotificationSignalService:
    """Owns notification side effects triggered by model signals."""

    def __init__(
        self,
        *,
        notification_service: NotificationService | None = None,
        event_dispatcher: EventDispatcher | None = None,
    ) -> None:
        self.notification_service = notification_service or NotificationService()
        self.event_dispatcher = event_dispatcher or EventDispatcher()

    def handle_leave_request_saved(self, leave_request: Any, *, created: bool) -> None:
        if created:
            self.dispatch_leave_request_created(leave_request)
            return

        previous_status = getattr(leave_request, "_previous_status", None)
        if previous_status == leave_request.status:
            return
        if leave_request.status == "APPROVED":
            self.dispatch_leave_request_approved(leave_request)
        elif leave_request.status == "REJECTED":
            self.dispatch_leave_request_rejected(leave_request)

    def dispatch_leave_request_created(self, leave_request: Any) -> None:
        hr_users = User.objects.filter(
            user_permissions__codename="view_employeeprofile"
        ).distinct()
        event = LeaveRequestEvent(
            leave_request=leave_request,
            event_type=EventType.LEAVE_REQUEST_CREATED,
            actor=leave_request.employee.user if leave_request.employee else None,
        )
        self.event_dispatcher.dispatch(
            event_type="leave.pending",
            event_data=event.to_dict(),
        )
        message = (
            f"{leave_request.employee.first_name} {leave_request.employee.last_name} "
            f"has requested {leave_request.leave_type.lower()} leave from "
            f"{leave_request.start_date} to {leave_request.end_date}."
        )
        for user in hr_users:
            try:
                employee_profile = user.employee_user
            except EmployeeProfile.DoesNotExist:
                continue
            self.notification_service.send_notification(
                recipient=employee_profile,
                notification_type="LEAVE_PENDING",
                title="New Leave Request",
                message=message,
                leave_request=leave_request,
                action_url=safe_reverse("payroll:manage_leave_requests"),
                priority="MEDIUM",
            )

    def dispatch_leave_request_approved(self, leave_request: Any) -> None:
        event = LeaveRequestEvent(
            leave_request=leave_request,
            event_type=EventType.LEAVE_REQUEST_APPROVED,
        )
        self.event_dispatcher.dispatch(
            event_type="leave.approved",
            event_data=event.to_dict(),
        )
        self.notification_service.send_notification(
            recipient=leave_request.employee,
            notification_type="LEAVE_APPROVED",
            title="Leave Request Approved",
            message=(
                f"Your {leave_request.leave_type.lower()} leave from "
                f"{leave_request.start_date} to {leave_request.end_date} has been approved."
            ),
            leave_request=leave_request,
            action_url=safe_reverse("payroll:leave_requests"),
            priority="HIGH",
        )
        self.send_leave_status_email(leave_request)

    def dispatch_leave_request_rejected(self, leave_request: Any) -> None:
        event = LeaveRequestEvent(
            leave_request=leave_request,
            event_type=EventType.LEAVE_REQUEST_REJECTED,
        )
        self.event_dispatcher.dispatch(
            event_type="leave.rejected",
            event_data=event.to_dict(),
        )
        self.notification_service.send_notification(
            recipient=leave_request.employee,
            notification_type="LEAVE_REJECTED",
            title="Leave Request Rejected",
            message=(
                f"Your {leave_request.leave_type.lower()} leave from "
                f"{leave_request.start_date} to {leave_request.end_date} has been rejected."
            ),
            leave_request=leave_request,
            action_url=safe_reverse("payroll:leave_requests"),
            priority="HIGH",
        )
        self.send_leave_status_email(leave_request)

    def handle_iou_saved(self, iou: Any, *, created: bool) -> None:
        if created:
            self.dispatch_iou_created(iou)
            return

        previous_status = getattr(iou, "_previous_status", None)
        if previous_status == iou.status:
            return
        if iou.status == "APPROVED":
            self.dispatch_iou_approved(iou)
        elif iou.status == "REJECTED":
            self.dispatch_iou_rejected(iou)
        elif iou.status == "PAID":
            self.dispatch_iou_paid(iou)

    def dispatch_iou_created(self, iou: Any) -> None:
        hr_users = User.objects.filter(
            user_permissions__codename="view_employeeprofile"
        ).distinct()
        event = IOUEvent(
            iou=iou,
            event_type=EventType.IOU_CREATED,
            actor=iou.employee_id.user if iou.employee_id else None,
        )
        self.event_dispatcher.dispatch(event_type="iou.pending", event_data=event.to_dict())
        message = (
            f"{iou.employee_id.first_name} {iou.employee_id.last_name} "
            f"has requested an IOU of NGN {iou.amount} for {iou.tenor} months."
        )
        for user in hr_users:
            try:
                employee_profile = user.employee_user
            except EmployeeProfile.DoesNotExist:
                continue
            self.notification_service.send_notification(
                recipient=employee_profile,
                notification_type="IOU_PENDING",
                title="New IOU Request",
                message=message,
                iou=iou,
                action_url=safe_reverse("payroll:iou_list"),
                priority="MEDIUM",
            )

    def dispatch_iou_approved(self, iou: Any) -> None:
        event = IOUEvent(iou=iou, event_type=EventType.IOU_APPROVED)
        self.event_dispatcher.dispatch(event_type="iou.approved", event_data=event.to_dict())
        self.notification_service.send_notification(
            recipient=iou.employee_id,
            notification_type="IOU_APPROVED",
            title="IOU Request Approved",
            message=(
                f"Your IOU request for NGN {iou.amount} has been approved. "
                f"Repayment will be deducted over {iou.tenor} months."
            ),
            iou=iou,
            action_url=safe_reverse("payroll:iou_list"),
            priority="HIGH",
        )
        self.send_iou_status_email(iou)

    def dispatch_iou_rejected(self, iou: Any) -> None:
        event = IOUEvent(iou=iou, event_type=EventType.IOU_REJECTED)
        self.event_dispatcher.dispatch(event_type="iou.rejected", event_data=event.to_dict())
        self.notification_service.send_notification(
            recipient=iou.employee_id,
            notification_type="IOU_REJECTED",
            title="IOU Request Rejected",
            message=f"Your IOU request for NGN {iou.amount} has been rejected.",
            iou=iou,
            action_url=safe_reverse("payroll:iou_list"),
            priority="HIGH",
        )
        self.send_iou_status_email(iou)

    def dispatch_iou_paid(self, iou: Any) -> None:
        event = IOUEvent(iou=iou, event_type=EventType.IOU_APPROVED)
        self.event_dispatcher.dispatch(event_type="iou.paid", event_data=event.to_dict())
        self.notification_service.send_notification(
            recipient=iou.employee_id,
            notification_type="IOU_APPROVED",
            title="IOU Fully Paid",
            message=f"Your IOU of NGN {iou.amount} has been fully repaid.",
            iou=iou,
            action_url=safe_reverse("payroll:iou_list"),
            priority="MEDIUM",
        )

    def handle_payroll_run_saved(self, payroll_run: Any, *, created: bool) -> None:
        previous_is_active = getattr(payroll_run, "_previous_is_active", False)
        became_active = payroll_run.is_active and (created or not previous_is_active)
        if became_active:
            self.dispatch_payroll_processed(payroll_run)

    def dispatch_payroll_processed(self, payroll_run: Any) -> None:
        payday_records = PayrollRunEntry.objects.filter(payroll_run=payroll_run)
        event = PayrollEvent(
            payroll=payroll_run,
            event_type=EventType.PAYROLL_PROCESSED,
            payday_records=payday_records,
        )
        self.event_dispatcher.dispatch(
            event_type="payroll.processed",
            event_data=event.to_dict(),
        )
        for payday in payday_records:
            employee = payday.payroll_entry.pays
            self.notification_service.send_notification(
                recipient=employee,
                notification_type="PAYSLIP_AVAILABLE",
                title="Payslip Available",
                message=(
                    f"Your payslip for {payroll_run.paydays} is now available. "
                    f"Net pay: NGN {payday.payroll_entry.netpay:,.2f}"
                ),
                payroll=payroll_run,
                action_url=safe_reverse(
                    "payroll:pay_period_detail",
                    args=[payroll_run.slug],
                ),
                priority="HIGH",
            )
            self.send_salary_created_email(payroll_run, payday)

        hr_users = User.objects.filter(
            user_permissions__codename="view_employeeprofile"
        ).distinct()
        for user in hr_users:
            try:
                employee_profile = user.employee_user
            except EmployeeProfile.DoesNotExist:
                continue
            self.notification_service.send_notification(
                recipient=employee_profile,
                notification_type="PAYROLL_PROCESSED",
                title="Payroll Processed",
                message=(
                    f"Payroll for {payroll_run.paydays} has been processed "
                    f"for {payday_records.count()} employees."
                ),
                payroll=payroll_run,
                action_url=safe_reverse(
                    "payroll:pay_period_detail",
                    args=[payroll_run.slug],
                ),
                priority="MEDIUM",
            )

    def handle_appraisal_assignment_saved(
        self,
        appraisal_assignment: Any,
        *,
        created: bool,
    ) -> None:
        if created:
            self.dispatch_appraisal_assigned(appraisal_assignment)

    def dispatch_appraisal_assigned(self, appraisal_assignment: Any) -> None:
        event = AppraisalEvent(
            appraisal_assignment=appraisal_assignment,
            event_type=EventType.APPRAISAL_ASSIGNED,
        )
        self.event_dispatcher.dispatch(
            event_type="appraisal.assigned",
            event_data=event.to_dict(),
        )
        appraisal = appraisal_assignment.appraisal
        self.notification_service.send_notification(
            recipient=appraisal_assignment.appraisee,
            notification_type="APPRAISAL_ASSIGNED",
            title="Performance Review Assigned",
            message=(
                f"You have been assigned to a performance review: {appraisal.name}. "
                "Please complete your self-assessment."
            ),
            appraisal=appraisal,
            action_url=safe_reverse("payroll:appraisal_detail", args=[appraisal.pk]),
            priority="HIGH",
        )
        self.notification_service.send_notification(
            recipient=appraisal_assignment.appraiser,
            notification_type="APPRAISAL_ASSIGNED",
            title="Review Assignment",
            message=(
                f"You have been assigned to review "
                f"{appraisal_assignment.appraisee.first_name} "
                f"{appraisal_assignment.appraisee.last_name} for the "
                f"{appraisal.name} appraisal."
            ),
            appraisal=appraisal,
            action_url=safe_reverse("payroll:appraisal_detail", args=[appraisal.pk]),
            priority="HIGH",
        )
        self.send_appraisal_assignment_emails(appraisal_assignment)

    def send_leave_status_email(self, leave_request: Any) -> None:
        recipient_email = self.get_employee_email(leave_request.employee)
        if not recipient_email:
            return
        try:
            custom_send_mail(
                subject=f"Leave Request {leave_request.status.title()}",
                template_name="email/leave_status_email.html",
                context={
                    "employee_name": self.get_employee_name(leave_request.employee),
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

    def send_iou_status_email(self, iou: Any) -> None:
        recipient_email = self.get_employee_email(iou.employee_id)
        if not recipient_email:
            return
        try:
            custom_send_mail(
                subject=f"IOU Request {iou.status.title()}",
                template_name="email/iou_status_email.html",
                context={
                    "employee_name": self.get_employee_name(iou.employee_id),
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

    def send_salary_created_email(self, payroll_run: Any, payday: Any) -> None:
        employee = payday.payroll_entry.pays
        recipient_email = self.get_employee_email(employee)
        if not recipient_email:
            return
        try:
            custom_send_mail(
                subject="Monthly Salary Created",
                template_name="email/monthly_salary_created_email.html",
                context={
                    "employee_name": self.get_employee_name(employee),
                    "payday": payroll_run.paydays,
                    "netpay": payday.payroll_entry.netpay,
                },
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.error("Failed to send monthly salary email: %s", exc)

    def send_appraisal_assignment_emails(self, appraisal_assignment: Any) -> None:
        appraisee_email = self.get_employee_email(appraisal_assignment.appraisee)
        appraiser_email = self.get_employee_email(appraisal_assignment.appraiser)
        appraisal = appraisal_assignment.appraisal
        review_path = safe_reverse(
            "payroll:review_create",
            args=[appraisal.pk, appraisal_assignment.appraisee.pk],
        )
        appraisal_path = safe_reverse("payroll:appraisal_detail", args=[appraisal.pk])
        app_base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
        review_url = f"{app_base_url}{review_path}" if app_base_url else review_path
        appraisal_url = (
            f"{app_base_url}{appraisal_path}" if app_base_url else appraisal_path
        )
        appraisee_name = self.get_employee_name(appraisal_assignment.appraisee)
        appraiser_name = self.get_employee_name(appraisal_assignment.appraiser)
        appraisal_period = f"{appraisal.start_date} - {appraisal.end_date}"

        if appraisee_email:
            self._send_appraisal_email(
                recipient_email=appraisee_email,
                subject=f"Performance Review Assigned: {appraisal.name}",
                recipient_name=appraisee_name,
                recipient_role="appraisee",
                appraisal_name=appraisal.name,
                appraisal_period=appraisal_period,
                appraisee_name=appraisee_name,
                appraiser_name=appraiser_name,
                action_url=appraisal_url,
                error_label="appraisee",
            )
        if appraiser_email:
            self._send_appraisal_email(
                recipient_email=appraiser_email,
                subject=f"Appraisal Review Task: {appraisal.name}",
                recipient_name=appraiser_name,
                recipient_role="appraiser",
                appraisal_name=appraisal.name,
                appraisal_period=appraisal_period,
                appraisee_name=appraisee_name,
                appraiser_name=appraiser_name,
                action_url=review_url,
                error_label="appraiser",
            )

    def _send_appraisal_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        recipient_name: str,
        recipient_role: str,
        appraisal_name: str,
        appraisal_period: str,
        appraisee_name: str,
        appraiser_name: str,
        action_url: str,
        error_label: str,
    ) -> None:
        try:
            custom_send_mail(
                subject=subject,
                template_name="email/appraisal_assignment_email.html",
                context={
                    "recipient_name": recipient_name,
                    "recipient_role": recipient_role,
                    "appraisal_name": appraisal_name,
                    "appraisal_period": appraisal_period,
                    "appraisee_name": appraisee_name,
                    "appraiser_name": appraiser_name,
                    "action_url": action_url,
                },
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.error(
                "Failed to send appraisal assignment email to %s: %s",
                error_label,
                exc,
            )

    @staticmethod
    def get_employee_email(employee_profile: Any) -> str | None:
        if not employee_profile:
            return None
        if employee_profile.user and employee_profile.user.email:
            return employee_profile.user.email
        if employee_profile.email:
            return employee_profile.email
        return None

    @staticmethod
    def get_employee_name(employee_profile: Any) -> str:
        if not employee_profile:
            return "Employee"
        name = (
            f"{employee_profile.first_name or ''} "
            f"{employee_profile.last_name or ''}"
        ).strip()
        return name or "Employee"
