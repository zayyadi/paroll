from __future__ import annotations

from typing import TYPE_CHECKING

from payroll.models import PayrollRunEntry

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from payroll.models import PayrollRunEntry


def resolve_payslip_run_entry(identifier: int) -> PayrollRunEntry | None:
    """
    Resolve a payslip request to its canonical PayrollRunEntry.

    Historically the app has passed three different ids around for payslip
    routes: PayrollRunEntry.id, PayrollEntry.id, and EmployeeProfile.id. This
    resolver keeps those legacy links working while we standardize templates on
    the actual PayrollRunEntry primary key.
    """

    base_queryset: QuerySet[PayrollRunEntry] = PayrollRunEntry.objects.select_related(
        "payroll_run",
        "payroll_entry__pays__user",
    )

    payslip = base_queryset.filter(id=identifier).first()
    if payslip is not None:
        return payslip

    payslip = (
        base_queryset.filter(payroll_entry_id=identifier)
        .order_by("-payroll_run__paydays")
        .first()
    )
    if payslip is not None:
        return payslip

    payslip = (
        base_queryset.filter(payroll_entry__pays__id=identifier)
        .order_by("-payroll_run__paydays")
        .first()
    )
    return payslip
