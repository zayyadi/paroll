from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import FileResponse
from django.core.exceptions import ValidationError

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
    from approvals.models import ApprovalRequest
    from approvals.permissions import has_company_permission
    from django.contrib.contenttypes.models import ContentType
    can_manage = has_company_permission(request.user, company, 'payroll.change_payrollrun')
    files = list(files)
    requests = ApprovalRequest.objects.filter(company=company, action='bank_payment.submit',
        content_type=ContentType.objects.get_for_model(BankPaymentFile), object_id__in=[item.pk for item in files]).prefetch_related('decisions').order_by('pk')
    by_file = {approval.object_id:approval for approval in requests}
    for item in files:
        approval = by_file.get(item.pk)
        item.can_submit = can_manage and item.created_by_id in (None, request.user.pk) and not (approval and approval.status == 'PENDING')
        final = max((decision for decision in approval.decisions.all() if decision.decision == 'APPROVE'), key=lambda decision:decision.stage, default=None) if approval else None
        item.can_confirm = bool(can_manage and approval and approval.status == 'APPROVED' and final and final.actor_id == request.user.pk)
        item.pending_approval_id = approval.pk if approval and approval.status == 'PENDING' else None
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
        try:
            approval = mark_submitted(payment_file=payment_file, reference_number=reference)
            from approvals.proposals import pending_response
            return pending_response(request, approval)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))

    return redirect("payroll:bank_payment_list")


@login_required
@permission_required("payroll.change_payrollrun", raise_exception=True)
def bank_payment_confirm(request, pk):
    company = get_user_company(request.user)
    payment_file = get_object_or_404(BankPaymentFile, pk=pk, company=company)

    if request.method == "POST":
        try:
            mark_confirmed(payment_file=payment_file)
            messages.success(request, "Payment file confirmed.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))

    return redirect("payroll:bank_payment_list")
