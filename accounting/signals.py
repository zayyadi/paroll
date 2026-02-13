# accounting/signals.py

from decimal import Decimal
from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from dateutil.relativedelta import relativedelta
from django.utils import timezone

# Import models from both your payroll and accounting apps
from payroll.models import PayrollRun, IOU
from accounting.models import Account, Journal, JournalEntry, AccountingAuditTrail
from accounting.utils import (
    create_journal_with_entries,
    get_or_create_fiscal_year,
    get_or_create_period,
    log_accounting_activity,
)
from payroll.models.payroll import Deduction

# --- Helper Function for Accounts ---


def _get_or_create_account(name, account_type, account_number):
    """
    A robust helper to get or create an account.
    This prevents the signals from failing if an account doesn't exist yet.
    """
    account, created = Account.objects.get_or_create(
        account_number=account_number,
        defaults={
            "name": name,
            "type": account_type,
        },
    )
    return account


# --- Signals for Payroll Events ---


@receiver(pre_save, sender=IOU)
def create_journal_for_approved_iou(sender, instance, **kwargs):
    """
    Creates a journal entry when an IOU's status changes to 'APPROVED'.

    Accounting Effect:
    - DEBIT:  Employee Advances (Asset) - The company is now owed money.
    - CREDIT: Cash/Bank (Asset) - Represents the cash paid out to the employee.
    """
    if not instance.pk:  # Don't run on creation, only on update
        return

    try:
        old_instance = IOU.objects.get(pk=instance.pk)
    except IOU.DoesNotExist:
        return

    # Trigger only on the status change from something else to APPROVED
    if old_instance.status != "APPROVED" and instance.status == "APPROVED":
        with transaction.atomic():
            # 1. Define the accounts needed for this transaction
            employee_advances_acc = _get_or_create_account(
                name="Employee Advances",
                account_type=Account.AccountType.ASSET,
                account_number="1400",
            )
            cash_acc = _get_or_create_account(
                name="Cash and Cash Equivalents",
                account_type=Account.AccountType.ASSET,
                account_number="1010",
            )

            # 2. Get fiscal year and period
            approval_date = instance.approved_at or instance.created_at
            fiscal_year = get_or_create_fiscal_year(approval_date.year)
            period = get_or_create_period(fiscal_year, approval_date.month)

            # 3. Create journal entries
            entries = [
                {
                    "account": employee_advances_acc,
                    "entry_type": "DEBIT",
                    "amount": instance.amount,
                    "memo": f"IOU approved for {instance.employee_id}",
                },
                {
                    "account": cash_acc,
                    "entry_type": "CREDIT",
                    "amount": instance.amount,
                    "memo": f"Cash paid for IOU to {instance.employee_id}",
                },
            ]

            # 4. Create the journal using enhanced function
            journal = create_journal_with_entries(
                date=approval_date,
                description=f"IOU approved for {instance.employee_id}",
                entries=entries,
                fiscal_year=fiscal_year,
                period=period,
                source_object=instance,
                auto_post=True,
            )

            # 5. Log the activity
            log_accounting_activity(
                user=None,  # System generated
                action=AccountingAuditTrail.ActionType.APPROVE,
                instance=journal,
                reason=f"IOU approved for {instance.employee_id}",
            )


# @receiver(pre_save, sender=PayrollRun)
# def create_journal_for_closed_payroll(sender, instance, **kwargs):
#     print(
#         f"DEBUG: create_journal_for_closed_payroll signal triggered for PayrollRun ID: {instance.id}"
#     )
#     """
#     Creates a comprehensive journal entry for the entire payroll period
#     when its status changes to 'closed'.

#     This signal aggregates all payroll data for the period and creates
#     a single, balanced journal entry.
#     """
#     if not instance.pk:
#         return

#     try:
#         old_instance = PayrollRun.objects.get(pk=instance.pk)
#     except PayrollRun.DoesNotExist:
#         return

