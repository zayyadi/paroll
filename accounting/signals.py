from django.db.models.signals import post_save
from django.dispatch import receiver
from payroll.models import Payday, IOU, Allowance, Deduction
from accounting.models import Account, Transaction, LedgerEntry
from django.db import transaction as db_transaction
from decimal import Decimal
from django.db.models import F

# --- Helper function to create ledger entries ---
def create_ledger_entry(transaction, account, entry_type, amount):
    if amount > Decimal('0.00'):
        LedgerEntry.objects.create(transaction=transaction, account=account, entry_type=entry_type, amount=amount)
        # Update account balance atomically
        if entry_type == LedgerEntry.EntryType.DEBIT:
            Account.objects.filter(pk=account.pk).update(balance=F('balance') + amount)
        else: # CREDIT
            Account.objects.filter(pk=account.pk).update(balance=F('balance') - amount)

# --- Payday Signal (Payroll Processing) ---
@receiver(post_save, sender=Payday)
def create_payday_ledger_entries(sender, instance, created, **kwargs):
    # This signal handles the comprehensive payroll transaction for a single employee
    # as calculated within a Payday entry.
    # It assumes that allowances and deductions are components of this payroll run.

    # Only process if the Payday instance is new or if its netpay has changed
    # (though for simplicity, we'll always process on save for now).
    # In a production system, you might want to check for actual changes
    # or implement a more sophisticated reconciliation process.

    payvar_instance = instance.payroll_id
    employee_profile = payvar_instance.pays

    # Skip if employee_profile or payroll_details are missing
    if not employee_profile or not employee_profile.employee_pay:
        return

    payroll_details = employee_profile.employee_pay

    # Amounts from PayVar and related Payroll/EmployeeProfile models
    gross_salary_from_payroll = payroll_details.gross_income
    # allowance_amount and other_deduction_amount now come from PayVar's properties
    # which sum up individual Allowance/Deduction instances for the period.
    allowance_amount = payvar_instance.calc_allowance
    paye_amount = payroll_details.payee
    pension_employee_amount = payroll_details.pension_employee
    pension_employer_amount = payroll_details.pension_employer
    nhf_amount = payvar_instance.nhf
    nhis_employee_amount = payvar_instance.employee_health
    nhis_employer_amount = payvar_instance.emplyr_health
    nsitf_amount = payroll_details.nsitf
    other_deduction_amount = payvar_instance.calc_deduction

    net_pay_amount = payvar_instance.netpay

    # Ensure all amounts are Decimal and non-negative
    amounts = {
        'gross_salary_from_payroll': gross_salary_from_payroll,
        'allowance_amount': allowance_amount,
        'paye_amount': paye_amount,
        'pension_employee_amount': pension_employee_amount,
        'pension_employer_amount': pension_employer_amount,
        'nhf_amount': nhf_amount,
        'nhis_employee_amount': nhis_employee_amount,
        'nhis_employer_amount': nhis_employer_amount,
        'nsitf_amount': nsitf_amount,
        'other_deduction_amount': other_deduction_amount,
        'net_pay_amount': net_pay_amount,
    }
    for key, value in amounts.items():
        if not isinstance(value, Decimal):
            amounts[key] = Decimal(value or '0.00')
        if amounts[key] < Decimal('0.00'):
            amounts[key] = Decimal('0.00') # Ensure no negative amounts

    gross_salary_from_payroll = amounts['gross_salary_from_payroll']
    allowance_amount = amounts['allowance_amount']
    paye_amount = amounts['paye_amount']
    pension_employee_amount = amounts['pension_employee_amount']
    pension_employer_amount = amounts['pension_employer_amount']
    nhf_amount = amounts['nhf_amount']
    nhis_employee_amount = amounts['nhis_employee_amount']
    nhis_employer_amount = amounts['nhis_employer_amount']
    nsitf_amount = amounts['nsitf_amount']
    other_deduction_amount = amounts['other_deduction_amount']
    net_pay_amount = amounts['net_pay_amount']

    with db_transaction.atomic():
        # Get or create necessary accounts
        salaries_expense, _ = Account.objects.get_or_create(name='Salaries Expense', type=Account.AccountType.EXPENSE)
        pension_expense, _ = Account.objects.get_or_create(name='Pension Expense', type=Account.AccountType.EXPENSE)
        nhis_expense, _ = Account.objects.get_or_create(name='NHIS Expense', type=Account.AccountType.EXPENSE)
        company_bank, _ = Account.objects.get_or_create(name='Company Bank Account', type=Account.AccountType.ASSET)
        paye_payable, _ = Account.objects.get_or_create(name='PAYE Payable', type=Account.AccountType.LIABILITY)
        pension_payable, _ = Account.objects.get_or_create(name='Pension Payable', type=Account.AccountType.LIABILITY)
        nhf_payable, _ = Account.objects.get_or_create(name='NHF Payable', type=Account.AccountType.LIABILITY)
        nhis_payable, _ = Account.objects.get_or_create(name='NHIS Payable', type=Account.AccountType.LIABILITY)
        nsitf_payable, _ = Account.objects.get_or_create(name='NSITF Payable', type=Account.AccountType.LIABILITY)
        other_deductions_payable, _ = Account.objects.get_or_create(name='Other Deductions Payable', type=Account.AccountType.LIABILITY)

        trans = Transaction.objects.create(description=f'Payroll for {employee_profile.first_name} {employee_profile.last_name} for {instance.paydays_id.paydays.strftime("%B %Y")}')

        # --- DEBITS (Expenses to the company) ---
        # Total gross earnings (salary + allowances) as an expense
        total_gross_earnings = gross_salary_from_payroll + allowance_amount
        create_ledger_entry(trans, salaries_expense, LedgerEntry.EntryType.DEBIT, total_gross_earnings)

        # Employer's pension contribution is an expense
        create_ledger_entry(trans, pension_expense, LedgerEntry.EntryType.DEBIT, pension_employer_amount)

        # Employer's NHIS contribution is an expense
        create_ledger_entry(trans, nhis_expense, LedgerEntry.EntryType.DEBIT, nhis_employer_amount)

        # --- CREDITS (Liabilities and Cash Outflow) ---
        # Employee deductions (liabilities until paid to relevant authorities)
        create_ledger_entry(trans, paye_payable, LedgerEntry.EntryType.CREDIT, paye_amount)
        create_ledger_entry(trans, nhf_payable, LedgerEntry.EntryType.CREDIT, nhf_amount)
        create_ledger_entry(trans, nsitf_payable, LedgerEntry.EntryType.CREDIT, nsitf_amount)
        create_ledger_entry(trans, other_deductions_payable, LedgerEntry.EntryType.CREDIT, other_deduction_amount)

        # Total pension (employee + employer) is a liability until paid to pension fund
        total_pension_payable = pension_employee_amount + pension_employer_amount
        create_ledger_entry(trans, pension_payable, LedgerEntry.EntryType.CREDIT, total_pension_payable)

        # Total NHIS (employee + employer) is a liability until paid to NHIS
        total_nhis_payable = nhis_employee_amount + nhis_employer_amount
        create_ledger_entry(trans, nhis_payable, LedgerEntry.EntryType.CREDIT, total_nhis_payable)

        # Net pay is credited to the bank account (cash outflow)
        create_ledger_entry(trans, company_bank, LedgerEntry.EntryType.CREDIT, net_pay_amount)


