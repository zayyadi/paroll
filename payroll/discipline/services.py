"""HR employment effects for disciplinary sanctions.

Owns the only place that may transition a User / EmployeeProfile to
terminated because of discipline. The ledger app must never mutate HR
records directly (see docs/adr/0002-discipline-belongs-to-hr.md).
"""

from __future__ import annotations

from django.apps import apps
from django.utils import timezone


def apply_termination_effects(sanction) -> None:
    """Deactivate the respondent when an ACTIVE TERMINATION takes effect."""
    if (
        getattr(sanction, "status", None) != sanction.Status.ACTIVE
        or getattr(sanction, "sanction_type", None) != sanction.SanctionType.TERMINATION
    ):
        return

    today = timezone.localdate()
    effective = getattr(sanction, "effective_date", None)
    if effective is not None and hasattr(effective, "date"):
        try:
            effective = effective.date()
        except Exception:
            pass
    if effective and effective > today:
        return

    case = getattr(sanction, "case", None)
    respondent = getattr(case, "respondent", None)
    if respondent is None:
        return

    if getattr(respondent, "is_active", False):
        respondent.is_active = False
        respondent.save(update_fields=["is_active"])

    EmployeeProfile = apps.get_model("payroll", "EmployeeProfile")
    try:
        employee = EmployeeProfile.objects.get(user=respondent)
    except EmployeeProfile.DoesNotExist:
        return

    if employee.status != "terminated":
        employee.status = "terminated"
        employee.save(update_fields=["status"])
