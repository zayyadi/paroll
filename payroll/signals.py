from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
import logging
from decimal import Decimal

# from django.contrib.contenttypes.models import ContentType

from accounting.models import Account, AccountingAuditTrail, Journal
from accounting.utils import (
    create_journal_with_entries,
    get_or_create_fiscal_year,
    get_or_create_period,
    log_accounting_activity,
)
from .models import (
    PayrollRun,
    IOU,
    Allowance,
    Deduction,
    IOUDeduction,
)

# from .models.employee_profile import EmployeeProfile

User = get_user_model()
logger = logging.getLogger(__name__)


def _deduction_debug_print(message: str) -> None:
    logger.debug("[DEDUCTION_DEBUG] %s", message)


# Helper function to get or create payroll accounts
def get_payroll_account(name, account_type, account_number):
    """Get or create a payroll account with the specified details."""
    account = Account.objects.filter(account_number=account_number).first()
    if not account:
        account = Account.objects.filter(name=name).first()

    if account:
        updated_fields = []
        # Normalize account number to configured mapping when possible.
        if (
            account.account_number != account_number
            and not Account.objects.filter(account_number=account_number).exclude(
                pk=account.pk
            ).exists()
        ):
            account.account_number = account_number
            updated_fields.append("account_number")
        if account.type != account_type:
            account.type = account_type
            updated_fields.append("type")
        if account.name != name and not Account.objects.filter(name=name).exclude(
            pk=account.pk
        ).exists():
            account.name = name
            updated_fields.append("name")
        if updated_fields:
            account.save(update_fields=updated_fields)
        return account

    account = Account.objects.create(
        name=name,
        account_number=account_number,
        type=account_type,
    )
    return account


# Payroll account mappings
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


def get_account(account_key):
    """Get a payroll account by key."""
    if account_key in PAYROLL_ACCOUNTS:
        name, account_type, account_number = PAYROLL_ACCOUNTS[account_key]
        return get_payroll_account(name, account_type, account_number)
    return None


def source_journal_exists(source_object, description_prefix):
    """Check if a journal already exists for this source object + description prefix."""
    if not source_object or not getattr(source_object, "pk", None):
        return False
    source_ct = ContentType.objects.get_for_model(source_object.__class__)
    return Journal.objects.filter(
        content_type=source_ct,
        object_id=source_object.pk,
        description__startswith=description_prefix,
    ).exists()


