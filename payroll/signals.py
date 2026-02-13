from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

# from django.contrib.contenttypes.models import ContentType

from accounting.models import Account, AccountingAuditTrail
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


# Helper function to get or create payroll accounts
def get_payroll_account(name, account_type, account_number):
    """Get or create a payroll account with the specified details."""
    account, created = Account.objects.get_or_create(
        account_number=account_number,
        defaults={
            "name": name,
            "type": account_type,
        },
    )
    return account


# Payroll account mappings
PAYROLL_ACCOUNTS = {
    "salary_expense": ("Salaries and Wages Expense", "EXPENSE", "6010"),
    "allowance_expense": ("Allowances Expense", "EXPENSE", "6015"),
    "pension_expense": ("Pension Expense (Employer)", "EXPENSE", "6020"),
    "health_expense": ("Health Contribution Expense (Employer)", "EXPENSE", "6030"),
    "nsitf_expense": ("NSITF Expense", "EXPENSE", "6040"),
    "cash": ("Cash and Cash Equivalents", "ASSET", "1010"),
    "bank": ("Bank Accounts", "ASSET", "1020"),
    "employee_advances": ("Employee Advances", "ASSET", "1400"),
    "paye_payable": ("PAYE Tax Payable", "LIABILITY", "2110"),
    "pension_payable": ("Pension Payable", "LIABILITY", "2120"),
    "health_payable": ("Health Contribution Payable", "LIABILITY", "2130"),
    "nsitf_payable": ("NSITF Payable", "LIABILITY", "2140"),
    "nhf_payable": ("NHF Payable", "LIABILITY", "2150"),
    "deductions_payable": ("Other Deductions Payable", "LIABILITY", "2160"),
}


