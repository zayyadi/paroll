from __future__ import annotations
from typing import Any, Optional
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from io import StringIO
import csv

NIP_BANK_CODES = {
    "Zenith": "057",
    "GTBank": "058",
    "Access": "044",
    "UBA": "033",
    "FCMB": "214",
    "FBN": "011",
    "Union": "032",
    "Jaiz": "301",
}


def generate_nip_file(*, payroll_run: Any, bank_code: str) -> Any:
    from payroll.models.payroll import PayrollEntry, PayrollRunEntry, BankPaymentFile

    bank_name = next(
        (k for k, v in NIP_BANK_CODES.items() if v == bank_code), "Unknown"
    )

    run_entries = PayrollRunEntry.objects.filter(
        payroll_run=payroll_run
    ).select_related("payroll_entry", "payroll_entry__pays")

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["BANK CODE", "BANK NAME", "SESSION DATE", "ORIGINATOR NAME"])
    writer.writerow([
        bank_code,
        bank_name,
        timezone.now().strftime("%Y-%m-%d"),
        payroll_run.name,
    ])
    writer.writerow([])
    writer.writerow(["BENE ACCOUNT NO", "BENE NAME", "BENE BANK CODE", "AMOUNT", "NARRATION"])

    total = Decimal("0.00")
    count = 0
    for run_entry in run_entries:
        entry = run_entry.payroll_entry
        emp = entry.pays
        if emp.bank_account_number:
            amount = entry.netpay
            writer.writerow([
                emp.bank_account_number,
                f"{emp.first_name} {emp.last_name}",
                bank_code,
                f"{amount:.2f}",
                f"Salary {payroll_run.paydays}",
            ])
            total += amount
            count += 1

    file_content = output.getvalue().encode("utf-8")

    from django.core.files.base import ContentFile
    file_name = f"nip_{bank_code}_{payroll_run.paydays}.csv"

    company = payroll_run.company
    payment_file = BankPaymentFile.objects.create(
        company=company,
        payroll_run=payroll_run,
        bank_code=bank_code,
        bank_name=bank_name,
        file_name=file_name,
        total_amount=total,
        total_records=count,
        status="GENERATED",
    )
    payment_file.file.save(file_name, ContentFile(file_content))
    return payment_file


def mark_submitted(*, payment_file: Any, reference_number: str = "") -> Any:
    payment_file.status = "SUBMITTED"
    payment_file.submitted_at = timezone.now()
    payment_file.reference_number = reference_number
    payment_file.save(update_fields=["status", "submitted_at", "reference_number"])
    return payment_file


def mark_confirmed(*, payment_file: Any) -> Any:
    payment_file.status = "CONFIRMED"
    payment_file.confirmed_at = timezone.now()
    payment_file.save(update_fields=["status", "confirmed_at"])
    return payment_file
