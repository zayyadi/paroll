from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from approvals.access import selected_company

from payroll.models import LeaveRequest
from payroll.financial_approval_actions import request_leave_allowance_backfill


class Command(BaseCommand):
    help = "Queue independent financial approval for missing historical leave allowances."

    def add_arguments(self, parser):
        parser.add_argument('--requested-by', type=int, help='Active company finance user submitting the corrections.')
        parser.add_argument('--approval-key', help='New submission key prefix when revising a cancelled or rejected request.')
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
        parser.add_argument(
            "--skip-email",
            action="store_true",
            help="Create allowance and slip records without queueing slip email delivery.",
        )

    def handle(self, *args, **options):
        queryset = LeaveRequest.objects.select_related(
            "employee",
            "employee__employee_pay",
            "employee__company",
        ).filter(
            status="APPROVED",
            leave_type="ANNUAL",
            processed_leave_allowance__isnull=True,
        )

        if options["leave_id"]:
            queryset = queryset.filter(pk=options["leave_id"])

        actor = None
        if not options['dry_run']:
            if not options['requested_by']:
                raise CommandError('--requested-by is required to queue financial corrections.')
            try:
                actor = get_user_model().objects.get(pk=options['requested_by'], is_active=True)
                company = selected_company(actor)
            except (get_user_model().DoesNotExist, PermissionDenied) as exc:
                raise CommandError('Choose an active requester with a selected company.') from exc
            queryset = queryset.filter(employee__company=company)
        queued = 0
        skipped = 0
        for leave_request in queryset.order_by("created_at"):
            if options["dry_run"]:
                self.stdout.write(
                    f"Would process leave #{leave_request.pk} for employee #{leave_request.employee_id}"
                )
                continue

            try:
                approval = request_leave_allowance_backfill(leave_request=leave_request, actor=actor,
                    queue_email=not options['skip_email'],
                    approval_key=f"{options['approval_key']}:{leave_request.pk}" if options['approval_key'] else None)
            except (PermissionDenied, ValidationError) as exc:
                raise CommandError(str(exc)) from exc
            if approval is None:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipped leave #{leave_request.pk}: no allowance amount could be calculated."
                    )
                )
                continue

            queued += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued leave #{leave_request.pk}: approval #{approval.pk}"
                )
            )

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Matched {queryset.count()} approved leave request(s)."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued {queued} leave allowance approval(s); skipped {skipped}."
                )
            )
