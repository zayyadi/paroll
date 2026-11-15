from __future__ import annotations

from typing import TYPE_CHECKING, Any

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


def can_view_payslip(user: Any, payslip: PayrollRunEntry) -> bool:
    """
    Object-level access check for a single payslip.

    Employees may always view their own payslip, even after switching company
    context. Payroll viewers and auditors may only view payslips belonging to
    their active company; a payslip with no resolvable company is denied.
    """
    from accounting.permissions import is_auditor
    from company.utils import get_user_company

    employee = payslip.payroll_entry.pays
    if employee.user_id is not None and employee.user_id == user.pk:
        return True

    if not (user.has_perm("payroll.view_payroll") or is_auditor(user)):
        return False

    payslip_company_id = employee.company_id or payslip.payroll_entry.company_id
    user_company = get_user_company(user)
    return (
        payslip_company_id is not None
        and user_company is not None
        and payslip_company_id == user_company.pk
    )


def queue_payslip_emails(payroll_run: Any) -> Any:
    """
    Queue payslip email delivery for after the current transaction commits.

    Called when a run is locked (payroll.financial_approval_actions.apply_run),
    so employees only receive payslips for approved pay. PDF rendering and SMTP
    delivery happen in Celery.
    """
    from django.db import transaction

    from payroll.models import PayslipEmailJob

    if not payroll_run or not getattr(payroll_run, "pk", None):
        return None
    job = PayslipEmailJob.objects.create(payroll_run=payroll_run)
    transaction.on_commit(lambda: job.enqueue())
    return job
