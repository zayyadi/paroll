"""
Celery tasks for automatic leave allowance slip delivery.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from payroll.models import LeaveAllowanceEmailJob, LeaveRequest
from payroll.views.payroll_view import generate_payslip_pdf
from users.email_backend import send_mail as custom_send_mail

logger = logging.getLogger(__name__)


def _employee_email(employee):
    if employee.user and employee.user.email:
        return employee.user.email
    return employee.email


@shared_task(
    bind=True,
    name="payroll.send_leave_allowance_slip",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_leave_allowance_slip_task(self, leave_request_id, job_id=None):
    job = None
    if job_id is not None:
        job = LeaveAllowanceEmailJob.objects.filter(id=job_id).first()

    if job is not None:
        job.status = LeaveAllowanceEmailJob.Status.RUNNING
        job.started_at = timezone.now()
        job.completed_at = None
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "started_at",
                "completed_at",
                "error_message",
                "updated_at",
            ]
        )

    leave_request = (
        LeaveRequest.objects.select_related(
            "employee__user",
            "employee__company",
            "employee__employee_pay",
            "processed_leave_allowance",
        )
        .filter(id=leave_request_id)
        .first()
    )
    if leave_request is None:
        return _mark_failed(job, "Leave request not found")

    allowance = getattr(leave_request, "processed_leave_allowance", None)
    if allowance is None:
        return _mark_failed(job, "Leave allowance has not been processed")

    recipient_email = _employee_email(leave_request.employee)
    if not recipient_email:
        return _mark_failed(job, "Employee email not found")

    employee = leave_request.employee
    context = {
        "employee": employee,
        "employee_name": (
            f"{employee.first_name or ''} {employee.last_name or ''}".strip()
            or recipient_email
        ),
        "leave_request": leave_request,
        "allowance": allowance,
        "amount": allowance.amount,
        "company": employee.company,
    }
    pdf_content = generate_payslip_pdf(
        context,
        template_path="pay/leave_allowance_slip_pdf.html",
    )
    if not pdf_content:
        return _mark_failed(job, "Leave allowance slip PDF generation failed")

    employee_identifier = employee.emp_id or str(employee.id)
    filename = (
        f"leave_allowance_slip_{employee_identifier}_"
        f"{leave_request.start_date:%Y_%m_%d}.pdf"
    )

    custom_send_mail(
        subject=f"Leave Allowance Slip - {leave_request.start_date:%B %Y}",
        template_name="email/leave_allowance_slip_email.html",
        context=context,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient_email],
        attachments=[
            {
                "filename": filename,
                "content": pdf_content,
                "mimetype": "application/pdf",
            }
        ],
        fail_silently=False,
    )

    if job is not None:
        job.status = LeaveAllowanceEmailJob.Status.SENT
        job.error_message = ""
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])

    logger.info(
        "Leave allowance slip sent: leave_request_id=%s amount=%s",
        leave_request_id,
        allowance.amount,
    )
    return {
        "success": True,
        "amount": str(allowance.amount),
        "leave_request_id": leave_request_id,
    }


def _mark_failed(job, message):
    if job is not None:
        job.status = LeaveAllowanceEmailJob.Status.FAILED
        job.error_message = message
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
    logger.warning("Leave allowance slip delivery failed: %s", message)
    return {"success": False, "message": message}
