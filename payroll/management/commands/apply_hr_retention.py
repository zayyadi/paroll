from django.core.management.base import BaseCommand

from payroll.models import HRRetentionPolicy
from payroll.services.retention import apply_hr_retention


class Command(BaseCommand):
    help = "Apply HR data retention policies for expired candidate and survey data."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--candidate-days", type=int, default=None)
        parser.add_argument("--survey-days", type=int, default=730)
        parser.add_argument("--disciplinary-days", type=int, default=1095)

    def handle(self, *args, **options):
        policy = HRRetentionPolicy.objects.filter(is_active=True).first()
        result = apply_hr_retention(
            policy=policy,
            dry_run=options["dry_run"],
            candidate_days=options["candidate_days"],
            survey_days=options["survey_days"],
            disciplinary_days=options["disciplinary_days"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Retention "
                f"candidates={result.candidates} "
                f"survey_responses={result.survey_responses} "
                f"disciplinary_cases={result.disciplinary_cases}"
            )
        )