#     # Trigger only when 'closed' changes from False to True
#     if not old_instance.closed and instance.closed:
#         with transaction.atomic():
#             # 1. Get all payroll calculations for this period
#             payrolls_in_period = instance.payroll_payday.all()
#             if not payrolls_in_period.exists():
#                 raise ValidationError(
#                     "Cannot close a payroll period with no employees."
#                 )

#             # 2. Define all necessary accounts
#             salaries_expense_acc = _get_or_create_account(
#                 "Salaries and Wages Expense", Account.AccountType.EXPENSE, "6010"
#             )
#             allowances_expense_acc = _get_or_create_account(
#                 "Allowances Expense", Account.AccountType.EXPENSE, "6015"
#             )
#             pension_expense_acc = _get_or_create_account(
#                 "Pension Expense (Employer)", Account.AccountType.EXPENSE, "6020"
#             )
#             health_expense_acc = _get_or_create_account(
#                 "Health Contribution Expense (Employer)",
#                 Account.AccountType.EXPENSE,
#                 "6030",
#             )
#             nsitf_expense_acc = _get_or_create_account(
#                 "NSITF Expense", Account.AccountType.EXPENSE, "6040"
#             )

#             cash_acc = _get_or_create_account(
#                 "Cash and Cash Equivalents", Account.AccountType.ASSET, "1010"
#             )
#             employee_advances_acc = _get_or_create_account(
#                 "Employee Advances", Account.AccountType.ASSET, "1400"
#             )

#             paye_payable_acc = _get_or_create_account(
#                 "PAYE Tax Payable", Account.AccountType.LIABILITY, "2110"
#             )
#             pension_payable_acc = _get_or_create_account(
#                 "Pension Payable", Account.AccountType.LIABILITY, "2120"
#             )
#             health_payable_acc = _get_or_create_account(
#                 "Health Contribution Payable", Account.AccountType.LIABILITY, "2130"
#             )
#             nsitf_payable_acc = _get_or_create_account(
#                 "NSITF Payable", Account.AccountType.LIABILITY, "2140"
#             )
#             deductions_payable_acc = _get_or_create_account(
#                 "Other Deductions Payable", Account.AccountType.LIABILITY, "2150"
#             )
#             nhf_payable, _ = Account.objects.get_or_create(
#                 name="NHF Payable",
#                 account_number="2030",
#                 type=Account.AccountType.LIABILITY,
#             )
#             print(
#                 f"DEBUG: NHF Payable Account: ID={nhf_payable.id}, Name={nhf_payable.name}, Type={nhf_payable.type}"
#             )

#             # 3. Aggregate totals from all employees in the payroll
#             total_gross_earnings_for_expense = Decimal(
#                 0
#             )  # Combined gross earnings for expense
#             total_net_pay = Decimal(0)
#             total_paye = Decimal(0)
#             total_pension_employee = Decimal(0)
#             total_pension_employer = Decimal(0)
#             total_nhf = Decimal(0)
#             total_employee_health = Decimal(0)
#             total_employer_health = Decimal(0)
#             total_nsitf = Decimal(0)
#             total_other_deductions = Decimal(0)
#             total_iou_repayments = Decimal(0)

#             for payday_link in payrolls_in_period:
#                 pay_var = payday_link
#                 employee_payroll = pay_var.pays.employee_pay

#                 # Aggregate values for total company expense (employee earnings)
#                 total_gross_earnings_for_expense += employee_payroll.basic_salary
#                 total_gross_earnings_for_expense += employee_payroll.housing
#                 total_gross_earnings_for_expense += employee_payroll.transport
#                 total_gross_earnings_for_expense += employee_payroll.bht
#                 total_gross_earnings_for_expense += (
#                     pay_var.calc_allowance
#                 )  # Add allowances here

