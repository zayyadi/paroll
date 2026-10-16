from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from io import StringIO
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

NIP_BANK_CODES = {
    "Zenith": "057", "GTBank": "058", "Access": "044", "UBA": "033",
    "FCMB": "214", "FBN": "011", "Union": "032", "Jaiz": "301",
}


def _salary_rows(payroll_run: Any) -> list[list[str]]:
    if payroll_run.currency != 'NGN':
        raise ValidationError('NIP payment instructions require NGN payroll obligations.')
    from payroll.models.payroll import PayrollRunEntry

    entries = PayrollRunEntry.objects.filter(payroll_run=payroll_run).select_related(
        "payroll_entry", "payroll_entry__pays"
    ).order_by("pk")
    rows = []
    employee_ids = set()
    for run_entry in entries:
        entry = run_entry.payroll_entry
        employee = entry.pays
        if entry.company_id != payroll_run.company_id or employee.company_id != payroll_run.company_id:
            raise ValidationError("Payment employees must belong to the payroll company.")
        if employee.pk in employee_ids:
            raise ValidationError("An employee cannot be paid twice in one payroll run.")
        employee_ids.add(employee.pk)
        amount = entry.netpay
        if amount < 0:
            raise ValidationError("Salary payments cannot be negative.")
        if amount == 0:
            continue
        beneficiary_bank = "GTBank" if employee.bank == "GTB" else employee.bank
        beneficiary_code = NIP_BANK_CODES.get(beneficiary_bank)
        if not employee.bank_account_number or not beneficiary_code:
            raise ValidationError("Every payable employee needs an account and a supported bank.")
        rows.append([
            employee.bank_account_number,
            f"{employee.first_name} {employee.last_name}",
            beneficiary_code,
            f"{amount:.2f}",
            f"Salary {payroll_run.paydays}",
        ])
    if not rows:
        raise ValidationError("The payroll run has no salaries payable by bank transfer.")
    return rows


def _validate_file(payment_file: Any, payroll_run: Any) -> None:
    """The CSV is the beneficiary snapshot; require exact current payable coverage."""
    if payment_file.payroll_run_id != payroll_run.pk or payment_file.company_id != payroll_run.company_id:
        raise ValidationError("The payment file and payroll run must belong to the same company.")
    if payment_file.bank_code not in NIP_BANK_CODES.values() or not payment_file.file:
        raise ValidationError("A valid bank payment file is required.")
    try:
        with payment_file.file.open("rb") as exported:
            rows = list(csv.reader(StringIO(exported.read().decode("utf-8"))))
        expected = _salary_rows(payroll_run)
        amounts = [Decimal(row[3]) for row in rows[4:]]
    except (UnicodeError, csv.Error, ValueError, IndexError, ArithmeticError, OSError) as exc:
        raise ValidationError("The payment file is invalid or unavailable.") from exc
    if (
        len(rows) < 4
        or rows[0] != ["BANK CODE", "BANK NAME", "SESSION DATE", "ORIGINATOR NAME"]
        or len(rows[1]) != 4
        or rows[1][0] != payment_file.bank_code
        or rows[1][3] != payroll_run.name
        or rows[3] != ["BENE ACCOUNT NO", "BENE NAME", "BENE BANK CODE", "AMOUNT", "NARRATION"]
        or Counter(map(tuple, rows[4:])) != Counter(map(tuple, expected))
        or len(amounts) != payment_file.total_records
        or sum(amounts, Decimal("0.00")) != payment_file.total_amount
    ):
        raise ValidationError("The payment file does not match the complete payroll obligations.")


def _locked_payroll_run(run_id: int) -> Any:
    from payroll.models.payroll import PayrollRun

    payroll_run = PayrollRun.all_objects.select_for_update().get(pk=run_id)
    if payroll_run.status != PayrollRun.Status.LOCKED:
        raise ValidationError("Only a locked, unpaid payroll run can be paid.")
    return payroll_run


