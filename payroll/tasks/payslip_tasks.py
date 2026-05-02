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

    from payroll.views.payroll_view import _send_payslips_for_payroll_run

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
