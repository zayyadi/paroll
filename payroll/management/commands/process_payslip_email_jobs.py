from django.core.management.base import BaseCommand

from payroll.models import PayslipEmailJob
from payroll.tasks.payslip_tasks import send_payslips_for_payroll_run_task


class Command(BaseCommand):
    help = "Process queued or failed payslip email jobs synchronously."

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            action="append",
            choices=[choice[0] for choice in PayslipEmailJob.Status.choices],
            help=(
                "Job status to process. Can be passed more than once. "
                "Defaults to queued and failed."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Maximum number of jobs to process.",
        )
        parser.add_argument(
            "--job-id",
            type=int,
            help="Process one specific PayslipEmailJob id.",
        )

    def handle(self, *args, **options):
        statuses = options["status"] or [
            PayslipEmailJob.Status.QUEUED,
            PayslipEmailJob.Status.FAILED,
        ]
        limit = options["limit"]
        job_id = options["job_id"]

        jobs = PayslipEmailJob.objects.select_related("payroll_run").order_by("queued_at")
        if job_id:
            jobs = jobs.filter(id=job_id)
        else:
            jobs = jobs.filter(status__in=statuses)[:limit]

        processed = 0
        for job in jobs:
            self.stdout.write(
                f"Processing payslip email job #{job.id} for payroll_run={job.payroll_run_id}"
            )
            send_payslips_for_payroll_run_task(job.payroll_run_id, job.id)
            processed += 1

        self.stdout.write(self.style.SUCCESS(f"Processed {processed} payslip email job(s)."))
