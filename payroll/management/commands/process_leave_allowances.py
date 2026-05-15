from django.core.management.base import BaseCommand

from payroll.models import LeaveRequest
from payroll.services.leave_allowance import process_leave_allowance_for_request


class Command(BaseCommand):
    help = "Process automatic leave allowances for approved leave requests."

    def add_arguments(self, parser):
        parser.add_argument(
            "--leave-id",
            type=int,
            help="Process one approved leave request id.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show matching approved leave requests without creating allowances.",
        )

    def handle(self, *args, **options):
        queryset = LeaveRequest.objects.select_related(
            "employee",
            "employee__employee_pay",
            "employee__company",
        ).filter(status="APPROVED")

        if options["leave_id"]:
            queryset = queryset.filter(pk=options["leave_id"])

        processed = 0
        skipped = 0
        for leave_request in queryset.order_by("created_at"):
            if options["dry_run"]:
                self.stdout.write(
                    f"Would process leave #{leave_request.pk} for employee #{leave_request.employee_id}"
                )
                continue

            allowance = process_leave_allowance_for_request(leave_request)
            if allowance is None:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipped leave #{leave_request.pk}: no allowance amount could be calculated."
                    )
                )
                continue

            processed += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Processed leave #{leave_request.pk}: allowance #{allowance.pk} amount={allowance.amount}"
                )
            )

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Matched {queryset.count()} approved leave request(s)."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Processed {processed} leave allowance(s); skipped {skipped}."
                )
            )
