from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone

from accounting.models import DisciplinaryCase
from payroll.models import HRRetentionPolicy, HiringCandidate, SurveyResponse


@dataclass
class RetentionResult:
    policy_id: int | None
    candidates: int = 0
    survey_responses: int = 0
    disciplinary_cases: int = 0

    def as_dict(self) -> dict[str, int | None]:
        return {
            "policy_id": self.policy_id,
            "candidates": self.candidates,
            "survey_responses": self.survey_responses,
            "disciplinary_cases": self.disciplinary_cases,
        }


def apply_hr_retention(
    *,
    policy: HRRetentionPolicy | None = None,
    dry_run: bool = False,
    candidate_days: int | None = None,
    survey_days: int | None = None,
    disciplinary_days: int | None = None,
) -> RetentionResult:
    active_policy = policy or HRRetentionPolicy.objects.filter(is_active=True).first()
    if active_policy is None:
        active_policy = HRRetentionPolicy()

    now = timezone.now()
    candidate_cutoff = now - timedelta(
        days=candidate_days or active_policy.candidate_retention_days
    )
    survey_cutoff = now - timedelta(days=survey_days or active_policy.survey_retention_days)
    discipline_cutoff_date = (
        now - timedelta(
            days=disciplinary_days or active_policy.disciplinary_retention_days
        )
    ).date()

    candidates = HiringCandidate.objects.filter(
        status=HiringCandidate.Status.REJECTED,
        rejected_at__lt=candidate_cutoff,
    )
    if active_policy.pk and active_policy.company_id:
        candidates = candidates.filter(company=active_policy.company)

    survey_responses = SurveyResponse.objects.filter(submitted_at__lt=survey_cutoff)
    if active_policy.pk and active_policy.company_id:
        survey_responses = survey_responses.filter(company=active_policy.company)

    disciplinary_cases = DisciplinaryCase.objects.filter(
        status__in=[
            DisciplinaryCase.Status.CLOSED,
            DisciplinaryCase.Status.DISMISSED,
        ],
        incident_date__lt=discipline_cutoff_date,
    )
    if active_policy.pk and active_policy.company_id:
        disciplinary_cases = disciplinary_cases.filter(company=active_policy.company)

    result = RetentionResult(
        policy_id=active_policy.pk,
        candidates=candidates.count(),
        survey_responses=survey_responses.count(),
        disciplinary_cases=disciplinary_cases.count(),
    )
    if dry_run:
        return result

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

    for case in disciplinary_cases:
        case.allegation_summary = f"Archived disciplinary case {case.pk}"
        case.allegation_details = ""
        case.findings_summary = ""
        case.decision_rationale = ""
        case.save(
            update_fields=[
                "allegation_summary",
                "allegation_details",
                "findings_summary",
                "decision_rationale",
                "updated_at",
            ]
        )

    return result


def result_to_dict(result: RetentionResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, RetentionResult):
        return result.as_dict()
    return dict(result)