@transaction.atomic
def generate_nip_file(*, payroll_run: Any, bank_code: str) -> Any:
    from payroll.models.payroll import BankPaymentFile

    payroll_run = _locked_payroll_run(payroll_run.pk)
    if bank_code not in NIP_BANK_CODES.values():
        raise ValidationError("Select a supported originator bank.")
    if BankPaymentFile.all_objects.filter(payroll_run=payroll_run, status__in=["SUBMITTED", "CONFIRMED"]).exists():
        raise ValidationError("This payroll run already has a submitted payment file.")
    bank_name = next(k for k, v in NIP_BANK_CODES.items() if v == bank_code)
    salary_rows = _salary_rows(payroll_run)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["BANK CODE", "BANK NAME", "SESSION DATE", "ORIGINATOR NAME"])
    writer.writerow([bank_code, bank_name, timezone.localdate().isoformat(), payroll_run.name])
    writer.writerow([])
    writer.writerow(["BENE ACCOUNT NO", "BENE NAME", "BENE BANK CODE", "AMOUNT", "NARRATION"])
    writer.writerows(salary_rows)
    file_name = f"nip_{bank_code}_{payroll_run.paydays}.csv"
    payment_file = BankPaymentFile.objects.create(
        company=payroll_run.company, payroll_run=payroll_run,
        bank_code=bank_code, bank_name=bank_name, file_name=file_name,
        total_amount=sum((Decimal(row[3]) for row in salary_rows), Decimal("0.00")),
        total_records=len(salary_rows), status="GENERATED",
    )
    payment_file.file.save(file_name, ContentFile(output.getvalue().encode("utf-8")))
    return payment_file


@transaction.atomic
def mark_submitted(*, payment_file: Any, reference_number: str = "") -> Any:
    from payroll.models.payroll import BankPaymentFile

    from approvals.services import execution_authorized, submit_approval
    from approvals.proposals import _request_actor
    if not execution_authorized(payment_file, 'bank_payment.submit'):
        maker = _request_actor.get() or payment_file.created_by
        return submit_approval(source=payment_file, action='bank_payment.submit', requester=maker,
            payload={'reference_number':reference_number,'currency':'NGN'})
    payroll_run = _locked_payroll_run(payment_file.payroll_run_id)
    current = BankPaymentFile.objects.select_for_update().get(pk=payment_file.pk)
    if current.status != "GENERATED":
        raise ValidationError("Only a generated payment file can be submitted.")
    if BankPaymentFile.all_objects.filter(payroll_run=payroll_run).exclude(pk=current.pk).filter(status__in=["SUBMITTED", "CONFIRMED"]).exists():
        raise ValidationError("This payroll run already has a submitted payment file.")
    _validate_file(current, payroll_run)
    current.status = "SUBMITTED"
    current.submitted_at = timezone.now()
    current.reference_number = reference_number
    current.save(update_fields=["status", "submitted_at", "reference_number"], _validated_transition=True)
    payment_file.refresh_from_db()
    return payment_file


@transaction.atomic
def mark_confirmed(*, payment_file: Any) -> Any:
    from payroll.models.payroll import BankPaymentFile

    from approvals.services import current_execution, authorize_approved_execution
    from approvals.models import ApprovalRequest
    from approvals.permissions import require_company_authority
    from approvals.proposals import _request_actor
    from django.contrib.contenttypes.models import ContentType
    actor = _request_actor.get()
    if current_execution() is None:
        require_company_authority(actor, payment_file.company, 'payroll.change_payrollrun')
        approval = ApprovalRequest.objects.filter(action='bank_payment.submit',
            content_type=ContentType.objects.get_for_model(payment_file), object_id=payment_file.pk,status='APPROVED').order_by('-pk').first()
        if approval is None:
            raise ValidationError('The bank instruction has not completed independent approval.')
        with authorize_approved_execution(approval, actor):
            return mark_confirmed(payment_file=payment_file)
    payroll_run = _locked_payroll_run(payment_file.payroll_run_id)
    current = BankPaymentFile.objects.select_for_update().get(pk=payment_file.pk)
    if current.status != "SUBMITTED":
        raise ValidationError("Only a submitted payment file can be confirmed.")
    _validate_file(current, payroll_run)
    current.status = "CONFIRMED"
    current.confirmed_at = timezone.now()
    current.save(update_fields=["status", "confirmed_at"], _validated_transition=True)
    payroll_run.payment_date = timezone.localdate()
    payroll_run.mark_paid(update_fields=["status", "closed", "payment_date"])
    payment_file.refresh_from_db()
    return payment_file