# --- IOU Signal (Issuance and Repayment) ---
@receiver(post_save, sender=IOU)
def create_iou_ledger_entries(sender, instance, created, **kwargs):
    # This signal handles the accounting for IOU issuance and repayment.
    # It assumes IOU amounts are positive.

    employee_profile = instance.employee_id
    if not employee_profile:
        return

    iou_amount = instance.amount
    if not isinstance(iou_amount, Decimal):
        iou_amount = Decimal(iou_amount or '0.00')
    if iou_amount < Decimal('0.00'):
        iou_amount = Decimal('0.00')

    with db_transaction.atomic():
        employee_iou_account, _ = Account.objects.get_or_create(name='Employee IOUs', type=Account.AccountType.ASSET)
        company_bank, _ = Account.objects.get_or_create(name='Company Bank Account', type=Account.AccountType.ASSET)

        if created and instance.status == 'APPROVED':
            # IOU Issuance: Company pays out cash, employee owes company
            trans = Transaction.objects.create(description=f'IOU issued to {employee_profile.first_name} {employee_profile.last_name}')

            # Debit Employee IOU Account (Asset increases)
            create_ledger_entry(trans, employee_iou_account, LedgerEntry.EntryType.DEBIT, iou_amount)
            # Credit Company Bank Account (Asset decreases)
            create_ledger_entry(trans, company_bank, LedgerEntry.EntryType.CREDIT, iou_amount)

        elif not created and instance.status == 'PAID':
            # IOU Repayment: Employee pays back, company receives cash
            trans = Transaction.objects.create(description=f'IOU repayment from {employee_profile.first_name} {employee_profile.last_name}')

            # Debit Company Bank Account (Asset increases)
            create_ledger_entry(trans, company_bank, LedgerEntry.EntryType.DEBIT, iou_amount)
            # Credit Employee IOU Account (Asset decreases)
            create_ledger_entry(trans, employee_iou_account, LedgerEntry.EntryType.CREDIT, iou_amount)


