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
    return checklist


def complete_task(*, task: Any, completed_by: Any, notes: str = "") -> Any:
    task.is_completed = True
    task.completed_by = completed_by
    task.completed_at = timezone.now()
    task.notes = notes
    task.save(update_fields=["is_completed", "completed_by", "completed_at", "notes"])
    return task


def calculate_final_settlement(*, checklist: Any) -> Decimal:
    employee = checklist.employee
    total = Decimal("0.00")

    if employee.employee_pay:
        total += employee.employee_pay.basic / Decimal("12")

    from payroll.models.payroll import LeaveBalance

    balance = LeaveBalance.objects.filter(employee=employee, year=timezone.now().year).first()
    if balance:
        total += Decimal(str(balance.annual_leave)) * (
            employee.employee_pay.basic / Decimal("12") / Decimal("20")
        )

    checklist.final_settlement_amount = total
    checklist.save(update_fields=["final_settlement_amount"])
    return total


def complete_offboarding(*, checklist: Any) -> Any:
    all_done = not checklist.tasks.filter(is_completed=False).exists()
    if not all_done:
        raise ValueError("All tasks must be completed before finalizing offboarding.")
    checklist.status = "COMPLETED"
    checklist.completed_at = timezone.now()
    checklist.save(update_fields=["status", "completed_at"])
    return checklist
