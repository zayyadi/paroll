"""Compensation planning service (P2-11).

Implements the create -> recommend -> approve -> apply cycle described in
docs/world_class_employee_management_research_2026-10-14.md (gap #11), on top
of ``SalaryHistory``.

Applying an approved review delegates to the registered ``salary.change``
operation: ``apply_review`` submits an ``ApprovalRequest`` (the assigned-config
guard forbids editing ``basic_salary`` inline), and when an independent
approver releases the change under a genuine execution context the operation
swaps in a new config, re-points ``employee_pay``, writes ``SalaryHistory`` and
finalises the review (status ``APPLIED`` + cycle roll-up).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from payroll.models.compensation import CompCycle, CompReview, SalaryBand


def create_cycle(
    *,
    company: Any,
    name: str,
    effective_date: date,
    budget_amount: Optional[Decimal] = None,
    created_by: Any = None,
) -> CompCycle:
    if budget_amount is not None and budget_amount < 0:
        raise ValidationError("A compensation budget cannot be negative.")
    return CompCycle.objects.create(
        company=company,
        name=name,
        effective_date=effective_date,
        budget_amount=budget_amount,
        created_by=created_by,
    )


def add_review(*, cycle: CompCycle, employee: Any) -> CompReview:
    """Add an employee to a cycle, snapshotting their current basic salary."""
    if cycle.status != CompCycle.Status.OPEN:
        raise ValidationError("Reviews can only be added to an open cycle.")
    config = employee.employee_pay
    if config is None:
        raise ValidationError("Employee has no salary configuration.")
    return CompReview.objects.create(
        cycle=cycle,
        employee=employee,
        current_basic=config.basic_salary,
        proposed_basic=config.basic_salary,
    )


def propose_review(
    *, review: CompReview, proposed_basic: Decimal, note: str = ""
) -> CompReview:
    """Recommend a raise for a review (moves it to ``recommended``)."""
    if review.status not in (
        CompReview.Status.PROPOSED,
        CompReview.Status.RECOMMENDED,
    ):
        raise ValidationError("Only proposed/recommended reviews can change.")
    if proposed_basic < review.current_basic:
        raise ValidationError("A compensation review cannot cut pay.")
    review.proposed_basic = proposed_basic
    review.note = note
    review.status = CompReview.Status.RECOMMENDED
    review.save(update_fields=["proposed_basic", "note", "status"])
    _recompute_cycle_status(review.cycle)
    return review


def reject_review(*, review: CompReview, note: str = "") -> CompReview:
    if review.status in (
        CompReview.Status.APPLIED,
        CompReview.Status.REJECTED,
    ):
        raise ValidationError("Only live reviews can be rejected.")
    review.status = CompReview.Status.REJECTED
    if note:
        review.note = note
    review.save(update_fields=["status", "note"])
    _recompute_cycle_status(review.cycle)
    return review


def approve_review(*, review: CompReview) -> CompReview:
    """Approve a recommended review (budget permitting)."""
    if review.status != CompReview.Status.RECOMMENDED:
        raise ValidationError("Only recommended reviews can be approved.")
    budget = review.cycle.budget_amount
    if budget is not None:
        increase = review.increase_amount
        committed = sum(
            r.increase_amount
            for r in review.cycle.reviews.filter(
                status__in=[
                    CompReview.Status.APPROVED,
                    CompReview.Status.APPLIED,
                ]
            )
        )
        if committed + increase > budget:
            raise ValidationError(
                "Approving this review would exceed the cycle budget."
            )
    review.status = CompReview.Status.APPROVED
    review.save(update_fields=["status"])
    _recompute_cycle_status(review.cycle)
    return review


@transaction.atomic
def apply_review(*, review: CompReview, actor: Any = None) -> CompReview:
    """Submit an approved review's raise for independent salary-change approval.

    A salary change is a controlled action (``Payroll.save`` refuses direct
    edits to an assigned config's ``basic_salary``), so this does **not** write
    the salary inline. It delegates to the domain's registered ``salary.change``
    operation (``payroll.financial_approval_actions.change_salary``), which —
    when called outside an execution context — creates an ``ActionProposal``
    and submits it through the approval workflow.

    The returned ``ApprovalRequest`` is stored on the review so an independent
    approver can decide it via ``approvals.services.decide_approval``; on final
    approval the operation runs under a genuine execution context, creating the
    new config, re-pointing ``employee_pay`` and writing ``SalaryHistory``.

    Returns ``(review, approval_request)``.
    """
    from payroll.financial_approval_actions import change_salary

    if review.status != CompReview.Status.APPROVED:
        raise ValidationError("Only approved reviews can be applied.")

    if review.employee.employee_pay is None:
        raise ValidationError("Employee has no salary configuration.")

    if review.approval_request_id:
        raise ValidationError("This review's raise is already awaiting approval.")
    approval = change_salary(
        employee=review.employee,
        basic_salary=review.proposed_basic,
        effective_date=review.cycle.effective_date,
        user=actor,
        approval_actor=actor,
    )
    review.approval_request = approval
    review.save(update_fields=["approval_request"])
    return review, approval


@transaction.atomic
def execute_review(*, review: CompReview, actor: Any = None) -> CompReview:
    """Mark a review's raise as applied once its approval has executed.

    Called after the ``salary.change`` approval for this review reaches
    ``APPROVED`` (the operation itself has already re-pointed
    ``employee_pay`` and written ``SalaryHistory`` under a genuine execution
    context). This only finalises the compensation bookkeeping.
    """
    if review.status != CompReview.Status.APPROVED:
        raise ValidationError("Only approved reviews can be marked applied.")
    review.status = CompReview.Status.APPLIED
    review.applied_at = timezone.now()
    review.save(update_fields=["status", "applied_at"])
    _recompute_cycle_status(review.cycle)
    return review


def finalise_review_for_execution(execution: Any) -> Optional[CompReview]:
    """Settle the compensation bookkeeping for an executing approval.

    ``payroll.financial_approval_actions.change_salary`` calls this under the
    genuine execution context of an approved ``salary.change`` request. If that
    request was submitted by :func:`apply_review`, the matching review moves to
    ``APPLIED`` and its cycle status rolls up. No-op for ordinary salary
    changes that did not originate from a compensation cycle.
    """
    if execution is None:
        return None
    review = (
        CompReview.objects.filter(approval_request=execution)
        .select_related("cycle")
        .first()
    )
    if review is None or review.status != CompReview.Status.APPROVED:
        return review
    return execute_review(review=review)


def cycle_totals(cycle: CompCycle) -> dict:
    """Aggregate increase/percent figures for a cycle."""
    reviews = list(cycle.reviews.all())
    total_increase = sum(
        (r.increase_amount for r in reviews), Decimal("0")
    )
    return {
        "review_count": len(reviews),
        "total_increase": total_increase,
        "budget": cycle.budget_amount,
        "budget_remaining": (
            None
            if cycle.budget_amount is None
            else cycle.budget_amount - total_increase
        ),
    }


def _recompute_cycle_status(cycle: CompCycle) -> None:
    """Roll review statuses up into the cycle status."""
    statuses = set(
        cycle.reviews.values_list("status", flat=True)
    ) or {None}
    if CompReview.Status.APPLIED in statuses:
        new_status = CompCycle.Status.APPLIED
    elif CompReview.Status.APPROVED in statuses:
        new_status = CompCycle.Status.APPROVED
    elif CompReview.Status.RECOMMENDED in statuses:
        new_status = CompCycle.Status.RECOMMENDED
    elif statuses == {CompReview.Status.REJECTED}:
        new_status = CompCycle.Status.CLOSED
    else:
        new_status = CompCycle.Status.OPEN
    if cycle.status != new_status:
        cycle.status = new_status
        cycle.save(update_fields=["status"])


__all__ = [
    "create_cycle",
    "add_review",
    "propose_review",
    "reject_review",
    "approve_review",
    "apply_review",
    "execute_review",
    "finalise_review_for_execution",
    "cycle_totals",
    "SalaryBand",
]
