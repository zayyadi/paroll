"""Payroll accounting service - journal entries for payroll closure, IOU approval, etc.

Extracted from payroll/signals.py to keep signal handlers thin.
"""

from decimal import Decimal
import logging
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from accounting.models import Account, AccountingAuditTrail, Journal
from accounting.utils import (
    create_journal_with_entries,
    get_or_create_fiscal_year,
    get_or_create_period,
    log_accounting_activity,
)

from payroll.models import IOU, PayrollRun, IOUDeduction

logger = logging.getLogger(__name__)


PAYROLL_ACCOUNTS = {
    "salary_expense": ("Salaries and Wages Expense", "EXPENSE", "6010"),
    "allowance_expense": ("Allowances Expense", "EXPENSE", "6015"),
    "pension_expense": ("Pension Expense (Employer)", "EXPENSE", "6020"),
    "health_expense": ("Health Contribution Expense (Employer)", "EXPENSE", "6030"),
    "nsitf_expense": ("NSITF Expense", "EXPENSE", "6040"),
    "cash": ("Cash and Cash Equivalents", "ASSET", "1100"),
    "bank": ("Bank Accounts", "ASSET", "1020"),
    "employee_advances": ("Employee Advances", "ASSET", "1400"),
    "paye_payable": ("PAYE Tax Payable", "LIABILITY", "2110"),
    "pension_payable": ("Pension Payable", "LIABILITY", "2120"),
    "health_payable": ("Health Contribution Payable", "LIABILITY", "2130"),
    "nsitf_payable": ("NSITF Payable", "LIABILITY", "2140"),
    "nhf_payable": ("NHF Payable", "LIABILITY", "2150"),
    "deductions_payable": ("Other Deductions Payable", "LIABILITY", "2160"),
    "interest_income": ("Interest Income", "REVENUE", "4110"),
}


def _get_payroll_account(
    company: Any,
    name: str,
    account_type: str,
    account_number: str,
) -> Account:
    account = Account.objects.filter(company=company, account_number=account_number).first()
    if not account:
        account = Account.objects.filter(company=company, name=name).first()

    if account:
        updated_fields = []
        if (
            account.account_number != account_number
            and not Account.objects.filter(
                company=company, account_number=account_number
            ).exclude(pk=account.pk).exists()
        ):
            account.account_number = account_number
            updated_fields.append("account_number")
        if account.type != account_type:
            account.type = account_type
            updated_fields.append("type")
        if (
            account.name != name
            and not Account.objects.filter(company=company, name=name)
            .exclude(pk=account.pk)
            .exists()
        ):
            account.name = name
            updated_fields.append("name")
        if updated_fields:
            account.save(update_fields=updated_fields)
        return account

    account = Account.objects.create(
        company=company,
        name=name,
        account_number=account_number,
        type=account_type,
    )
    return account


def get_account(company: Any, account_key: str) -> Account | None:
    if account_key in PAYROLL_ACCOUNTS:
        name, account_type, account_number = PAYROLL_ACCOUNTS[account_key]
        return _get_payroll_account(company, name, account_type, account_number)
    return None


def source_journal_exists(
    source_object: Any,
    description_prefix: str,
    company: Any = None,
) -> bool:
    if not source_object or not getattr(source_object, "pk", None):
        return False
    source_ct = ContentType.objects.get_for_model(source_object.__class__)
    return Journal.objects.filter(
        company=company,
        content_type=source_ct,
        object_id=source_object.pk,
        description__startswith=description_prefix,
    ).exists()