@receiver(pre_save, sender=PayrollRun)
def handle_payroll_period_closure(sender, instance, **kwargs):
    """
    Create comprehensive journal entries when a payroll period is closed.
    Implements proper double-entry bookkeeping for all payroll transactions.
    """
    if not instance.pk:
        return

    try:
        old_instance = PayrollRun.objects.get(pk=instance.pk)
    except PayrollRun.DoesNotExist:
        return

    # Trigger only when 'closed' changes from False to True
    if not old_instance.closed and instance.closed:
        if source_journal_exists(instance, "Payroll for period:"):
            return
        with transaction.atomic():
            pay_run_entries = instance.payroll_run_entries.select_related(
                "payroll_entry__pays__employee_pay"
            )
            if not pay_run_entries.exists():
                raise ValueError("Cannot close a payroll period with no employees.")

            # Get fiscal year and period
            fiscal_year = get_or_create_fiscal_year(instance.paydays.year)
            period = get_or_create_period(fiscal_year, instance.paydays.month)
            # Build a balanced payroll journal with clear Nigerian payroll liability mapping.
            # Employee-side items (PAYE/Pension/NHF/Health/Other deductions/IOU deductions)
            # are credited to payable/recovery accounts, cash gets net pay, and salary expense
            # is debited for net pay + employee deductions.
            aggregate_entries = {}

            def add_entry(account_key, entry_type, amount, memo):
                amount = Decimal(amount or 0)
                if amount <= 0:
                    return
                account = get_account(account_key)
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

                # Employee liabilities (monthly equivalents where base figures are annualized)
                payee = Decimal(employee_payroll.payee or 0)
                pension_employee = Decimal(employee_payroll.pension_employee or 0) / Decimal("12")
                nhf = Decimal(employee_payroll.nhf or 0)
                employee_health = Decimal(employee_payroll.employee_health or 0)

                other_deduction = Decimal("0.00")
                for deduction in employee.deductions.filter(
                    created_at__month=instance.paydays.month,
                    created_at__year=instance.paydays.year,
                ):
                    if deduction.deduction_type != "IOU":
                        amount = Decimal(deduction.amount or 0)
                        other_deduction += amount
                        _deduction_debug_print(
                            f"Payroll closure deduction: employee={employee_name}, "
                            f"deduction_id={deduction.id}, type={deduction.deduction_type}, amount={amount}."
                        )
                        add_entry(
                            "deductions_payable",
                            "CREDIT",
                            amount,
                            f"Other deduction payable - {employee_name}",
                        )

                iou_repayment = Decimal("0.00")
                for iou_deduction in employee.iou_deductions.filter(
                    payday__paydays__month=instance.paydays.month,
                    payday__paydays__year=instance.paydays.year,
                ):
                    amount = Decimal(iou_deduction.amount or 0)
                    iou_repayment += amount
                    _deduction_debug_print(
                        f"Payroll closure IOU recovery: employee={employee_name}, "
                        f"iou_deduction_id={iou_deduction.id}, amount={amount}."
                    )
                    add_entry(
                        "employee_advances",
                        "CREDIT",
                        amount,
                        f"IOU recovery - {employee_name}",
                    )

                add_entry("paye_payable", "CREDIT", payee, f"PAYE payable - {employee_name}")
                add_entry(
                    "pension_payable",
                    "CREDIT",
                    pension_employee,
                    f"Employee pension payable - {employee_name}",
                )
                add_entry("nhf_payable", "CREDIT", nhf, f"NHF payable - {employee_name}")
                add_entry(
                    "health_payable",
                    "CREDIT",
                    employee_health,
                    f"Employee health payable - {employee_name}",
                )

                employee_liability_total = (
                    payee
                    + pension_employee
                    + nhf
                    + employee_health
                    + other_deduction
                    + iou_repayment
                )
                _deduction_debug_print(
                    f"Payroll closure liability rollup: employee={employee_name}, "
                    f"payee={payee}, pension_employee={pension_employee}, nhf={nhf}, "
                    f"employee_health={employee_health}, other_deduction={other_deduction}, "
                    f"iou_repayment={iou_repayment}, total={employee_liability_total}."
                )

                net_pay = Decimal(pay_var.netpay or 0)
                add_entry("cash", "CREDIT", net_pay, f"Net salary payment - {employee_name}")
                add_entry(
                    "salary_expense",
                    "DEBIT",
                    net_pay + employee_liability_total,
                    f"Gross salary expense - {employee_name}",
                )

                # Employer-side statutory contributions
                pension_employer = Decimal(employee_payroll.pension_employer or 0) / Decimal("12")
                employer_health = Decimal(employee_payroll.emplyr_health or 0)
                nsitf = Decimal(employee_payroll.nsitf or 0) / Decimal("12")

                add_entry(
                    "pension_expense",
                    "DEBIT",
                    pension_employer,
                    f"Employer pension expense - {employee_name}",
                )
                add_entry(
                    "pension_payable",
                    "CREDIT",
                    pension_employer,
                    f"Employer pension payable - {employee_name}",
                )
                add_entry(
                    "health_expense",
                    "DEBIT",
                    employer_health,
                    f"Employer health expense - {employee_name}",
                )
                add_entry(
                    "health_payable",
                    "CREDIT",
                    employer_health,
                    f"Employer health payable - {employee_name}",
                )
                add_entry(
                    "nsitf_expense",
                    "DEBIT",
                    nsitf,
                    f"NSITF expense - {employee_name}",
                )
                add_entry(
                    "nsitf_payable",
                    "CREDIT",
                    nsitf,
                    f"NSITF payable - {employee_name}",
                )

            entries = list(aggregate_entries.values())

            # Create the journal with all entries
            if entries:
                paydays_value = instance.paydays
                if hasattr(paydays_value, "first_day"):
                    journal_date = paydays_value.first_day()
                elif paydays_value:
                    journal_date = paydays_value.replace(day=1)
                else:
                    journal_date = timezone.now().date().replace(day=1)

                journal = create_journal_with_entries(
                    date=journal_date,
                    description=f"Payroll for period: {instance.save_month_str}",
                    entries=entries,
                    fiscal_year=fiscal_year,
                    period=period,
                    source_object=instance,
                    auto_post=True,
                    validate_balances=False,
                )

                # Log the payroll closure
                log_accounting_activity(
                    user=None,  # System generated
                    action=AccountingAuditTrail.ActionType.POST,
                    instance=journal,
                    reason=f"Payroll period {instance.save_month_str} closed",
                )


@receiver(pre_save, sender=IOU)
def handle_iou_approval(sender, instance, **kwargs):
    """
    Create journal entries when an IOU is approved.
    Debit: Employee Advances (Asset)
    Credit: Cash/Bank (Asset)
    """
    if not instance.pk:
        return

    try:
        old_instance = IOU.objects.get(pk=instance.pk)
    except IOU.DoesNotExist:
        return

    # Trigger only on status change to APPROVED
    if old_instance.status != "APPROVED" and instance.status == "APPROVED":
        if source_journal_exists(instance, "IOU approved for"):
            return
        try:
            with transaction.atomic():
                # Get fiscal year and period
                approval_date = instance.approved_at or timezone.now().date()
                fiscal_year = get_or_create_fiscal_year(approval_date.year)
                period = get_or_create_period(fiscal_year, approval_date.month)

                # Create journal entries
                entries = [
                    {
                        "account": get_account("employee_advances"),
                        "entry_type": "DEBIT",
                        "amount": instance.amount,
                        "memo": f"IOU approved for {instance.employee_id.first_name} {instance.employee_id.last_name}",
                    },
                    {
                        "account": get_account("cash"),
                        "entry_type": "CREDIT",
                        "amount": instance.amount,
                        "memo": f"Cash paid for IOU to {instance.employee_id.first_name} {instance.employee_id.last_name}",
                    },
                ]

                # Create the journal
                journal = create_journal_with_entries(
                    date=approval_date,
                    description=f"IOU approved for {instance.employee_id.first_name} {instance.employee_id.last_name}",
                    entries=entries,
                    fiscal_year=fiscal_year,
                    period=period,
                    source_object=instance,
                    auto_post=True,
                    validate_balances=False,
                )

                # Log the IOU approval
                log_accounting_activity(
                    user=None,  # System generated
                    action=AccountingAuditTrail.ActionType.APPROVE,
                    instance=journal,
                    reason=f"IOU approved for {instance.employee_id.first_name} {instance.employee_id.last_name}",
                )
        except ValidationError as exc:
            # Do not block IOU status transition when accounting balances are insufficient.
            logger.warning(
                "IOU approved without accounting journal for IOU %s due to validation error: %s",
                instance.pk,
                exc,
            )
        except Exception as exc:
            logger.exception(
                "Unexpected error while creating IOU approval journal for IOU %s: %s",
                instance.pk,
                exc,
            )


