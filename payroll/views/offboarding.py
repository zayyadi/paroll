from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from company.utils import get_user_company
from payroll.models import EmployeeProfile
from payroll.models.workforce import OffboardingChecklist, OffboardingTask
from payroll.services.offboarding_service import (
    initiate_offboarding,
    complete_task,
    calculate_final_settlement,
    complete_offboarding,
)


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

    return render(request, "employee/offboarding_detail.html", {
        "checklist": checklist,
        "tasks": tasks,
        "completed_count": completed_count,
        "total_count": total_count,
        "all_done": all_done,
        "page_title": f"Offboarding - {checklist.employee}",
    })


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def offboarding_task_complete(request, pk):
    company = get_user_company(request.user)
    task = get_object_or_404(
        OffboardingTask.objects.select_related("checklist__company"),
        pk=pk,
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
    company = get_user_company(request.user)
    checklist = get_object_or_404(OffboardingChecklist, pk=pk, company=company)

    if request.method == "POST":
        amount = calculate_final_settlement(checklist=checklist)
        messages.success(request, f"Final settlement calculated: ₦{amount:,.2f}")

    return redirect("payroll:offboarding_detail", pk=pk)


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def offboarding_complete(request, pk):
    company = get_user_company(request.user)
    checklist = get_object_or_404(OffboardingChecklist, pk=pk, company=company)

    if request.method == "POST":
        try:
            complete_offboarding(checklist=checklist)
            messages.success(request, "Offboarding completed successfully.")
        except ValueError as e:
            messages.error(request, str(e))

    return redirect("payroll:offboarding_detail", pk=pk)