def get_account(account_key):
    """Get a payroll account by key."""
    if account_key in PAYROLL_ACCOUNTS:
        name, account_type, account_number = PAYROLL_ACCOUNTS[account_key]
        return get_payroll_account(name, account_type, account_number)
    return None


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
        with transaction.atomic():
            pay_vars_in_period = instance.payroll_payday.all()
            if not pay_vars_in_period.exists():
                raise ValueError("Cannot close a payroll period with no employees.")

            # Get fiscal year and period
            fiscal_year = get_or_create_fiscal_year(instance.paydays.year)
            period = get_or_create_period(fiscal_year, instance.paydays.month)

            # Initialize aggregate totals
            total_debits = []
            total_credits = []

            # Aggregate all payroll components
            for pay_var in pay_vars_in_period:
                employee = pay_var.pays
                employee_payroll = employee.employee_pay

                # Salary payments (Debit: Salary Expense, Credit: Cash/Bank)
                gross_salary = (
                    employee_payroll.basic
                    + employee_payroll.housing
                    + employee_payroll.transport
                    + employee_payroll.bht
                )
                if gross_salary > 0:
                    total_debits.append(
                        {
                            "account": get_account("salary_expense"),
                            "amount": gross_salary,
                            "memo": f"Salary for {employee.first_name} {employee.last_name}",
                        }
                    )
                    total_credits.append(
                        {
                            "account": get_account("cash"),
                            "amount": gross_salary,
                            "memo": f"Salary payment for {employee.first_name} {employee.last_name}",
                        }
                    )

                # Allowances (Debit: Allowance Expense, Credit: Cash/Bank)
                allowance_total = pay_var.calc_allowance
                if allowance_total > 0:
                    total_debits.append(
                        {
                            "account": get_account("allowance_expense"),
                            "amount": allowance_total,
                            "memo": f"Allowances for {employee.first_name} {employee.last_name}",
                        }
                    )
                    total_credits.append(
                        {
                            "account": get_account("cash"),
                            "amount": allowance_total,
                            "memo": f"Allowance payment for {employee.first_name} {employee.last_name}",
                        }
                    )

                # Employer contributions (Debit: Expense, Credit: Liability)
                if employee_payroll.pension_employer > 0:
                    total_debits.append(
                        {
                            "account": get_account("pension_expense"),
                            "amount": employee_payroll.pension_employer,
                            "memo": f"Employer pension contribution for {employee.first_name} {employee.last_name}",
                        }
                    )
                    total_credits.append(
                        {
                            "account": get_account("pension_payable"),
                            "amount": employee_payroll.pension_employer,
                            "memo": f"Employer pension liability for {employee.first_name} {employee.last_name}",
                        }
                    )

                if pay_var.emplyr_health > 0:
                    total_debits.append(
                        {
                            "account": get_account("health_expense"),
                            "amount": pay_var.emplyr_health,
                            "memo": f"Employer health contribution for {employee.first_name} {employee.last_name}",
                        }
                    )
                    total_credits.append(
                        {
                            "account": get_account("health_payable"),
                            "amount": pay_var.emplyr_health,
                            "memo": f"Employer health liability for {employee.first_name} {employee.last_name}",
                        }
                    )

                if employee_payroll.nsitf > 0:
                    total_debits.append(
                        {
                            "account": get_account("nsitf_expense"),
                            "amount": employee_payroll.nsitf,
                            "memo": f"NSITF contribution for {employee.first_name} {employee.last_name}",
                        }
                    )
                    total_credits.append(
                        {
                            "account": get_account("nsitf_payable"),
                            "amount": employee_payroll.nsitf,
                            "memo": f"NSITF liability for {employee.first_name} {employee.last_name}",
                        }
                    )

                # Employee deductions (Debit: Salary Expense, Credit: Various Liability Accounts)
                if employee_payroll.payee > 0:
                    total_debits.append(
                        {
                            "account": get_account("salary_expense"),
                            "amount": employee_payroll.payee,
                            "memo": f"PAYE tax for {employee.first_name} {employee.last_name}",
                        }
                    )
                    total_credits.append(
                        {
                            "account": get_account("paye_payable"),
                            "amount": employee_payroll.payee,
                            "memo": f"PAYE tax liability for {employee.first_name} {employee.last_name}",
                        }
                    )

                if employee_payroll.pension_employee > 0:
                    total_debits.append(
                        {
                            "account": get_account("salary_expense"),
                            "amount": employee_payroll.pension_employee,
                            "memo": f"Employee pension for {employee.first_name} {employee.last_name}",
                        }
                    )
                    total_credits.append(
                        {
                            "account": get_account("pension_payable"),
                            "amount": employee_payroll.pension_employee,
                            "memo": f"Employee pension liability for {employee.first_name} {employee.last_name}",
                        }
                    )

                if pay_var.employee_health > 0:
                    total_debits.append(
                        {
                            "account": get_account("salary_expense"),
                            "amount": pay_var.employee_health,
                            "memo": f"Employee health contribution for {employee.first_name} {employee.last_name}",
                        }
                    )
                    total_credits.append(
                        {
                            "account": get_account("health_payable"),
                            "amount": pay_var.employee_health,
                            "memo": f"Employee health liability for {employee.first_name} {employee.last_name}",
                        }
                    )

                if pay_var.nhf > 0:
                    total_debits.append(
                        {
                            "account": get_account("salary_expense"),
                            "amount": pay_var.nhf,
                            "memo": f"NHF contribution for {employee.first_name} {employee.last_name}",
                        }
                    )
                    total_credits.append(
                        {
                            "account": get_account("nhf_payable"),
                            "amount": pay_var.nhf,
                            "memo": f"NHF liability for {employee.first_name} {employee.last_name}",
                        }
                    )

                # Other deductions
                for deduction in employee.deductions.filter(
                    created_at__month=instance.paydays.month,
                    created_at__year=instance.paydays.year,
                ):
                    if deduction.deduction_type != "IOU":  # IOU handled separately
                        total_debits.append(
                            {
                                "account": get_account("salary_expense"),
                                "amount": deduction.amount,
                                "memo": f"{deduction.deduction_type} deduction for {employee.first_name} {employee.last_name}",
                            }
                        )
                        total_credits.append(
                            {
                                "account": get_account("deductions_payable"),
                                "amount": deduction.amount,
                                "memo": f"{deduction.deduction_type} liability for {employee.first_name} {employee.last_name}",
                            }
                        )

                # IOU repayments (reduce asset)
                for iou_deduction in employee.iou_deductions.filter(
                    payday__paydays__month=instance.paydays.month,
                    payday__paydays__year=instance.paydays.year,
                ):
                    total_credits.append(
                        {
                            "account": get_account("employee_advances"),
                            "amount": iou_deduction.amount,
                            "memo": f"IOU repayment for {employee.first_name} {employee.last_name}",
                        }
                    )

            # Create journal entries
            entries = []
            for debit in total_debits:
                entries.append(
                    {
                        "account": debit["account"],
                        "entry_type": "DEBIT",
                        "amount": debit["amount"],
                        "memo": debit["memo"],
                    }
                )

            for credit in total_credits:
                entries.append(
                    {
                        "account": credit["account"],
                        "entry_type": "CREDIT",
                        "amount": credit["amount"],
                        "memo": credit["memo"],
                    }
                )

            # Create the journal with all entries
            if entries:
                journal = create_journal_with_entries(
                    date=instance.paydays.first_day(),
                    description=f"Payroll for period: {instance.save_month_str}",
                    entries=entries,
                    fiscal_year=fiscal_year,
                    period=period,
                    source_object=instance,
                    auto_post=True,
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
            )

            # Log the IOU approval
            log_accounting_activity(
                user=None,  # System generated
                action=AccountingAuditTrail.ActionType.APPROVE,
                instance=journal,
                reason=f"IOU approved for {instance.employee_id.first_name} {instance.employee_id.last_name}",
            )