@receiver(pre_save, sender=IOU)
def handle_iou_direct_payment(sender, instance, **kwargs):
    """
    Create journal entries when an IOU is fully paid by direct payment.
    Debit: Cash/Bank (Asset)
    Credit: Employee Advances (Asset) for principal
    Credit: Interest Income (Revenue) for interest component, if any
    """
    if not instance.pk:
        return

    try:
        old_instance = IOU.objects.get(pk=instance.pk)
    except IOU.DoesNotExist:
        return

    status_changed_to_paid = old_instance.status != "PAID" and instance.status == "PAID"
    if not status_changed_to_paid or instance.payment_method != "DIRECT_PAYMENT":
        return

    if source_journal_exists(instance, "IOU paid (direct) by"):
        return

    payment_date = timezone.now().date()
    fiscal_year = get_or_create_fiscal_year(payment_date.year)
    period = get_or_create_period(fiscal_year, payment_date.month)

    principal_amount = Decimal(instance.amount or 0)
    total_repayment = Decimal(instance.total_amount or 0)
    interest_amount = total_repayment - principal_amount

    entries = [
        {
            "account": get_account("cash"),
            "entry_type": "DEBIT",
            "amount": total_repayment,
            "memo": f"Direct IOU repayment received from {instance.employee_id.first_name} {instance.employee_id.last_name}",
        },
        {
            "account": get_account("employee_advances"),
            "entry_type": "CREDIT",
            "amount": principal_amount,
            "memo": f"IOU principal cleared for {instance.employee_id.first_name} {instance.employee_id.last_name}",
        },
    ]

    if interest_amount > 0:
        entries.append(
            {
                "account": get_account("interest_income"),
                "entry_type": "CREDIT",
                "amount": interest_amount,
                "memo": f"IOU interest income from {instance.employee_id.first_name} {instance.employee_id.last_name}",
            }
        )

    try:
        journal = create_journal_with_entries(
            date=payment_date,
            description=f"IOU paid (direct) by {instance.employee_id.first_name} {instance.employee_id.last_name}",
            entries=entries,
            fiscal_year=fiscal_year,
            period=period,
            source_object=instance,
            auto_post=True,
            validate_balances=False,
        )
        log_accounting_activity(
            user=None,
            action=AccountingAuditTrail.ActionType.POST,
            instance=journal,
            reason=f"Direct IOU repayment posted for IOU {instance.pk}",
        )
    except Exception as exc:
        logger.exception(
            "Unexpected error while creating IOU direct-payment journal for IOU %s: %s",
            instance.pk,
            exc,
        )


@receiver(post_save, sender=IOUDeduction)
def handle_iou_repayment(sender, instance, created, **kwargs):
    """
    IOU repayment posting is recognized at payroll period closure for proper
    salary-period matching and to avoid duplicate postings.
    """
    if created:
        _deduction_debug_print(
            f"IOU deduction created: id={instance.id}, employee_id={instance.employee_id}, "
            f"iou_id={instance.iou_id}, amount={instance.amount}, payday={instance.payday_id}."
        )
    else:
        _deduction_debug_print(
            f"IOU deduction updated: id={instance.id}, employee_id={instance.employee_id}, "
            f"iou_id={instance.iou_id}, amount={instance.amount}, payday={instance.payday_id}."
        )
    return


@receiver(post_save, sender=Allowance)
def handle_allowance_creation(sender, instance, created, **kwargs):
    """
    Allowance posting is recognized at payroll period closure for proper
    salary-period matching and to avoid duplicate postings.
    """
    return


@receiver(post_save, sender=Deduction)
def handle_deduction_creation(sender, instance, created, **kwargs):
    """
    Deduction posting is recognized at payroll period closure for proper
    salary-period matching and to avoid duplicate postings.
    """
    action = "created" if created else "updated"
    _deduction_debug_print(
        f"Deduction {action}: id={instance.id}, employee_id={instance.employee_id}, "
        f"type={instance.deduction_type}, amount={instance.amount}, reason={instance.reason or ''}."
    )
    return