def handle_payroll_period_closure(payroll_run: PayrollRun) -> None:
    """
    Create comprehensive journal entries when a payroll period is closed.
    Implements proper double-entry bookkeeping for all payroll transactions.
    """
    company = payroll_run.company
    if source_journal_exists(payroll_run, "Payroll for period:", company=company):
        return

    with transaction.atomic():
        pay_run_entries = payroll_run.payroll_run_entries.select_related(
            "payroll_entry__pays__employee_pay"
        )
        if not pay_run_entries.exists():
            raise ValueError("Cannot close a payroll period with no employees.")

        fiscal_year = get_or_create_fiscal_year(payroll_run.paydays.year, company=company)
        period = get_or_create_period(fiscal_year, payroll_run.paydays.month, company=company)

        aggregate_entries = {}

        def _add_entry(
            account_key: str,
            entry_type: str,
            amount: Any,
            memo: str,
        ) -> None:
            amount = Decimal(amount or 0)
            if amount <= 0:
                return
            account = get_account(company, account_key)
            if account is None:
                return
            key = (account.id, entry_type, memo)
            if key not in aggregate_entries:
                aggregate_entries[key] = {
                    "account": account,
                    "entry_type": entry_type,
                    "amount": Decimal("0.00"),
                    "memo": memo,
                }
            aggregate_entries[key]["amount"] += amount

        for pay_run_entry in pay_run_entries:
            pay_var = pay_run_entry.payroll_entry
            employee = pay_var.pays
            employee_payroll = employee.employee_pay
            if not employee_payroll:
                continue

            employee_name = f"{employee.first_name} {employee.last_name}".strip()

            payee = Decimal(employee_payroll.payee or 0)
            pension_employee = Decimal(employee_payroll.pension_employee or 0) / Decimal("12")
            nhf = Decimal(employee_payroll.nhf or 0) / Decimal("12")
            employee_health = Decimal(employee_payroll.employee_health or 0) / Decimal("12")

            other_deduction = Decimal("0.00")
            for deduction in employee.deductions.filter(
                created_at__month=payroll_run.paydays.month,
                created_at__year=payroll_run.paydays.year,
            ):
                if deduction.deduction_type != "IOU":
                    amount = Decimal(deduction.amount or 0)
                    other_deduction += amount
                    _add_entry(
                        "deductions_payable",
                        "CREDIT",
                        amount,
                        f"Other deduction payable - {employee_name}",
                    )

            iou_repayment = Decimal("0.00")
            for iou_deduction in employee.iou_deductions.filter(
                payday__paydays__month=payroll_run.paydays.month,
                payday__paydays__year=payroll_run.paydays.year,
            ):
                amount = Decimal(iou_deduction.amount or 0)
                iou_repayment += amount
                _add_entry(
                    "employee_advances",
                    "CREDIT",
                    amount,
                    f"IOU recovery - {employee_name}",
                )

            _add_entry("paye_payable", "CREDIT", payee, f"PAYE payable - {employee_name}")
            _add_entry(
                "pension_payable",
                "CREDIT",
                pension_employee,
                f"Employee pension payable - {employee_name}",
            )
            _add_entry("nhf_payable", "CREDIT", nhf, f"NHF payable - {employee_name}")
            _add_entry(
                "health_payable",
                "CREDIT",
                employee_health,
                f"Employee health payable - {employee_name}",
            )

            employee_liability_total = (
                payee + pension_employee + nhf + employee_health
                + other_deduction + iou_repayment
            )

            allowance = Decimal(pay_var.calc_allowance or 0)
            net_pay = Decimal(pay_var.netpay or 0)
            _add_entry("cash", "CREDIT", net_pay, f"Net salary payment - {employee_name}")
            _add_entry(
                "allowance_expense",
                "DEBIT",
                allowance,
                f"Allowance expense - {employee_name}",
            )
            _add_entry(
                "salary_expense",
                "DEBIT",
                net_pay - allowance + employee_liability_total,
                f"Gross salary expense - {employee_name}",
            )

            pension_employer = Decimal(employee_payroll.pension_employer or 0) / Decimal("12")
            employer_health = Decimal(employee_payroll.emplyr_health or 0) / Decimal("12")
            nsitf = Decimal(employee_payroll.nsitf or 0) / Decimal("12")

            _add_entry(
                "pension_expense",
                "DEBIT",
                pension_employer,
                f"Employer pension expense - {employee_name}",
            )
            _add_entry(
                "pension_payable",
                "CREDIT",
                pension_employer,
                f"Employer pension payable - {employee_name}",
            )
            _add_entry(
                "health_expense",
                "DEBIT",
                employer_health,
                f"Employer health expense - {employee_name}",
            )
            _add_entry(
                "health_payable",
                "CREDIT",
                employer_health,
                f"Employer health payable - {employee_name}",
            )
            _add_entry("nsitf_expense", "DEBIT", nsitf, f"NSITF expense - {employee_name}")
            _add_entry("nsitf_payable", "CREDIT", nsitf, f"NSITF payable - {employee_name}")

        entries = list(aggregate_entries.values())

        if entries:
            paydays_value = payroll_run.paydays
            if hasattr(paydays_value, "first_day"):
                journal_date = paydays_value.first_day()
            elif paydays_value:
                journal_date = paydays_value.replace(day=1)
            else:
                journal_date = timezone.now().date().replace(day=1)

            journal = create_journal_with_entries(
                company=company,
                date=journal_date,
                description=f"Payroll for period: {payroll_run.save_month_str}",
                entries=entries,
                fiscal_year=fiscal_year,
                period=period,
                source_object=payroll_run,
                auto_post=True,
                validate_balances=False,
            )

            log_accounting_activity(
                user=None,
                action=AccountingAuditTrail.ActionType.POST,
                instance=journal,
                reason=f"Payroll period {payroll_run.save_month_str} closed",
            )


