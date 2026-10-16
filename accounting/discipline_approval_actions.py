"""Reviewed findings and appeal outcomes are applied only by independent checkers."""
from __future__ import annotations
from typing import Any
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from approvals.registry import ApprovalAction, register_action
from approvals.permissions import require_company_authority
from approvals.services import submit_approval, current_execution
from accounting.models import DisciplinaryCase, DisciplinaryAppeal, DisciplinaryCaseAudit

REVIEW_PERMISSIONS = {
    "MANAGER": "accounting.change_disciplinarycase",
    "HR_LEAD": "accounting.review_hr_disciplinarycase",
    "PANEL": "accounting.review_panel_disciplinarycase",
    "EXECUTIVE": "accounting.review_executive_disciplinarycase",
}

def decision_action(case: DisciplinaryCase) -> str:
    level = case.compute_required_review_level()
    return "discipline.decide" + ("." + level.lower() if level != "MANAGER" else "")

def appeal_action(case: DisciplinaryCase) -> str:
    level = case.compute_required_review_level()
    return "discipline.appeal.review" + ("." + level.lower() if level != "MANAGER" else "")

def case_snapshot(case: DisciplinaryCase) -> dict[str, Any]:
    return {"fields": {field.attname: getattr(case, field.attname) for field in case._meta.concrete_fields},
            "evidence": list(case.evidence_items.order_by("pk").values("pk", "title", "description", "submitted_by_id", "file", "reliability_score"))}

def appeal_snapshot(appeal: DisciplinaryAppeal) -> dict[str, Any]:
    return {"appeal": {field.attname: getattr(appeal, field.attname) for field in appeal._meta.concrete_fields},
            "case": case_snapshot(appeal.case)}

def case_parties(case: DisciplinaryCase) -> list[int]:
    return [value for value in (case.respondent_id, case.reporter_id) if value]

def appeal_conflicts(appeal: DisciplinaryAppeal) -> list[int]:
    return [value for value in (appeal.appellant_id, appeal.case.respondent_id, appeal.case.reporter_id, appeal.case.decided_by_id) if value]

def validate_decision(case: DisciplinaryCase, payload: dict[str, Any]) -> None:
    if case.status not in {case.Status.INTAKE, case.Status.UNDER_INVESTIGATION, case.Status.PANEL_REVIEW}:
        raise ValidationError("Only an open investigated case can receive a new decision.")
    if payload.get("finding") not in DisciplinaryCase.Finding.values:
        raise ValidationError("A valid finding is required.")
    if not str(payload.get("rationale", "")).strip():
        raise ValidationError("A decision rationale is required.")

def _audit(case: DisciplinaryCase, actor: Any, action: str, details: dict[str, Any]) -> None:
    DisciplinaryCaseAudit.objects.create(case=case, actor=actor, action=action, details=details)

def apply_decision(case: DisciplinaryCase, actor: Any, payload: dict[str, Any]) -> None:
    if current_execution().action != decision_action(case):
        raise ValidationError("Case review authority changed; submit the required review level.")
    validate_decision(case, payload)
    old_status = case.status
    case.finding = payload["finding"]
    case.findings_summary = payload.get("findings_summary", "")
    case.decision_rationale = payload["rationale"]
    case.decided_by = actor
    case.decision_at = timezone.now()
    case.appeal_window_ends_at = timezone.now() + timedelta(days=10)
    case.status = case.Status.DECIDED
    case.save(update_fields=["finding", "findings_summary", "decision_rationale", "decided_by", "decision_at", "appeal_window_ends_at", "status", "updated_at"])
    _audit(case, actor, DisciplinaryCaseAudit.Action.DECISION_RECORDED,
           {"old_status": old_status, "new_status": case.status, "finding": case.finding, "required_review_level": case.required_review_level, "approval_id": current_execution().pk})

@transaction.atomic
def submit_case_decision(*, case: DisciplinaryCase, actor: Any, finding: str, rationale: str, findings_summary: str = "") -> Any:
    require_company_authority(actor, case.company, "accounting.change_disciplinarycase")
    return submit_approval(source=case, action=decision_action(case), requester=actor,
                           payload={"finding": finding, "rationale": rationale, "findings_summary": findings_summary})

def validate_appeal(appeal: DisciplinaryAppeal, payload: dict[str, Any]) -> None:
    if appeal.status not in {appeal.Status.SUBMITTED, appeal.Status.UNDER_REVIEW}:
        raise ValidationError("Only an unresolved appeal can be reviewed.")
    if payload.get("status") not in set(appeal.Status.values) - {appeal.Status.SUBMITTED, appeal.Status.UNDER_REVIEW}:
        raise ValidationError("Select a final appeal outcome.")
    if not str(payload.get("outcome_notes", "")).strip():
        raise ValidationError("Appeal outcome reasons are required.")

