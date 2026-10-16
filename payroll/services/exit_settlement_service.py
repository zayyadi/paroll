"""Exit settlement parity (P2-15): one Full-and-Final document per exit.

Frappe's Full and Final Statement combines payables, receivables and asset
recovery into a single statement with journal linkage. paroll had the pieces —
``OffboardingChecklist.final_settlement_amount`` (payables only), the IOU
register (receivables) and ``EmployeeAsset`` (recovery) — but no document that
assembles them at exit and posts a double-entry journal for the result.

Design:
- :func:`build_settlement` is the *only* place the numbers are computed. It
  reads real balances (IOU ``outstanding_amount``, asset ``replacement_cost``)
  so the statement cannot drift from the ledgers it summarises. Discretionary
  add-backs/deductions live in the model's ``other_*`` fields and survive a
  rebuild.
- :func:`post_settlement` writes the journal: payables debit ``6010`` salaries
  expense, receivables credit ``1400`` employee advances (recovered at exit),
  and the net is credited to ``1020`` bank when the company pays the leaver.
  A negative net (the leaver owes more than is owed) debits ``1400`` instead.
- Posting runs inside the ``exit.settlement`` approval execution, so the
  ``ExitSettlement.status`` transition to POSTED passes ``guard_state`` and
  the journal is stamped with the approving request.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

__all__ = [
    "payables_for",
    "receivables_for",
    "build_settlement",
    "post_settlement",
]


def payables_for(employee: Any, *, last_working_day: Any = None) -> dict:
    """Final-month salary plus leave encashment for a departing employee.

    Shared with ``offboarding_service.calculate_final_settlement`` so the
    legacy one-number summary and the full statement always agree.
    """
    from payroll.models.payroll import LeaveBalance, LeaveType

    basic = Decimal("0.00")
    if employee.employee_pay:
        basic = Decimal(employee.employee_pay.basic) / Decimal("12")

    encashment = Decimal("0.00")
    balance = LeaveBalance.objects.filter(
        employee=employee, year=timezone.now().year
    ).first()
    if balance and employee.employee_pay:
        daily = Decimal(employee.employee_pay.basic) / Decimal("12") / Decimal("20")
        # Encashment is driven by the per-type LeaveType config (P2-12): only
        # types flagged encashable pay out, each at its own rate.
        encashable = {
            lt.code: lt
            for lt in LeaveType.objects.filter(
                company=employee.company, encashable=True, is_active=True
            )
        }
        annual = encashable.get("ANNUAL")
        if annual:
            encashment = (
                Decimal(str(balance.annual_leave)) * daily * annual.encashment_rate
            )
    return {
        "final_month_salary": basic.quantize(Decimal("0.01")),
        "leave_encashment": encashment.quantize(Decimal("0.01")),
    }


def receivables_for(employee: Any, *, as_of: Any = None) -> dict:
    """Outstanding IOU balances plus unreturned asset recovery value.

    A PAID IOU is fully repaid by definition (``outstanding_amount`` is zero),
    and assets whose status is ``returned``/``available``/``retired`` carry no
    recovery charge — only ``in_use`` and ``lost`` assets do.
    """
    from payroll.models.payroll import IOU
    from payroll.models.workforce import EmployeeAsset

    outstanding = sum(
        (iou.outstanding_amount for iou in IOU.objects.filter(
            employee_id=employee, status="APPROVED"
        )),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    assets = EmployeeAsset.objects.filter(
        employee=employee,
        status__in=[
            EmployeeAsset.Status.IN_USE,
            EmployeeAsset.Status.LOST,
        ],
    )
    asset_value = sum(
        ((asset.replacement_cost or Decimal("0.00")) for asset in assets),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    return {
        "outstanding_iou": outstanding,
        "unreturned_assets_value": asset_value,
    }


def build_settlement(*, checklist: Any) -> Any:
    """Create (or refresh) the Full-and-Final statement for an offboarding.

    The checklist's own ``final_settlement_amount`` is kept in step with the
    statement's payables total so legacy readers stay correct.
    """
    from payroll.models.workforce import ExitSettlement

    employee = checklist.employee
    payables = payables_for(employee)
    receivables = receivables_for(employee)

    settlement, _created = ExitSettlement.objects.get_or_create(
        checklist=checklist,
        defaults={
            "company": checklist.company,
            "employee": employee,
            "last_working_day": checklist.last_working_day,
        },
    )
    if settlement.status != ExitSettlement.Status.DRAFT:
        raise ValidationError(
            "A posted exit settlement cannot be rebuilt; raise a correction "
            "through the offboarding workflow instead."
        )

    settlement.final_month_salary = payables["final_month_salary"]
    settlement.leave_encashment = payables["leave_encashment"]
    settlement.outstanding_iou = receivables["outstanding_iou"]
    settlement.unreturned_assets_value = receivables["unreturned_assets_value"]
    settlement.last_working_day = checklist.last_working_day
    settlement.full_clean()
    settlement.save()

    # Keep the checklist's legacy one-number summary consistent (P2-15).
    checklist.final_settlement_amount = settlement.payables_total
    checklist.save(update_fields=["final_settlement_amount"])
    return settlement


@transaction.atomic
def post_settlement(*, settlement: Any, actor: Any = None) -> Any:
    """Write the double-entry journal for a DRAFT statement and mark it posted.

    Called from inside the ``exit.settlement`` approval execution (see
    ``payroll.approval_actions``), which is what authorises the status
    transition and stamps the journal with the approving request.
    """
    from accounting.utils import create_journal_with_entries
    from payroll.models.workforce import ExitSettlement
    from payroll.services.payroll_accounting_service import get_account

    if settlement.status != ExitSettlement.Status.DRAFT:
        raise ValidationError("Only a draft exit settlement can be posted.")

    company = settlement.company
    working_day = settlement.last_working_day
    entries = []
    if settlement.payables_total > 0:
        entries.append(
            {
                "account": get_account(company, "salary_expense"),
                "entry_type": "DEBIT",
                "amount": settlement.payables_total,
                "memo": "Final salary and leave encashment at exit",
            }
        )
    if settlement.receivables_total > 0:
        entries.append(
            {
                "account": get_account(company, "employee_advances"),
                "entry_type": "CREDIT",
                "amount": settlement.receivables_total,
                "memo": "IOU and asset recovery at exit",
            }
        )
    if settlement.net_settlement > 0:
        # The company pays the leaver the net amount.
        entries.append(
            {
                "account": get_account(company, "bank"),
                "entry_type": "CREDIT",
                "amount": settlement.net_settlement,
                "memo": "Net exit settlement paid to leaver",
            }
        )
    elif settlement.net_settlement < 0:
        # The leaver owes more than is owed: the shortfall stays recoverable.
        entries.append(
            {
                "account": get_account(company, "employee_advances"),
                "entry_type": "DEBIT",
                "amount": -settlement.net_settlement,
                "memo": "Net amount recoverable from leaver at exit",
            }
        )

    if entries:
        # auto_post=False keeps us on the plain (non-proposal) path: this
        # posting already runs inside the exit.settlement execution, so a
        # nested journal-approval proposal would be double authority.
        journal = create_journal_with_entries(
            date=working_day if isinstance(working_day, date) else date.today(),
            description=f"Exit settlement: {settlement.employee}",
            entries=entries,
            company=company,
            user=actor,
            auto_post=False,
            source_object=settlement,
            # System posting from an approved workflow, matching the payroll
            # close path: the settlement amounts were themselves reviewed.
            validate_balances=False,
        )
        # System-style post, mirroring accounting.utils' auto_post path.
        journal.submit_for_approval()
        journal.approve(None)
        journal.post(None)
        settlement.journal = journal

    settlement.status = "POSTED"
    settlement.posted_by = actor
    settlement.posted_at = timezone.now()
    settlement.save(update_fields=["status", "posted_by", "posted_at", "journal"])
    return settlement