def handle_iou_approval_accounting(iou: IOU) -> None:
    """Create journal entries when an IOU is approved."""
    company = iou.employee_id.company
    if source_journal_exists(iou, "IOU approved for", company=company):
        return

    approval_date = iou.approved_at or timezone.now().date()
    fiscal_year = get_or_create_fiscal_year(approval_date.year, company=company)
    period = get_or_create_period(fiscal_year, approval_date.month, company=company)

    employee_name = f"{iou.employee_id.first_name} {iou.employee_id.last_name}".strip()

    entries = [
        {
            "account": get_account(company, "employee_advances"),
            "entry_type": "DEBIT",
            "amount": iou.amount,
            "memo": f"IOU approved for {employee_name}",
        },
        {
            "account": get_account(company, "cash"),
            "entry_type": "CREDIT",
            "amount": iou.amount,
            "memo": f"Cash paid for IOU to {employee_name}",
        },
    ]

    journal = create_journal_with_entries(
        company=company,
        date=approval_date,
        description=f"IOU approved for {employee_name}",
        entries=entries,
        fiscal_year=fiscal_year,
        period=period,
        source_object=iou,
        auto_post=True,
        validate_balances=False,
    )

    log_accounting_activity(
        user=None,
        action=AccountingAuditTrail.ActionType.APPROVE,
        instance=journal,
        reason=f"IOU approved for {employee_name}",
    )


def handle_iou_direct_payment_accounting(iou: IOU) -> None:
    """Create journal entries when an IOU is fully paid by direct payment."""
    company = iou.employee_id.company
    if source_journal_exists(iou, "IOU paid (direct) by", company=company):
        return

    payment_date = timezone.now().date()
    fiscal_year = get_or_create_fiscal_year(payment_date.year, company=company)
    period = get_or_create_period(fiscal_year, payment_date.month, company=company)

    principal_amount = Decimal(iou.amount or 0)
    total_repayment = Decimal(iou.total_amount or 0)
    interest_amount = total_repayment - principal_amount

    employee_name = f"{iou.employee_id.first_name} {iou.employee_id.last_name}".strip()

    entries = [
        {
            "account": get_account(company, "cash"),
            "entry_type": "DEBIT",
            "amount": total_repayment,
            "memo": f"Direct IOU repayment received from {employee_name}",
        },
        {
            "account": get_account(company, "employee_advances"),
            "entry_type": "CREDIT",
            "amount": principal_amount,
            "memo": f"IOU principal cleared for {employee_name}",
        },
    ]

    if interest_amount > 0:
        entries.append({
            "account": get_account(company, "interest_income"),
            "entry_type": "CREDIT",
            "amount": interest_amount,
            "memo": f"IOU interest income from {employee_name}",
        })

    journal = create_journal_with_entries(
        company=company,
        date=payment_date,
        description=f"IOU paid (direct) by {employee_name}",
        entries=entries,
        fiscal_year=fiscal_year,
        period=period,
        source_object=iou,
        auto_post=True,
        validate_balances=False,
    )
    log_accounting_activity(
        user=None,
        action=AccountingAuditTrail.ActionType.POST,
        instance=journal,
        reason=f"Direct IOU repayment posted for IOU {iou.pk}",
    )


def create_iou_deduction_for_payroll_entry(
    payroll_run_entry: Any,
) -> IOUDeduction | None:
    """
    For each payroll run entry, create month's IOU deduction from net pay
    using the approved repayment percentage for approved salary-deduction IOUs.
    """
    payroll_run = payroll_run_entry.payroll_run
    payroll_entry = payroll_run_entry.payroll_entry
    employee = payroll_entry.pays
    if not employee:
        return

    month_anchor = getattr(payroll_run, "paydays", None)
    if not month_anchor:
        return

    month_start = month_anchor.replace(day=1)

    ious = IOU.objects.filter(
        employee_id=employee,
        status="APPROVED",
        payment_method="SALARY_DEDUCTION",
        approved_at__isnull=False,
        approved_at__lte=month_start,
    ).order_by("approved_at", "id")

    monthly_netpay = Decimal(employee.net_pay or Decimal("0.00"))
    if monthly_netpay <= 0:
        monthly_netpay = Decimal(payroll_entry.netpay or Decimal("0.00"))
    if monthly_netpay <= 0 and employee.employee_pay:
        monthly_netpay = Decimal(employee.employee_pay.basic_salary or Decimal("0.00"))

    for iou in ious:
        if IOUDeduction.objects.filter(iou=iou, payday=payroll_run).exists():
            continue

        outstanding = iou.outstanding_amount
        if outstanding <= 0:
            if iou.status != "PAID":
                iou.status = "PAID"
                iou.save(update_fields=["status"])
            continue

        repayment_percent = Decimal(iou.repayment_deduction_percentage or Decimal("0.00"))
        if repayment_percent <= 0 or monthly_netpay <= 0:
            continue

        monthly_cap = (monthly_netpay * repayment_percent) / Decimal("100")
        deduction_amount = min(outstanding, monthly_cap)
        if deduction_amount <= 0:
            continue

        IOUDeduction.objects.create(
            iou=iou,
            employee=employee,
            payday=payroll_run,
            amount=deduction_amount,
        )

        if deduction_amount >= outstanding:
            iou.status = "PAID"
            iou.save(update_fields=["status"])

    payroll_entry.save()