@transaction.atomic
def submit_appeal_review(*, appeal: DisciplinaryAppeal, actor: Any, status: str, outcome_notes: str) -> Any:
    require_company_authority(actor, appeal.case.company, "accounting.change_disciplinaryappeal")
    return submit_approval(source=appeal, action=appeal_action(appeal.case), requester=actor,
                           payload={"status": status, "outcome_notes": outcome_notes})

def apply_appeal(appeal: DisciplinaryAppeal, actor: Any, payload: dict[str, Any]) -> None:
    if current_execution().action != appeal_action(appeal.case):
        raise ValidationError("The appeal review level changed; submit again.")
    validate_appeal(appeal, payload)
    old_status = appeal.status
    appeal.status = payload["status"]
    appeal.outcome_notes = payload["outcome_notes"]
    appeal.reviewed_by = actor
    appeal.reviewed_at = timezone.now()
    appeal.save(update_fields=["status", "outcome_notes", "reviewed_by", "reviewed_at", "updated_at"])
    case = appeal.case
    if appeal.status == appeal.Status.REINVESTIGATION_ORDERED:
        case.status = case.Status.UNDER_INVESTIGATION
        case.finding = None
        case.save(update_fields=["status", "finding", "updated_at"])
    else:
        if appeal.status == appeal.Status.OVERTURNED:
            from accounting.discipline_services import revoke_sanctions_for_overturn
            revoke_sanctions_for_overturn(case=case, actor=actor)
            case.finding = case.Finding.UNSUBSTANTIATED
        case.status = case.Status.CLOSED
        case.closed_at = timezone.now()
        case.save(update_fields=["status", "finding", "closed_at", "updated_at"])
    _audit(case, actor, DisciplinaryCaseAudit.Action.APPEAL_REVIEWED,
           {"appeal_id": appeal.pk, "old_appeal_status": old_status, "new_appeal_status": appeal.status,
            "outcome_notes": appeal.outcome_notes, "approval_id": current_execution().pk})

for level, permission in REVIEW_PERMISSIONS.items():
    suffix = "." + level.lower() if level != "MANAGER" else ""
    register_action(ApprovalAction(key="discipline.decide" + suffix, model_label="accounting.DisciplinaryCase",
        permission=permission, apply=apply_decision, validate=validate_decision, snapshot=case_snapshot,
        requester=None, beneficiaries=case_parties))
    register_action(ApprovalAction(key="discipline.appeal.review" + suffix, model_label="accounting.DisciplinaryAppeal",
        permission="accounting.change_disciplinaryappeal" if level == "MANAGER" else permission,
        apply=apply_appeal, validate=validate_appeal, snapshot=appeal_snapshot,
        requester=None, beneficiaries=appeal_conflicts, company=lambda source: source.case.company))


def retention_days(case: DisciplinaryCase) -> int:
    from payroll.models import HRRetentionPolicy
    policy = HRRetentionPolicy.objects.filter(company=case.company, is_active=True).first()
    if policy is None:
        policy = HRRetentionPolicy.objects.filter(company__isnull=True, is_active=True).first() or HRRetentionPolicy()
    return policy.disciplinary_retention_days


def validate_anonymization(case: DisciplinaryCase, payload: dict[str, Any]) -> None:
    if case.status not in {case.Status.CLOSED, case.Status.DISMISSED}:
        raise ValidationError("Only finalized discipline records can be anonymized.")
    try:
        requested_days = int(payload.get("retention_days", retention_days(case)))
    except (TypeError, ValueError):
        raise ValidationError("Retention days must be a whole number.")
    days = max(retention_days(case), requested_days)
    if not case.incident_date or case.incident_date >= timezone.localdate() - timedelta(days=days):
        raise ValidationError("The configured retention period has not elapsed.")
    if case.allegation_summary.startswith("Archived disciplinary case "):
        raise ValidationError("The discipline narrative is already anonymized.")


def anonymization_snapshot(case: DisciplinaryCase) -> dict[str, Any]:
    return {"case": case_snapshot(case), "retention_days": retention_days(case)}


def apply_anonymization(case: DisciplinaryCase, actor: Any, payload: dict[str, Any]) -> None:
    validate_anonymization(case, payload)
    case.allegation_summary = f"Archived disciplinary case {case.pk}"
    case.allegation_details = ""
    case.findings_summary = ""
    case.decision_rationale = ""
    case.save(update_fields=["allegation_summary", "allegation_details", "findings_summary", "decision_rationale", "updated_at"])
    _audit(case, actor, DisciplinaryCaseAudit.Action.STATUS_CHANGED,
           {"operation": "narrative_anonymized", "approval_id": current_execution().pk})

register_action(ApprovalAction(key="discipline.anonymize", model_label="accounting.DisciplinaryCase",
    permission="accounting.change_disciplinarycase", requester=None, beneficiaries=case_parties,
    snapshot=anonymization_snapshot, validate=validate_anonymization, apply=apply_anonymization))
