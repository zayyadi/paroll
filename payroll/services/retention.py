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
    disciplinary_queued: int = 0
    disciplinary_requires_approval: int = 0

    def as_dict(self) -> dict[str, int | None]:
        return {
            "policy_id": self.policy_id,
            "candidates": self.candidates,
            "survey_responses": self.survey_responses,
            "disciplinary_cases": self.disciplinary_cases,
            "disciplinary_queued": self.disciplinary_queued,
            "disciplinary_requires_approval": self.disciplinary_requires_approval,
        }


def apply_hr_retention(
    *,
    policy: HRRetentionPolicy | None = None,
    dry_run: bool = False,
    candidate_days: int | None = None,
    survey_days: int | None = None,
    disciplinary_days: int | None = None,
    actor: Any = None,
) -> RetentionResult:
    active_policy = policy or HRRetentionPolicy.objects.filter(is_active=True).first()
    if active_policy is None:
        active_policy = HRRetentionPolicy()

    if actor is not None:
        from approvals.permissions import require_company_authority
        from company.utils import get_user_company
        company = get_user_company(actor)
        require_company_authority(actor, company, "accounting.change_disciplinarycase")
        if policy is None:
            active_policy = (HRRetentionPolicy.objects.filter(company=company, is_active=True).first()
                             or HRRetentionPolicy.objects.filter(company__isnull=True, is_active=True).first()
                             or HRRetentionPolicy())
        if active_policy.pk and active_policy.company_id and active_policy.company_id != company.pk:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("Retention policy must belong to the selected company.")
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

    if actor is not None:
        candidates = candidates.filter(company=company)
        survey_responses = survey_responses.filter(company=company)
        disciplinary_cases = disciplinary_cases.filter(company=company)
    disciplinary_cases = disciplinary_cases.exclude(allegation_summary__startswith="Archived disciplinary case ")
    result = RetentionResult(
        policy_id=active_policy.pk,
        candidates=candidates.count(),
        survey_responses=survey_responses.count(),
        disciplinary_cases=0,
        disciplinary_requires_approval=disciplinary_cases.count(),
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

    if actor is not None:
        from approvals.services import submit_approval
        for case in disciplinary_cases:
            submit_approval(source=case, action="discipline.anonymize", requester=actor,
                            payload={"retention_days": disciplinary_days or active_policy.disciplinary_retention_days})
            result.disciplinary_queued += 1

    return result


def result_to_dict(result: RetentionResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, RetentionResult):
        return result.as_dict()
    return dict(result)
