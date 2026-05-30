from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from payroll.models import HiringCandidate, SurveyResponse


class Command(BaseCommand):
    help = "Apply HR data retention policies for expired candidate and survey data."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--candidate-days", type=int, default=730)
        parser.add_argument("--survey-days", type=int, default=730)

    def handle(self, *args, **options):
        now = timezone.now()
        candidate_cutoff = now - timedelta(days=options["candidate_days"])
        survey_cutoff = now - timedelta(days=options["survey_days"])

        candidates = HiringCandidate.objects.filter(
            status=HiringCandidate.Status.REJECTED,
            rejected_at__lt=candidate_cutoff,
        )
        survey_responses = SurveyResponse.objects.filter(submitted_at__lt=survey_cutoff)

        candidate_count = candidates.count()
        survey_count = survey_responses.count()

        if not options["dry_run"]:
            for candidate in candidates:
                candidate.first_name = "Deleted"
                candidate.last_name = "Candidate"
                candidate.email = f"deleted-candidate-{candidate.pk}@retained.local"
                candidate.phone = ""
                candidate.structured_notes = {}
                candidate.source = ""
                candidate.consent_to_process = False
                candidate.save(
                    update_fields=[
                        "first_name",
                        "last_name",
                        "email",
                        "phone",
                        "structured_notes",
                        "source",
                        "consent_to_process",
                        "updated_at",
                    ]
                )
            survey_responses.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Retention candidates={candidate_count} survey_responses={survey_count}"
            )
        )
