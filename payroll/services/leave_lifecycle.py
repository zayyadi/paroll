"""Leave request lifecycle transitions (P2-12, gap #12).

Adds the fourth/fifth request states alongside the existing escalation wiring
(``escalation_service``): an employee may withdraw a still-pending request,
and HR may cancel an approved one before it is consumed. Both are auditable
status transitions, not deletions, so the ledger and audit log stay consistent.
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from payroll.models import LeaveRequest


def withdraw_request(*, leave: LeaveRequest, actor: Any = None) -> LeaveRequest:
    """Employee withdraws their own request while it is still pending.

    Only the original requester may withdraw, and only from a live state.
    A request that was already decided (approved/rejected) cannot be withdrawn
    through this path — approval must be cancelled by HR instead.
    """
    if leave.status not in LeaveRequest.LIVE_STATES:
        raise ValidationError(
            "Only a pending leave request can be withdrawn."
        )
    if actor is not None:
        requester_id = getattr(leave.employee, "user_id", None)
        if getattr(actor, "pk", None) != requester_id:
            raise ValidationError("Only the requester may withdraw a leave request.")

    leave.status = "WITHDRAWN"
    leave.save(update_fields=["status", "updated_at"], user=actor)
    return leave


def cancel_request(
    *, leave: LeaveRequest, actor: Any = None, reason: str = ""
) -> LeaveRequest:
    """HR cancels a still-pending request (e.g. it was raised in error).

    An already-approved leave is a reviewed decision and cannot be cancelled
    here — ``LeaveRequest.save`` routes any transition out of APPROVED/REJECTED
    through the ``leave.approve`` workflow (``guard_state``), and reversing a
    consumed entitlement belongs to that workflow, not to a direct save.
    """
    if leave.status in LeaveRequest.TERMINAL_STATES or leave.status == "APPROVED":
        raise ValidationError(
            "This leave request is already decided and cannot be cancelled."
        )

    leave.status = "CANCELLED"
    leave.save(update_fields=["status", "updated_at"], user=actor)
    return leave


def escalate_to_hr(*, leave: LeaveRequest, actor: Any = None) -> LeaveRequest:
    """Move a pending request into the HR-review queue (``PENDING_HR``).

    Used by the escalation path so a request that has aged past the manager
    window surfaces to HR rather than silently staying ``PENDING``.
    """
    if leave.status != "PENDING":
        raise ValidationError("Only a pending request can be escalated to HR.")
    leave.status = "PENDING_HR"
    leave.save(update_fields=["status", "updated_at"], user=actor)
    return leave


__all__ = [
    "withdraw_request",
    "cancel_request",
    "escalate_to_hr",
]
