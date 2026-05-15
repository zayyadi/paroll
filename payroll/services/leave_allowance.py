from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from accounting.models import Account, Journal
from accounting.utils import (
    create_journal_with_entries,
    get_or_create_fiscal_year,
    get_or_create_period,
    log_accounting_activity,
)
from payroll.models import Allowance, CompanyPayrollSetting, LeaveAllowanceEmailJob


MONEY_QUANTIZER = Decimal("0.01")
PAYROLL_ACCOUNT_MAP = {
    "allowance_expense": ("Allowances Expense", Account.AccountType.EXPENSE, "6015"),
    "cash": ("Cash and Cash Equivalents", Account.AccountType.ASSET, "1100"),
}


def _employee_name(employee):
    return f"{employee.first_name or ''} {employee.last_name or ''}".strip() or (
        employee.emp_id or f"Employee #{employee.pk}"
    )


def _get_payroll_account(company, account_key):
    name, account_type, account_number = PAYROLL_ACCOUNT_MAP[account_key]
    account = Account.objects.filter(company=company, account_number=account_number).first()
    if account is None:
        account = Account.objects.filter(company=company, name=name).first()

    if account is None:
        return Account.objects.create(
            company=company,
            name=name,
            type=account_type,
            account_number=account_number,
        )

    update_fields = []
    if (
        account.name != name
        and not Account.objects.filter(company=company, name=name)
        .exclude(pk=account.pk)
        .exists()
    ):
        account.name = name
        update_fields.append("name")
    if account.type != account_type:
        account.type = account_type
        update_fields.append("type")
    if account.account_number != account_number:
        account.account_number = account_number
        update_fields.append("account_number")
    if update_fields:
        account.save(update_fields=update_fields)
    return account


def _journal_exists_for_allowance(allowance):
    source_ct = ContentType.objects.get_for_model(Allowance)
    return Journal.objects.filter(
        company=allowance.employee.company,
        content_type=source_ct,
        object_id=allowance.pk,
        description__startswith="Leave allowance paid to",
    ).exists()


def calculate_leave_allowance_amount(leave_request):
    employee = leave_request.employee
    payroll = getattr(employee, "employee_pay", None)
    if not payroll:
        return Decimal("0.00")

    company = employee.company
    if not company:
        return Decimal("0.00")

    setting = CompanyPayrollSetting.objects.filter(company=company).first()
    if not setting or not setting.leave_allowance_percentage:
        return Decimal("0.00")

    percentage = Decimal(setting.leave_allowance_percentage)
    if percentage <= 0:
        return Decimal("0.00")

    basic_salary = Decimal(payroll.basic_salary or Decimal("0.00"))
    amount = (basic_salary * percentage) / Decimal("100")
    return amount.quantize(MONEY_QUANTIZER)


def process_leave_allowance_for_request(leave_request):
    """
    Create the automatic leave allowance and queue its slip email once.

    The explicit allowance prevents duplicate payment in payroll calculations.
    Older approved leaves without this record still use the payroll-entry
    fallback calculation.
    """
    if leave_request.status != "APPROVED":
        return None

    amount = calculate_leave_allowance_amount(leave_request)
    if amount <= 0:
        return None

    with transaction.atomic():
        allowance, allowance_created = Allowance.objects.get_or_create(
            source_leave_request=leave_request,
            defaults={
                "employee": leave_request.employee,
                "allowance_type": "LV",
                "amount": amount,
            },
        )
        if not allowance_created:
            update_fields = []
            if allowance.employee_id != leave_request.employee_id:
                allowance.employee = leave_request.employee
                update_fields.append("employee")
            if allowance.allowance_type != "LV":
                allowance.allowance_type = "LV"
                update_fields.append("allowance_type")
            if allowance.amount != amount:
                allowance.amount = amount
                update_fields.append("amount")
            if update_fields:
                allowance.save(update_fields=update_fields)

        job, job_created = LeaveAllowanceEmailJob.objects.get_or_create(
            leave_request=leave_request,
            defaults={
                "allowance": allowance,
                "amount": amount,
            },
        )
        job_updates = []
        if job.allowance_id != allowance.id:
            job.allowance = allowance
            job_updates.append("allowance")
        if job.amount != amount:
            job.amount = amount
            job_updates.append("amount")
        if job_updates:
            job.save(update_fields=job_updates + ["updated_at"])

        post_leave_allowance_journal(allowance, leave_request)

        if job_created:
            transaction.on_commit(lambda: job.enqueue())

    return allowance


def post_leave_allowance_journal(allowance, leave_request):
    if not allowance or not getattr(allowance, "pk", None):
        return None
    if _journal_exists_for_allowance(allowance):
        return None

    amount = Decimal(allowance.amount or Decimal("0.00")).quantize(MONEY_QUANTIZER)
    if amount <= 0:
        return None

    employee = leave_request.employee
    company = employee.company
    employee_name = _employee_name(employee)
    posting_date = leave_request.start_date
    fiscal_year = get_or_create_fiscal_year(posting_date.year, company=company)
    period = get_or_create_period(fiscal_year, posting_date.month, company=company)
    description = (
        f"Leave allowance paid to {employee_name} "
        f"for {leave_request.get_leave_type_display()} "
        f"({leave_request.start_date} to {leave_request.end_date})"
    )

    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description=description,
        entries=[
            {
                "account": _get_payroll_account(company, "allowance_expense"),
                "entry_type": "DEBIT",
                "amount": amount,
                "memo": f"Leave allowance expense - {employee_name}",
            },
            {
                "account": _get_payroll_account(company, "cash"),
                "entry_type": "CREDIT",
                "amount": amount,
                "memo": f"Leave allowance payment - {employee_name}",
            },
        ],
        fiscal_year=fiscal_year,
        period=period,
        auto_post=True,
        source_object=allowance,
        validate_balances=False,
    )
    log_accounting_activity(
        action="POST",
        instance=journal,
        reason=f"Automatic leave allowance posting for leave request #{leave_request.pk}",
    )
    return journal
