"""NDPA 2023 data-subject request workflow (P1-8).

Gap #8 of docs/world_class_employee_management_research_2026-10-14.md: NDPA
rights need a request intake, identity verification, and approve/fulfil/reject
states with export/erasure actions that respect retention rules.

The workflow is service-driven: every state change goes through a function
here that records the actor and timestamp, and only the transitions documented
on ``DataSubjectRequest`` are allowed.

Fulfilment actions:
- ACCESS / PORTABILITY -> a JSON export of the subject's stored data
  (``build_subject_export``).
- RECTIFICATION / OBJECTION / ERASURE -> recorded summary; erasure anonymises
  the subject's PII in place and refuses when statutory retention rules
  (``DataRetentionPolicy`` on payroll/tax records) still apply.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from compliance.models import DataSubjectRequest, DataRetentionPolicy

# NDPA 2023 handling window used by this app: controllers respond without
# undue delay; this workflow tracks a 30-day internal deadline.
RESPONSE_DEADLINE_DAYS = 30

# Retention record types that block erasure while active (statutory books:
# PAYE/PenCom/NHF records must be kept for the statutory period).
ERASURE_BLOCKING_RETENTION_TYPES = ("PAYROLL", "TAX")

_ALLOWED_TRANSITIONS = {
    DataSubjectRequest.Status.SUBMITTED: {
        DataSubjectRequest.Status.VERIFIED,
        DataSubjectRequest.Status.REJECTED,
    },
    DataSubjectRequest.Status.VERIFIED: {
        DataSubjectRequest.Status.APPROVED,
        DataSubjectRequest.Status.REJECTED,
    },
    DataSubjectRequest.Status.APPROVED: {
        DataSubjectRequest.Status.FULFILLED,
        DataSubjectRequest.Status.REJECTED,
    },
    DataSubjectRequest.Status.FULFILLED: set(),
    DataSubjectRequest.Status.REJECTED: set(),
}


def submit_request(
    *,
    company: Any,
    request_type: str,
    subject_email: str,
    subject: Any = None,
    description: str = "",
) -> DataSubjectRequest:
    """Intake: register a new data-subject request (status ``submitted``)."""
    valid_types = {code for code, _ in DataSubjectRequest.RequestType.choices}
    if request_type not in valid_types:
        raise ValidationError(f"Unknown request type {request_type!r}.")
    now = timezone.now()
    return DataSubjectRequest.objects.create(
        company=company,
        subject=subject,
        subject_email=subject_email,
        request_type=request_type,
        description=description,
        received_at=now,
        due_at=now + timedelta(days=RESPONSE_DEADLINE_DAYS),
    )


def verify_request(
    request: DataSubjectRequest, *, actor: Any, note: str = ""
) -> DataSubjectRequest:
    """Identity verification step: ``submitted`` -> ``verified``."""
    _transition(request, DataSubjectRequest.Status.VERIFIED)
    request.verified_by = actor
    request.verified_at = timezone.now()
    request.verification_note = note
    request.save()
    return request


def approve_request(
    request: DataSubjectRequest, *, actor: Any, note: str = ""
) -> DataSubjectRequest:
    """Approve a verified request: ``verified`` -> ``approved``."""
    _transition(request, DataSubjectRequest.Status.APPROVED)
    request.decided_by = actor
    request.decided_at = timezone.now()
    request.decision_note = note
    request.save()
    return request


def reject_request(
    request: DataSubjectRequest, *, actor: Any, note: str = ""
) -> DataSubjectRequest:
    """Refuse a request (any non-terminal state) with a recorded reason."""
    _transition(request, DataSubjectRequest.Status.REJECTED)
    request.decided_by = actor
    request.decided_at = timezone.now()
    request.decision_note = note
    request.save()
    return request


@transaction.atomic
def fulfil_request(
    request: DataSubjectRequest, *, actor: Any
) -> DataSubjectRequest:
    """Apply the approved action and mark the request ``fulfilled``.

    ACCESS/PORTABILITY produce a JSON export stored on ``response``; erasure
    anonymises the subject's PII (refusing when statutory retention blocks
    it); rectification/objection record an empty summary.
    """
    _transition(request, DataSubjectRequest.Status.FULFILLED)
    request_type = request.request_type

    if request_type in (
        DataSubjectRequest.RequestType.ACCESS,
        DataSubjectRequest.RequestType.PORTABILITY,
    ):
        request.response = build_subject_export(request)
    elif request_type == DataSubjectRequest.RequestType.ERASURE:
        request.response = _erase_subject(request)
    else:
        request.response = {"action": "acknowledged", "request_type": request_type}

    request.fulfilled_at = timezone.now()
    request.save()
    return request


def erasure_blocked_by_retention(company: Any) -> list:
    """Active statutory-retention policies that block erasure, by name."""
    return list(
        DataRetentionPolicy.objects.filter(
            company=company,
            is_active=True,
            record_type__in=ERASURE_BLOCKING_RETENTION_TYPES,
        ).values_list("record_type", flat=True)
    )


def build_subject_export(request: DataSubjectRequest) -> dict:
    """JSON export of everything the system stores about the subject."""
    user = request.subject
    payload: dict = {
        "subject_email": request.subject_email,
        "request_type": request.request_type,
        "exported_at": timezone.now().isoformat(),
    }
    if user is None:
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.filter(
            email__iexact=request.subject_email
        ).first()
    if user is None:
        payload["profile"] = None
        return payload

    payload["user"] = {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "date_joined": user.date_joined.isoformat(),
    }
    employee = user.employee_user
    if employee is not None:
        config = employee.employee_pay
        payload["employee"] = {
            "employee_id": str(employee.id),
            "status": employee.status,
            "phone": employee.phone,
            "address": employee.address,
            "bank": employee.bank,
            "basic_salary": (
                str(config.basic_salary) if config is not None else None
            ),
        }
    return payload


def _erase_subject(request: DataSubjectRequest) -> dict:
    """Anonymise the subject's PII in place, respecting retention rules."""
    blocked = erasure_blocked_by_retention(request.company)
    if blocked:
        raise ValidationError(
            "Erasure blocked by active statutory retention: "
            + ", ".join(sorted(blocked))
            + "."
        )

    from django.contrib.auth import get_user_model

    user = request.subject
    if user is None:
        user = get_user_model().objects.filter(
            email__iexact=request.subject_email
        ).first()
    if user is None:
        return {"action": "erased", "scope": "none", "reason": "no matching subject"}

    employee = user.employee_user
    anonymised = []
    if employee is not None:
        employee.first_name = "Redacted"
        employee.last_name = "Redacted"
        employee.phone = ""
        employee.address = None
        employee.bank = ""
        employee.bank_account_name = ""
        employee.bank_account_number = ""
        employee.emergency_contact_name = ""
        employee.emergency_contact_phone = ""
        employee.save()
        anonymised.append("employee_profile")

    # PII fields on the login user; the row itself is retained (audit trail).
    user.first_name = "Redacted"
    user.last_name = "Redacted"
    user.email = f"erased-{user.pk}@invalid.local"
    user.save()
    anonymised.append("user")

    return {
        "action": "erased",
        "scope": "+".join(anonymised),
        "retention_checked": True,
    }


def _transition(request: DataSubjectRequest, new_status: str) -> None:
    if request.status not in _ALLOWED_TRANSITIONS:
        raise ValidationError(f"Unknown status {request.status!r}.")
    if new_status not in _ALLOWED_TRANSITIONS[request.status]:
        raise ValidationError(
            f"Cannot move a {request.status!r} request to {new_status!r}."
        )
    request.status = new_status
