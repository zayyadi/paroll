from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from company.utils import get_user_company
from payroll.models import EmployeeProfile
from payroll.forms import ExitSettlementForm
from payroll.models.workforce import ExitSettlement, OffboardingChecklist, OffboardingTask
from payroll.services import exit_settlement_service
from payroll.services.offboarding_service import (
    initiate_offboarding,
    complete_task,
    complete_offboarding,
)


def _pending_settlement_approval(settlement):
    """The open exit.settlement approval request for a statement, if any."""
    from approvals.models import ApprovalRequest
    from django.contrib.contenttypes.models import ContentType

    if settlement is None:
        return None
    return ApprovalRequest.objects.filter(
        action="exit.settlement",
        content_type=ContentType.objects.get_for_model(ExitSettlement),
        object_id=settlement.pk,
        status="PENDING",
    ).first()


def _error_text(exc):
    return "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def offboarding_list(request):
    company = get_user_company(request.user)
    checklists = OffboardingChecklist.objects.filter(
        company=company
    ).select_related("employee", "initiated_by")
    return render(request, "employee/offboarding_list.html", {
        "checklists": checklists,
        "page_title": "Offboarding",
    })


@login_required
@permission_required("payroll.add_employeeprofile", raise_exception=True)
def offboarding_initiate(request):
    company = get_user_company(request.user)
    employees = EmployeeProfile.objects.filter(company=company, status="active")

    if request.method == "POST":
        employee_id = request.POST.get("employee")
        last_working_day = request.POST.get("last_working_day")
        reason = request.POST.get("reason")

        employee = get_object_or_404(EmployeeProfile, id=employee_id, company=company)
        checklist = initiate_offboarding(
            employee=employee,
            last_working_day=last_working_day,
            reason=reason,
            initiated_by=request.user,
        )
        messages.success(request, f"Offboarding initiated for {employee}.")
        return redirect("payroll:offboarding_detail", pk=checklist.pk)

    return render(request, "employee/offboarding_initiate.html", {
        "employees": employees,
        "page_title": "Initiate Offboarding",
    })


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def offboarding_detail(request, pk):
    company = get_user_company(request.user)
    checklist = get_object_or_404(
        OffboardingChecklist.objects.select_related("employee", "initiated_by"),
        pk=pk, company=company,
    )
    tasks = checklist.tasks.all()
    completed_count = tasks.filter(is_completed=True).count()
    total_count = tasks.count()
    all_done = completed_count == total_count if total_count > 0 else False
    settlement = ExitSettlement.objects.filter(checklist=checklist).first()
    pending_approval = _pending_settlement_approval(settlement)
    editable = (
        settlement is not None
        and settlement.status == ExitSettlement.Status.DRAFT
        and pending_approval is None
    )

    return render(request, "employee/offboarding_detail.html", {
        "checklist": checklist,
        "tasks": tasks,
        "completed_count": completed_count,
        "total_count": total_count,
        "all_done": all_done,
        "settlement": settlement,
        "settlement_form": ExitSettlementForm(instance=settlement) if editable else None,
        "pending_approval": pending_approval,
        "page_title": f"Offboarding - {checklist.employee}",
    })


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def offboarding_task_complete(request, pk, task_id):
    company = get_user_company(request.user)
    task = get_object_or_404(
        OffboardingTask.objects.select_related("checklist__company"),
        pk=task_id,
        checklist_id=pk,
    )
    if task.checklist.company != company:
        messages.error(request, "Access denied.")
        return redirect("payroll:offboarding_list")

    if request.method == "POST":
        notes = request.POST.get("notes", "")
        complete_task(task=task, completed_by=request.user, notes=notes)
        messages.success(request, f"Task '{task.title}' marked as complete.")

    return redirect("payroll:offboarding_detail", pk=task.checklist_id)


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def offboarding_calculate_settlement(request, pk):
    """Build or refresh the exit settlement statement from current balances."""
    company = get_user_company(request.user)
    checklist = get_object_or_404(OffboardingChecklist, pk=pk, company=company)

    if request.method == "POST":
        settlement = ExitSettlement.objects.filter(checklist=checklist).first()
        if _pending_settlement_approval(settlement):
            messages.error(request, "The settlement is awaiting approval and cannot be recalculated.")
        else:
            try:
                settlement = exit_settlement_service.build_settlement(checklist=checklist)
            except ValidationError as exc:
                messages.error(request, _error_text(exc))
            else:
                messages.success(
                    request, f"Settlement calculated: net ₦{settlement.net_settlement:,.2f}"
                )

    return redirect("payroll:offboarding_detail", pk=pk)


@login_required
@permission_required("payroll.change_exitsettlement", raise_exception=True)
@require_POST
def offboarding_settlement_edit(request, pk):
    """Save HR-entered amounts (gratuity, compensation, other items)."""
    company = get_user_company(request.user)
    settlement = get_object_or_404(ExitSettlement, checklist_id=pk, company=company)
    if settlement.status != ExitSettlement.Status.DRAFT or _pending_settlement_approval(settlement):
        messages.error(request, "Only a draft settlement that is not awaiting approval can be edited.")
        return redirect("payroll:offboarding_detail", pk=pk)

    form = ExitSettlementForm(request.POST, instance=settlement)
    if form.is_valid():
        form.save()
        messages.success(request, f"Settlement updated: PAYE ₦{settlement.paye_on_exit:,.2f}, net ₦{settlement.net_settlement:,.2f}")
    else:
        for field, errors in form.errors.items():
            messages.error(request, f"{form.fields[field].label if field in form.fields else field}: {errors[0]}")
    return redirect("payroll:offboarding_detail", pk=pk)


@login_required
@permission_required("payroll.change_exitsettlement", raise_exception=True)
@require_POST
def offboarding_settlement_submit(request, pk):
    """Send the draft settlement for approval; approval posts the journal."""
    from approvals.services import submit_approval

    company = get_user_company(request.user)
    settlement = get_object_or_404(ExitSettlement, checklist_id=pk, company=company)
    if _pending_settlement_approval(settlement):
        messages.info(request, "The settlement is already awaiting approval.")
        return redirect("payroll:offboarding_detail", pk=pk)
    initiator = settlement.checklist.initiated_by
    if initiator is not None and initiator.pk != request.user.pk:
        messages.error(
            request,
            f"Only {initiator.get_full_name() or initiator.email}, who started this offboarding, can submit the settlement.",
        )
        return redirect("payroll:offboarding_detail", pk=pk)
    try:
        submit_approval(source=settlement, action="exit.settlement", requester=request.user)
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, _error_text(exc))
    else:
        messages.success(request, "Settlement submitted for approval.")
    return redirect("payroll:offboarding_detail", pk=pk)


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def offboarding_complete(request, pk):
    company = get_user_company(request.user)
    checklist = get_object_or_404(OffboardingChecklist, pk=pk, company=company)

    if request.method == "POST":
        try:
            result = complete_offboarding(checklist=checklist, actor=request.user)
            if result.status == "PENDING":
                messages.info(request, "Approval recorded; awaiting the next stage.")
            else:
                messages.success(request, "Offboarding approval completed.")
        except (ValidationError, ValueError) as e:
            messages.error(request, "; ".join(e.messages) if isinstance(e, ValidationError) else str(e))

    return redirect("payroll:offboarding_detail", pk=pk)