@receiver(post_save, sender=IOUDeduction)
def handle_iou_repayment(sender, instance, created, **kwargs):
    """
    Create journal entries when IOU repayments are made.
    Debit: Salary Expense (for the repayment amount)
    Credit: Employee Advances (reducing the asset)
    """
    if not created:
        return

    with transaction.atomic():
        # Get fiscal year and period
        repayment_date = instance.payday.paydays.first_day()
        fiscal_year = get_or_create_fiscal_year(repayment_date.year)
        period = get_or_create_period(fiscal_year, repayment_date.month)

        # Create journal entries
        entries = [
            {
                "account": get_account("salary_expense"),
                "entry_type": "DEBIT",
                "amount": instance.amount,
                "memo": f"IOU repayment from {instance.employee.first_name} {instance.employee.last_name}",
            },
            {
                "account": get_account("employee_advances"),
                "entry_type": "CREDIT",
                "amount": instance.amount,
                "memo": f"Reduce IOU balance for {instance.employee.first_name} {instance.employee.last_name}",
            },
        ]

        # Create the journal
        journal = create_journal_with_entries(
            date=repayment_date,
            description=f"IOU repayment from {instance.employee.first_name} {instance.employee.last_name}",
            entries=entries,
            fiscal_year=fiscal_year,
            period=period,
            source_object=instance,
            auto_post=True,
        )

        # Log the IOU repayment
        log_accounting_activity(
            user=None,  # System generated
            action=AccountingAuditTrail.ActionType.POST,
            instance=journal,
            reason=f"IOU repayment from {instance.employee.first_name} {instance.employee.last_name}",
        )


@receiver(post_save, sender=Allowance)
def handle_allowance_creation(sender, instance, created, **kwargs):
    """
    Create journal entries when allowances are created.
    Debit: Allowance Expense
    Credit: Cash/Bank
    """
    if not created:
        return

    with transaction.atomic():
        # Get fiscal year and period
        allowance_date = instance.created_at.date()
        fiscal_year = get_or_create_fiscal_year(allowance_date.year)
        period = get_or_create_period(fiscal_year, allowance_date.month)

        # Create journal entries
        entries = [
            {
                "account": get_account("allowance_expense"),
                "entry_type": "DEBIT",
                "amount": instance.amount,
                "memo": f"{instance.allowance_type} allowance for {instance.employee.first_name} {instance.employee.last_name}",
            },
            {
                "account": get_account("cash"),
                "entry_type": "CREDIT",
                "amount": instance.amount,
                "memo": f"Payment of {instance.allowance_type} allowance to {instance.employee.first_name} {instance.employee.last_name}",
            },
        ]

        # Create the journal
        journal = create_journal_with_entries(
            date=allowance_date,
            description=f"{instance.allowance_type} allowance for {instance.employee.first_name} {instance.employee.last_name}",
            entries=entries,
            fiscal_year=fiscal_year,
            period=period,
            source_object=instance,
            auto_post=True,
        )

        # Log the allowance creation
        log_accounting_activity(
            user=None,  # System generated
            action=AccountingAuditTrail.ActionType.CREATE,
            instance=journal,
            reason=f"{instance.allowance_type} allowance created for {instance.employee.first_name} {instance.employee.last_name}",
        )


@receiver(post_save, sender=Deduction)
def handle_deduction_creation(sender, instance, created, **kwargs):
    """
    Create journal entries when deductions are created (excluding IOU).
    Debit: Salary Expense
    Credit: Various Liability Accounts
    """
    if not created or instance.deduction_type == "IOU":
        return

    with transaction.atomic():
        # Get fiscal year and period
        deduction_date = instance.created_at.date()
        fiscal_year = get_or_create_fiscal_year(deduction_date.year)
        period = get_or_create_period(fiscal_year, deduction_date.month)

        # Create journal entries
        entries = [
            {
                "account": get_account("salary_expense"),
                "entry_type": "DEBIT",
                "amount": instance.amount,
                "memo": f"{instance.deduction_type} deduction for {instance.employee.first_name} {instance.employee.last_name}",
            },
            {
                "account": get_account("deductions_payable"),
                "entry_type": "CREDIT",
                "amount": instance.amount,
                "memo": f"{instance.deduction_type} liability for {instance.employee.first_name} {instance.employee.last_name}",
            },
        ]

        # Create the journal
        journal = create_journal_with_entries(
            date=deduction_date,
            description=f"{instance.deduction_type} deduction for {instance.employee.first_name} {instance.employee.last_name}",
            entries=entries,
            fiscal_year=fiscal_year,
            period=period,
            source_object=instance,
            auto_post=True,
        )

        # Log the deduction creation
        log_accounting_activity(
            user=None,  # System generated
            action=AccountingAuditTrail.ActionType.CREATE,
            instance=journal,
            reason=f"{instance.deduction_type} deduction created for {instance.employee.first_name} {instance.employee.last_name}",
        )
