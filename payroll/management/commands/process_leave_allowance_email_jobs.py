from django.core.management.base import BaseCommand

from payroll.models import LeaveAllowanceEmailJob
from payroll.tasks.leave_allowance_tasks import send_leave_allowance_slip_task


class Command(BaseCommand):
    help = "Process queued or failed leave allowance slip email jobs synchronously."

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            action="append",
            choices=[choice[0] for choice in LeaveAllowanceEmailJob.Status.choices],
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
            help="Process one specific LeaveAllowanceEmailJob id.",
        )

    def handle(self, *args, **options):
        statuses = options["status"] or [
            LeaveAllowanceEmailJob.Status.QUEUED,
            LeaveAllowanceEmailJob.Status.FAILED,
        ]
        limit = options["limit"]
        job_id = options["job_id"]

        jobs = LeaveAllowanceEmailJob.objects.select_related(
            "leave_request",
            "allowance",
        ).order_by("queued_at")
        if job_id:
            jobs = jobs.filter(id=job_id)
        else:
            jobs = jobs.filter(status__in=statuses)[:limit]

        processed = 0
        for job in jobs:
            self.stdout.write(
                f"Processing leave allowance email job #{job.id} "
                f"for leave_request={job.leave_request_id}"
            )
            send_leave_allowance_slip_task(job.leave_request_id, job.id)
            processed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed} leave allowance email job(s)."
            )
        )
