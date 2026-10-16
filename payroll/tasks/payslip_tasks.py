"""
Celery tasks for payslip delivery.
"""

import logging

from celery import shared_task
from django.utils import timezone

from payroll.models import PayrollRun, PayslipEmailJob

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="payroll.send_payslips_for_payroll_run",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_payslips_for_payroll_run_task(self, payroll_run_id, job_id=None):
    """
    Send payslip emails for a payroll run outside the request/response cycle.
    """
    job = None
    if job_id is not None:
        job = PayslipEmailJob.objects.filter(id=job_id).first()

    if job is not None:
        job.status = PayslipEmailJob.Status.RUNNING
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

    payroll_run = PayrollRun.objects.filter(id=payroll_run_id).first()
    if payroll_run is None:
        message = "Payroll run not found"
        logger.warning(
            "Skipping payslip email task because payroll_run_id=%s does not exist",
            payroll_run_id,
        )
        if job is not None:
            job.status = PayslipEmailJob.Status.FAILED
            job.error_message = message
            job.completed_at = timezone.now()
            job.save(
                update_fields=["status", "error_message", "completed_at", "updated_at"]
            )
        return {
            "success": False,
            "sent_count": 0,
            "skipped_count": 0,
            "message": message,
        }

    from payroll.views.payroll_payslips import _send_payslips_for_payroll_run

    try:
        sent_count, skipped_details = _send_payslips_for_payroll_run(payroll_run)
    except Exception as exc:
        if job is not None:
            job.status = PayslipEmailJob.Status.FAILED
            job.error_message = str(exc)
            job.completed_at = timezone.now()
            job.save(
                update_fields=["status", "error_message", "completed_at", "updated_at"]
            )
        raise

    if job is not None:
        job.status = (
            PayslipEmailJob.Status.PARTIAL
            if skipped_details
            else PayslipEmailJob.Status.SENT
        )
        job.sent_count = sent_count
        job.skipped_count = len(skipped_details)
        job.skipped_details = skipped_details
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "sent_count",
                "skipped_count",
                "skipped_details",
                "completed_at",
                "updated_at",
            ]
        )

    logger.info(
        "Payslip email task completed for payroll_run_id=%s sent=%s skipped=%s",
        payroll_run_id,
        sent_count,
        len(skipped_details),
    )
    return {
        "success": True,
        "sent_count": sent_count,
        "skipped_count": len(skipped_details),
        "skipped_details": skipped_details,
    }


@shared_task(
    bind=True,
    name="payroll.send_single_payslip_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_single_payslip_email_task(self, payroll_id):
    """Render a single payslip PDF and queue its email in the background.

    Used by the add-pay flow so PDF generation + SMTP never block payroll
    creation. Failures are logged; the core Payroll row already exists.
    """
    from django.conf import settings

    from payroll.models import Payroll
    from payroll.views.payroll_payslips import generate_payslip_pdf
    from users.email_backend import send_mail as custom_send_mail

    payroll_instance = Payroll.objects.filter(id=payroll_id).first()
    if payroll_instance is None:
        logger.warning("Payroll %s not found, skipping payslip email", payroll_id)
        return {"success": False, "message": "Payroll not found"}

    # Payroll -> EmployeeProfile reverse: pointed to by EmployeeProfile.employee_pay.
    from payroll.models import EmployeeProfile

    employee = EmployeeProfile.objects.select_related("user").filter(
        employee_pay_id=payroll_instance.id
    ).first()
    if employee is None:
        logger.warning("No employee linked to payroll %s, skipping email", payroll_id)
        return {"success": False, "message": "Employee not found"}

    recipient_email = None
    if getattr(employee, "user", None) and employee.user.email:
        recipient_email = employee.user.email
    elif getattr(employee, "email", None):
        recipient_email = employee.email
    if not recipient_email:
        logger.warning("Employee email missing for payroll %s", payroll_id)
        return {"success": False, "message": "Employee email not found"}

    try:
        pdf_content = generate_payslip_pdf(
            {"payroll": payroll_instance, "employee": employee}
        )
    except Exception as exc:
        logger.exception("Payslip PDF generation failed for payroll %s: %s", payroll_id, exc)
        return {"success": False, "message": f"PDF generation failed: {exc}"}
    if not pdf_content:
        logger.error("Payslip PDF generation returned empty for payroll %s", payroll_id)
        return {"success": False, "message": "PDF generation failed"}

    employee_name = (
        f"{getattr(employee, 'first_name', '') or ''} "
        f"{getattr(employee, 'last_name', '') or ''}".strip()
        or recipient_email
    )
    month_year = getattr(payroll_instance, "month_year", "")
    filename = f"payslip_{getattr(employee, 'emp_id', None) or employee.id}_{month_year}.pdf"
    try:
        custom_send_mail(
            subject=f"Your Payslip for {month_year}",
            template_name="email/payslip_email.html",
            context={
                "user": getattr(employee, "user", None) or employee,
                "employee": employee,
                "employee_name": employee_name,
                "payroll": payroll_instance,
                "month_year": month_year,
                "net_pay_amount": getattr(
                    payroll_instance, "net_pay", getattr(payroll_instance, "netpay", "")
                ),
            },
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[recipient_email],
            attachments=[
                {
                    "filename": filename,
                    "content": pdf_content,
                    "mimetype": "application/pdf",
                }
            ],
        )
    except Exception as exc:
        logger.exception("Payslip email enqueue failed for payroll %s: %s", payroll_id, exc)
        return {"success": False, "message": str(exc)}

    logger.info("Queued single payslip email for payroll %s to %s", payroll_id, recipient_email)
    return {"success": True, "payroll_id": payroll_id, "recipient": recipient_email}