# --- Allowance Signal (Separate Allowance Payment) ---
@receiver(post_save, sender=Allowance)
def create_allowance_ledger_entries(sender, instance, created, **kwargs):
    if not created: # Only create entries for new allowances
        return

    allowance_amount = instance.amount
    if not isinstance(allowance_amount, Decimal):
        allowance_amount = Decimal(allowance_amount or '0.00')
    if allowance_amount <= Decimal('0.00'):
        return

    with db_transaction.atomic():
        allowance_expense, _ = Account.objects.get_or_create(name='Allowances Expense', type=Account.AccountType.EXPENSE)
        company_bank, _ = Account.objects.get_or_create(name='Company Bank Account', type=Account.AccountType.ASSET)

        trans = Transaction.objects.create(description=f'Allowance payment to {instance.employee.first_name} {instance.employee.last_name}: {instance.allowance_type} of {allowance_amount}')

        # Debit Allowance Expense (Expense increases)
        create_ledger_entry(trans, allowance_expense, LedgerEntry.EntryType.DEBIT, allowance_amount)
        # Credit Company Bank Account (Asset decreases)
        create_ledger_entry(trans, company_bank, LedgerEntry.EntryType.CREDIT, allowance_amount)


# --- Deduction Signal (Disciplinary Deduction) ---
@receiver(post_save, sender=Deduction)
def create_deduction_ledger_entries(sender, instance, created, **kwargs):
    if not created: # Only create entries for new deductions
        return

    deduction_amount = instance.amount
    employee_profile = instance.employee

    if not employee_profile:
        return

    if not isinstance(deduction_amount, Decimal):
        deduction_amount = Decimal(deduction_amount or '0.00')
    if deduction_amount <= Decimal('0.00'):
        return

    with db_transaction.atomic():
        # Accounts involved in a disciplinary deduction
        # Assuming it's a recovery of funds or an income for the company
        company_bank, _ = Account.objects.get_or_create(name='Company Bank Account', type=Account.AccountType.ASSET)
        disciplinary_income, _ = Account.objects.get_or_create(name='Disciplinary Income', type=Account.AccountType.REVENUE)

        trans = Transaction.objects.create(description=f'Disciplinary deduction from {employee_profile.first_name} {employee_profile.last_name}: {instance.deduction_type} of {deduction_amount}')

        # Debit Company Bank Account (Asset increases - company receives money)
        create_ledger_entry(trans, company_bank, LedgerEntry.EntryType.DEBIT, deduction_amount)
        # Credit Disciplinary Income (Revenue increases)
        create_ledger_entry(trans, disciplinary_income, LedgerEntry.EntryType.CREDIT, deduction_amount)
