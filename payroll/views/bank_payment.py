from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import FileResponse

from company.utils import get_user_company
from payroll.models.payroll import PayrollRun, BankPaymentFile
from payroll.services.bank_payment_service import (
    generate_nip_file,
    mark_submitted,
    mark_confirmed,
    NIP_BANK_CODES,
)


@login_required
@permission_required("payroll.view_payrollrun", raise_exception=True)
def bank_payment_list(request):
    company = get_user_company(request.user)
    files = BankPaymentFile.objects.filter(
        company=company
    ).select_related("payroll_run", "created_by")
    return render(request, "payroll/bank_payment_list.html", {
        "payment_files": files,
        "page_title": "Bank Payment Files",
    })


@login_required
@permission_required("payroll.add_payrollrun", raise_exception=True)
def bank_payment_generate(request):
    company = get_user_company(request.user)
    runs = PayrollRun.objects.filter(company=company, closed=True)

    if request.method == "POST":
        run_id = request.POST.get("payroll_run")
        bank_code = request.POST.get("bank_code")

        payroll_run = get_object_or_404(PayrollRun, id=run_id, company=company)

        if not bank_code or bank_code not in NIP_BANK_CODES.values():
            messages.error(request, "Invalid bank code selected.")
            return redirect("payroll:bank_payment_generate")

        try:
            payment_file = generate_nip_file(
                payroll_run=payroll_run,
                bank_code=bank_code,
            )
            payment_file.created_by = request.user
            payment_file.save(update_fields=["created_by"])
            messages.success(
                request,
                f"Payment file generated: {payment_file.total_records} records, "
                f"₦{payment_file.total_amount:,.2f}",
            )
            return redirect("payroll:bank_payment_list")
        except Exception as e:
            messages.error(request, f"Error generating payment file: {e}")
            return redirect("payroll:bank_payment_generate")

    return render(request, "payroll/bank_payment_generate.html", {
        "runs": runs,
        "bank_codes": NIP_BANK_CODES,
        "page_title": "Generate Bank Payment File",
    })


@login_required
@permission_required("payroll.view_payrollrun", raise_exception=True)
def bank_payment_download(request, pk):
    company = get_user_company(request.user)
    payment_file = get_object_or_404(
        BankPaymentFile, pk=pk, company=company
    )
    if not payment_file.file:
        messages.error(request, "File not available.")
        return redirect("payroll:bank_payment_list")

    return FileResponse(
        payment_file.file.open("rb"),
        as_attachment=True,
        filename=payment_file.file_name,
    )


@login_required
@permission_required("payroll.change_payrollrun", raise_exception=True)
def bank_payment_submit(request, pk):
    company = get_user_company(request.user)
    payment_file = get_object_or_404(BankPaymentFile, pk=pk, company=company)

    if request.method == "POST":
        reference = request.POST.get("reference_number", "")
        mark_submitted(payment_file=payment_file, reference_number=reference)
        messages.success(request, "Payment file marked as submitted.")

    return redirect("payroll:bank_payment_list")


@login_required
@permission_required("payroll.change_payrollrun", raise_exception=True)
def bank_payment_confirm(request, pk):
    company = get_user_company(request.user)
    payment_file = get_object_or_404(BankPaymentFile, pk=pk, company=company)

    if request.method == "POST":
        mark_confirmed(payment_file=payment_file)
        messages.success(request, "Payment file confirmed.")

    return redirect("payroll:bank_payment_list")