#                 total_net_pay += pay_var.netpay
#                 total_paye += employee_payroll.payee
#                 total_pension_employee += employee_payroll.pension_employee
#                 total_pension_employer += employee_payroll.pension_employer
#                 total_nhf += pay_var.nhf
#                 total_employee_health += pay_var.employee_health
#                 total_employer_health += pay_var.emplyr_health
#                 total_nsitf += employee_payroll.nsitf

#                 # Add water_rate directly to total_other_deductions
#                 total_other_deductions += employee_payroll.water_rate

#                 # Separate IOU repayments from other deductions from the Deduction model
#                 for deduction in pay_var.pays.deductions.filter(
#                     created_at__month=instance.paydays.month,
#                     created_at__year=instance.paydays.year,
#                 ):
#                     if deduction.deduction_type == "IOU":
#                         total_iou_repayments += deduction.amount
#                     else:
#                         total_other_deductions += deduction.amount

#             # DEBUG: Print aggregated totals
#             print(f"DEBUG Aggregated Totals:")
#             print(
#                 f"  total_gross_earnings_for_expense: {total_gross_earnings_for_expense}"
#             )
#             print(f"  total_net_pay (from PayrollEntry): {total_net_pay}")
#             print(f"  total_paye: {total_paye}")
#             print(f"  total_pension_employee: {total_pension_employee}")
#             print(f"  total_pension_employer: {total_pension_employer}")
#             print(f"  total_nhf: {total_nhf}")
#             print(f"  total_employee_health: {total_employee_health}")
#             print(f"  total_employer_health: {total_employer_health}")
#             print(f"  total_nsitf: {total_nsitf}")
#             print(f"  total_other_deductions: {total_other_deductions}")
#             print(f"  total_iou_repayments: {total_iou_repayments}")

#             # Calculate net pay based on aggregated components for the journal entry
#             calculated_net_pay_for_journal = total_gross_earnings_for_expense - (
#                 total_paye
#                 + total_pension_employee
#                 + total_nhf
#                 + total_employee_health
#                 + total_other_deductions
#                 + total_iou_repayments
#             )

#             # 4. Create the main Journal
#             journal_date = (
#                 instance.paydays.first_day()
#             )  # Use first_day() to get a date object
#             journal = Journal.objects.create(
#                 description=f"Payroll for period: {instance.save_month_str}",
#                 date=journal_date,
#             )

#             # 5. Create DEBIT entries (Expenses)
#             journal.add_entry(
#                 salaries_expense_acc, "DEBIT", total_gross_earnings_for_expense
#             )  # Use the combined total
#             # Removed separate allowances_expense_acc debit
#             if total_pension_employer > 0:
#                 journal.add_entry(pension_expense_acc, "DEBIT", total_pension_employer)
#             if total_employer_health > 0:
#                 journal.add_entry(health_expense_acc, "DEBIT", total_employer_health)
#             if total_nsitf > 0:
#                 journal.add_entry(nsitf_expense_acc, "DEBIT", total_nsitf)

#             # 6. Create CREDIT entries (Liabilities and Cash Out)
#             journal.add_entry(
#                 cash_acc, "CREDIT", calculated_net_pay_for_journal
#             )  # Use the calculated net pay for balancing
#             journal.add_entry(paye_payable_acc, "CREDIT", total_paye)
#             # Total pension liability is both employee and employer contributions
#             journal.add_entry(
#                 pension_payable_acc,
#                 "CREDIT",
#                 total_pension_employee + total_pension_employer,
#             )
#             # Total health liability is both employee and employer contributions
#             journal.add_entry(
#                 health_payable_acc,
#                 "CREDIT",
#                 total_employee_health + total_employer_health,
#             )
#             journal.add_entry(nsitf_payable_acc, "CREDIT", total_nsitf)

#             if total_other_deductions > 0:
#                 journal.add_entry(
#                     deductions_payable_acc, "CREDIT", total_other_deductions
#                 )

