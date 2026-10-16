from __future__ import annotations
from typing import Any
from decimal import Decimal
from django.utils import timezone
from django.db import transaction


def initiate_offboarding(
    *, employee: Any, last_working_day: Any, reason: str, initiated_by: Any
) -> Any:
    from payroll.models.workforce import OffboardingChecklist, OffboardingTask

    with transaction.atomic():
        checklist = OffboardingChecklist.objects.create(
            company=employee.company,
            employee=employee,
            last_working_day=last_working_day,
            reason=reason,
            initiated_by=initiated_by,
        )
        default_tasks = [
            ("ASSET_RETURN", "Return all company assets (laptop, phone, badge)", 1),
            ("ACCESS_REVOCATION", "Revoke system access and credentials", 2),
            ("KNOWLEDGE_TRANSFER", "Complete knowledge transfer documentation", 3),
            ("FINANCIAL", "Calculate final settlement (accrued leave, pro-rated salary)", 4),
            ("HR", "Return company ID and collect exit form", 5),
            ("DOCUMENTATION", "Collect signed non-disclosure agreement", 6),
        ]
        for cat, title, order in default_tasks:
            OffboardingTask.objects.create(
                checklist=checklist, category=cat, title=title, order=order
            )
        # Fan out a signed webhook when an exit/termination begins (P1-9).
        # ``last_working_day`` may arrive as a str or date, so coerce.
        from webhooks.services import emit_event

        if hasattr(last_working_day, "isoformat"):
            lwd = last_working_day.isoformat()
        else:
            lwd = str(last_working_day)
        emit_event(
            employee.company,
            "employee.terminated",
            {
                "checklist_id": str(checklist.pk),
                "employee_id": str(employee.pk),
                "reason": reason,
                "last_working_day": lwd,
            },
        )
    return checklist


def complete_task(*, task: Any, completed_by: Any, notes: str = "") -> Any:
    task.is_completed = True
    task.completed_by = completed_by
    task.completed_at = timezone.now()
    task.notes = notes
    task.save(update_fields=["is_completed", "completed_by", "completed_at", "notes"])
    return task


def calculate_final_settlement(*, checklist: Any) -> Decimal:
    """Legacy one-number settlement summary (payables only).

    P2-15: the full statement (payables + receivables + asset recovery with
    journal linkage) lives in ``ExitSettlement``; this delegates to the same
    payables helper so the two can never disagree.
    """
    from payroll.services.exit_settlement_service import payables_for

    payables = payables_for(checklist.employee)
    total = payables["final_month_salary"] + payables["leave_encashment"]

    checklist.final_settlement_amount = total
    checklist.save(update_fields=["final_settlement_amount"])
    return total


def complete_offboarding(*, checklist: Any, actor: Any = None) -> Any:
    from approvals.services import execution_authorized
    if not execution_authorized(checklist, "offboarding.complete"):
        from payroll.services.hr_workflow import decide
        return decide(checklist, "offboarding.complete", actor)

    all_done = not checklist.tasks.filter(is_completed=False).exists()
    if not all_done:
        raise ValueError("All tasks must be completed before finalizing offboarding.")
    checklist.status = "COMPLETED"
    checklist.completed_at = timezone.now()
    checklist.save(update_fields=["status", "completed_at"])
    return checklist
