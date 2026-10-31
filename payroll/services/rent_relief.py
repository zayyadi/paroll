"""Rent declarations: employee submits rent with proof, HR approves.

Only an approved declaration earns rent relief (see
``EmployeeProfile.rent_relief_for``). A decision re-saves the employee so
their salary config recomputes PAYE and net pay straight away.
"""

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone


@transaction.atomic
def review_declaration(*, declaration: Any, reviewer: Any, approve: bool, note: str = "") -> Any:
    """Approve or reject a pending declaration (maker-checker)."""
    from payroll.models import RentDeclaration

    declaration = RentDeclaration.objects.select_for_update().get(pk=declaration.pk)
    if declaration.status != RentDeclaration.Status.PENDING:
        raise ValidationError("Only a pending rent declaration can be reviewed.")
    if declaration.employee.user_id == reviewer.pk:
        raise PermissionDenied("You cannot review your own rent declaration.")
    if not approve and not note.strip():
        raise ValidationError("Give a reason when rejecting a rent declaration.")

    declaration.status = (
        RentDeclaration.Status.APPROVED if approve else RentDeclaration.Status.REJECTED
    )
    declaration.reviewed_by = reviewer
    declaration.reviewed_at = timezone.now()
    declaration.review_note = note.strip()
    declaration.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])

    if approve:
        # post_save on EmployeeProfile re-saves the salary config, which
        # recomputes taxable income, PAYE and net pay with the new relief.
        declaration.employee.save()
    return declaration
