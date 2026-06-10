from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models import Model
    from payroll.models import Company, HiringStage


STANDARD_HIRING_STAGE_BLUEPRINT = [
    ("sourced", "Sourced", False, False),
    ("screening", "Screening", False, False),
    ("structured_interview", "Structured Interview", True, False),
    ("scorecard_review", "Scorecard Review", True, True),
    ("reference_check", "Reference Check", False, False),
    ("offer", "Offer", False, True),
    ("hired", "Hired", False, False),
]


def create_standard_hiring_stages(company: Any) -> list[Any]:
    from payroll.models import HiringStage

    stages = []
    for sequence, (stage_type, name, requires_scorecard, requires_approval) in enumerate(
        STANDARD_HIRING_STAGE_BLUEPRINT, start=1
    ):
        stage, _created = HiringStage.objects.update_or_create(
            company=company,
            stage_type=stage_type,
            defaults={
                "name": name,
                "sequence": sequence,
                "requires_scorecard": requires_scorecard,
                "requires_approval": requires_approval,
                "is_active": True,
            },
        )
        stages.append(stage)
    return stages


def record_candidate_scorecard(
    *,
    candidate: Any,
    stage: Any,
    interviewer: Any,
    competency_scores: dict[str, Any],
    recommendation: str,
    notes: str = "",
) -> Any:
    from payroll.models import HiringStageScorecard

    if candidate.company_id != stage.company_id:
        raise ValueError("Candidate and hiring stage must belong to the same company")
    numeric_scores = [Decimal(str(score)) for score in competency_scores.values()]
    average_score = Decimal("0.00")
    if numeric_scores:
        average_score = (sum(numeric_scores) / len(numeric_scores)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return HiringStageScorecard.objects.create(
        company=candidate.company,
        candidate=candidate,
        stage=stage,
        interviewer=interviewer,
        competency_scores=competency_scores,
        average_score=average_score,
        recommendation=recommendation,
        notes=notes,
    )


def advance_candidate(
    candidate: Any,
    next_stage: Any,
    advanced_by: Any = None,
) -> Any:
    from payroll.models import HiringCandidate, HiringStage

    if candidate.company_id != next_stage.company_id:
        raise ValueError("Candidate and hiring stage must belong to the same company")
    if next_stage.requires_scorecard and not candidate.scorecards.filter(stage=next_stage).exists():
        raise ValueError("A structured scorecard is required before advancing to this stage")
    candidate.current_stage = next_stage
    candidate.status = (
        HiringCandidate.Status.HIRED
        if next_stage.stage_type == HiringStage.StageType.HIRED
        else HiringCandidate.Status.IN_PROCESS
    )
    if candidate.status == HiringCandidate.Status.HIRED:
        candidate.hired_at = timezone.now()
    candidate.save(update_fields=["current_stage", "status", "hired_at", "updated_at"])
    return candidate


def create_job_offer(
    *,
    candidate: Any,
    title: str,
    employment_type: str,
    salary_amount: Decimal,
    currency: str,
    start_date: Any,
    created_by: Any = None,
    terms: dict[str, Any] | None = None,
) -> Any:
    from payroll.models import HiringCandidate, JobOffer

    offer = JobOffer.objects.create(
        company=candidate.company,
        candidate=candidate,
        title=title,
        employment_type=employment_type,
        salary_amount=salary_amount,
        currency=currency,
        start_date=start_date,
        created_by=created_by,
        terms=terms or {},
    )
    candidate.status = HiringCandidate.Status.OFFER
    candidate.save(update_fields=["status", "updated_at"])
    return offer


def accept_job_offer(offer: Any, accepted_by: Any = None) -> Any:
    from payroll.models import HiringCandidate, JobOffer, JobRequisition, Position, WorkflowExecution, WorkflowTemplate

    offer.status = JobOffer.Status.ACCEPTED
    offer.accepted_at = timezone.now()
    offer.save(update_fields=["status", "accepted_at", "updated_at"])

    stages = create_standard_hiring_stages(offer.company)
    hired_stage = next(stage for stage in stages if stage.stage_type == "hired")
    candidate = offer.candidate
    candidate.current_stage = hired_stage
    candidate.status = HiringCandidate.Status.HIRED
    candidate.hired_at = timezone.now()
    candidate.save(update_fields=["current_stage", "status", "hired_at", "updated_at"])

    requisition = candidate.requisition
    hired_count = requisition.candidates.filter(status=HiringCandidate.Status.HIRED).count()
    if hired_count >= requisition.headcount:
        requisition.status = JobRequisition.Status.FILLED
        requisition.closed_at = timezone.now()
        requisition.position.status = Position.Status.FILLED
        requisition.position.save(update_fields=["status", "updated_at"])
        requisition.save(update_fields=["status", "closed_at", "updated_at"])

    template = (
        WorkflowTemplate.objects.filter(
            company=offer.company,
            workflow_type=WorkflowTemplate.WorkflowType.ONBOARDING,
            trigger_event="candidate.hired",
            is_active=True,
        )
        .order_by("name")
        .first()
    )
    if template is None:
        template = WorkflowTemplate.objects.create(
            company=offer.company,
            name="Candidate Onboarding",
            workflow_type=WorkflowTemplate.WorkflowType.ONBOARDING,
            trigger_event="candidate.hired",
        )
    return WorkflowExecution.objects.create(
        company=offer.company,
        template=template,
        started_by=accepted_by,
        status=WorkflowExecution.Status.PENDING,
        context={
            "trigger_event": "candidate.hired",
            "candidate_id": candidate.pk,
            "candidate_email": candidate.email,
            "candidate_name": str(candidate),
            "requisition_id": requisition.pk,
            "position_title": requisition.title,
            "start_date": offer.start_date.isoformat(),
        },
    )