#             if total_iou_repayments > 0:
#                 journal.add_entry(employee_advances_acc, "CREDIT", total_iou_repayments)

#             # 7. Validate and Post the final journal
#             # For debugging: Calculate sums before posting
#             calculated_debits = sum(
#                 entry.amount for entry in journal.entries.filter(entry_type="DEBIT")
#             )
#             calculated_credits = sum(
#                 entry.amount for entry in journal.entries.filter(entry_type="CREDIT")
#             )
#             print(f"Payroll Journal Debits: {calculated_debits}")
#             print(f"Payroll Journal Credits: {calculated_credits}")
#             print(
#                 f"Payroll Journal Difference: {calculated_debits - calculated_credits}"
#             )

#             try:
#                 journal.post()
#             except ValidationError as e:
#                 print(f"Validation Error posting payroll journal: {e.message}")
#                 # Re-raise the exception to ensure it's not silently ignored during development
#                 raise


# In payroll/signals.py


@receiver(pre_save, sender=PayrollRun)
def create_journal_for_closed_payroll(sender, instance, **kwargs):
    """
    Creates a comprehensive, balanced journal entry for the entire payroll period
    when its status is changed to 'closed'.

    This signal derives all values directly from payroll components to ensure
    the accounting entry is always balanced, by calculating net cash paid as the
    balancing figure.
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
                raise ValidationError(
                    "Cannot close a payroll period with no employees."
                )

            # 1. Define all necessary accounts for clarity
            salaries_expense_acc = _get_or_create_account(
                "Salaries and Wages Expense", Account.AccountType.EXPENSE, "6010"
            )
            pension_expense_acc = _get_or_create_account(
                "Pension Expense (Employer)", Account.AccountType.EXPENSE, "6020"
            )
            health_expense_acc = _get_or_create_account(
                "Health Contribution Expense (Employer)",
                Account.AccountType.EXPENSE,
                "6030",
            )
            nsitf_expense_acc = _get_or_create_account(
                "NSITF Expense", Account.AccountType.EXPENSE, "6040"
            )

            cash_acc = _get_or_create_account(
                "Cash and Cash Equivalents", Account.AccountType.ASSET, "1010"
            )
            employee_advances_acc = _get_or_create_account(
                "Employee Advances", Account.AccountType.ASSET, "1400"
            )

            paye_payable_acc = _get_or_create_account(
                "PAYE Tax Payable", Account.AccountType.LIABILITY, "2110"
            )
            pension_payable_acc = _get_or_create_account(
                "Pension Payable", Account.AccountType.LIABILITY, "2120"
            )
            health_payable_acc = _get_or_create_account(
                "Health Contribution Payable", Account.AccountType.LIABILITY, "2130"
            )
            nsitf_payable_acc = _get_or_create_account(
                "NSITF Payable", Account.AccountType.LIABILITY, "2140"
            )
            nhf_payable_acc = _get_or_create_account(
                "NHF Payable", Account.AccountType.LIABILITY, "2150"
            )
            deductions_payable_acc = _get_or_create_account(
                "Other Deductions Payable", Account.AccountType.LIABILITY, "2160"
            )

            # 2. Initialize aggregate totals to zero
            total_salary_expense = Decimal(0)
            total_allowance_expense = Decimal(0)
            total_pension_employer_expense = Decimal(0)
            total_health_employer_expense = Decimal(0)
            total_nsitf_expense = Decimal(0)

            total_paye_liability = Decimal(0)
            total_pension_liability = Decimal(0)
            total_health_liability = Decimal(0)
            total_nsitf_liability = Decimal(0)
            total_nhf_liability = Decimal(0)
            total_other_deductions_liability = Decimal(0)
            total_iou_repayment_credit = Decimal(0)

            # 3. Aggregate all components from the payroll run
            for pay_var in pay_vars_in_period:
                employee_payroll = pay_var.pays.employee_pay

                # --- Aggregate Expenses (for the DEBIT side) ---
                # Gross salary expense includes basic and fixed allowances
                gross_salary_for_employee = (
                    employee_payroll.basic
                    + employee_payroll.housing
                    + employee_payroll.transport
                )
                total_salary_expense += gross_salary_for_employee

                total_allowance_expense += pay_var.calc_allowance
                total_pension_employer_expense += employee_payroll.pension_employer
                total_health_employer_expense += pay_var.emplyr_health
                total_nsitf_expense += employee_payroll.nsitf

                # --- Aggregate Liabilities and Asset Reductions (for the CREDIT side) ---
                total_paye_liability += employee_payroll.payee
                # Pension liability is the sum of employee and employer contributions
                total_pension_liability += (
                    employee_payroll.pension_employee
                    + employee_payroll.pension_employer
                )
                # Health liability is the sum of employee and employer contributions
                total_health_liability += (
                    pay_var.employee_health + pay_var.emplyr_health
                )
                total_nsitf_liability += (
                    employee_payroll.nsitf
                )  # The liability matches the expense
                total_nhf_liability += pay_var.nhf

                # Separate IOU repayments from other deductions
                for deduction in pay_var.pays.deductions.filter(
                    created_at__month=instance.paydays.month,
                    created_at__year=instance.paydays.year,
                ):
                    if deduction.deduction_type == "IOU":
                        total_iou_repayment_credit += deduction.amount
                    else:
                        total_other_deductions_liability += deduction.amount

            # 4. Calculate total debits and credits to find the balancing cash figure
            total_debits = (
                total_salary_expense
                + total_allowance_expense
                + total_pension_employer_expense
                + total_health_employer_expense
                + total_nsitf_expense
            )

            total_credits_non_cash = (
                total_paye_liability
                + total_pension_liability
                + total_health_liability
                + total_nsitf_liability
                + total_nhf_liability
                + total_other_deductions_liability
                + total_iou_repayment_credit
            )

            # The cash paid out is the balancing figure. This guarantees the journal will balance.
            calculated_net_cash_paid = total_debits - total_credits_non_cash

            # 5. Get fiscal year and period
            journal_date = instance.paydays.first_day()  # Correct method for MonthField
            fiscal_year = get_or_create_fiscal_year(journal_date.year)
            period = get_or_create_period(fiscal_year, journal_date.month)

            # 6. Create the journal entries
            entries = []

            # --- DEBIT entries ---
            entries.append(
                {
                    "account": salaries_expense_acc,
                    "entry_type": "DEBIT",
                    "amount": total_salary_expense + total_allowance_expense,
                    "memo": f"Salaries and allowances for period {instance.save_month_str}",
                }
            )
            if total_pension_employer_expense > 0:
                entries.append(
                    {
                        "account": pension_expense_acc,
                        "entry_type": "DEBIT",
                        "amount": total_pension_employer_expense,
                        "memo": f"Employer pension contributions for period {instance.save_month_str}",
                    }
                )
            if total_health_employer_expense > 0:
                entries.append(
                    {
                        "account": health_expense_acc,
                        "entry_type": "DEBIT",
                        "amount": total_health_employer_expense,
                        "memo": f"Employer health contributions for period {instance.save_month_str}",
                    }
                )
            if total_nsitf_expense > 0:
                entries.append(
                    {
                        "account": nsitf_expense_acc,
                        "entry_type": "DEBIT",
                        "amount": total_nsitf_expense,
                        "memo": f"NSITF contributions for period {instance.save_month_str}",
                    }
                )

            # --- CREDIT entries ---
            entries.append(
                {
                    "account": cash_acc,
                    "entry_type": "CREDIT",
                    "amount": calculated_net_cash_paid,
                    "memo": f"Net cash paid for period {instance.save_month_str}",
                }
            )
            if total_paye_liability > 0:
                entries.append(
                    {
                        "account": paye_payable_acc,
                        "entry_type": "CREDIT",
                        "amount": total_paye_liability,
                        "memo": f"PAYE tax liability for period {instance.save_month_str}",
                    }
                )
            if total_pension_liability > 0:
                entries.append(
                    {
                        "account": pension_payable_acc,
                        "entry_type": "CREDIT",
                        "amount": total_pension_liability,
                        "memo": f"Pension liability for period {instance.save_month_str}",
                    }
                )
            if total_health_liability > 0:
                entries.append(
                    {
                        "account": health_payable_acc,
                        "entry_type": "CREDIT",
                        "amount": total_health_liability,
                        "memo": f"Health contribution liability for period {instance.save_month_str}",
                    }
                )
            if total_nsitf_liability > 0:
                entries.append(
                    {
                        "account": nsitf_payable_acc,
                        "entry_type": "CREDIT",
                        "amount": total_nsitf_liability,
                        "memo": f"NSITF liability for period {instance.save_month_str}",
                    }
                )
            if total_nhf_liability > 0:
                entries.append(
                    {
                        "account": nhf_payable_acc,
                        "entry_type": "CREDIT",
                        "amount": total_nhf_liability,
                        "memo": f"NHF liability for period {instance.save_month_str}",
                    }
                )
            if total_other_deductions_liability > 0:
                entries.append(
                    {
                        "account": deductions_payable_acc,
                        "entry_type": "CREDIT",
                        "amount": total_other_deductions_liability,
                        "memo": f"Other deductions liability for period {instance.save_month_str}",
                    }
                )
            if total_iou_repayment_credit > 0:
                entries.append(
                    {
                        "account": employee_advances_acc,
                        "entry_type": "CREDIT",
                        "amount": total_iou_repayment_credit,
                        "memo": f"IOU repayments for period {instance.save_month_str}",
                    }
                )

            # 7. Create the journal using enhanced function
            journal = create_journal_with_entries(
                date=journal_date,
                description=f"Payroll for period: {instance.save_month_str}",
                entries=entries,
                fiscal_year=fiscal_year,
                period=period,
                source_object=instance,
                auto_post=True,
            )

            # 8. Log the activity
            log_accounting_activity(
                user=None,  # System generated
                action=AccountingAuditTrail.ActionType.POST,
                instance=journal,
                reason=f"Payroll period {instance.save_month_str} closed",
            )


@receiver(post_save, sender=IOU)
def schedule_iou_repayments_on_approval(sender, instance, created, **kwargs):
    """
    When an IOU is approved, this signal automatically creates monthly
    Deduction records for the entire tenor of the IOU.
    """
    # Trigger only when status is 'APPROVED'
    if instance.status != "APPROVED":
        return

    # Check if deductions for this IOU have already been scheduled to prevent duplicates
    if instance.repayment_installments.exists():
        return

    # Ensure we have a tenor and an approval date to work with
    if instance.tenor > 0 and instance.approved_at:
        # Use a transaction to ensure all deductions are created or none are
        with transaction.atomic():
            # Calculate the fixed monthly repayment amount
            monthly_installment = round(instance.total_amount / instance.tenor, 2)

            # Schedule one deduction for each month of the tenor
            for i in range(instance.tenor):
                # Calculate the date for this specific installment
                # The first payment is one month after the approval date
                deduction_date = instance.approved_at + relativedelta(months=i + 1)

                Deduction.objects.create(
                    employee=instance.employee_id,
                    iou=instance,  # Link the deduction back to the IOU
                    deduction_type="IOU",  # Explicitly set the type
                    amount=monthly_installment,
                    # Set the 'created_at' to the future date so payroll picks it up in the correct month
                    created_at=deduction_date,
                    reason=f"Monthly repayment for IOU of {instance.amount} (Installment {i+1}/{instance.tenor})",
                )
