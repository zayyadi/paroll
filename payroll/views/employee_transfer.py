from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from company.utils import get_user_company
from payroll.models import EmployeeProfile, Department, EmployeeTransfer, Promotion
from payroll.services.transfer_service import (
    execute_transfer,
    approve_transfer,
    reject_transfer,
    execute_promotion,
    approve_promotion,
    reject_promotion,
)


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def transfer_list(request):
    company = get_user_company(request.user)
    transfers = EmployeeTransfer.objects.filter(
        company=company
    ).select_related("employee", "from_department", "to_department", "approved_by")
    return render(request, "employee/transfer_list.html", {
        "transfers": transfers,
        "page_title": "Employee Transfers",
    })


@login_required
@permission_required("payroll.add_employeeprofile", raise_exception=True)
def transfer_create(request):
    company = get_user_company(request.user)
    employees = EmployeeProfile.objects.filter(company=company, status="active")
    departments = Department.objects.filter(company=company)

    if request.method == "POST":
        employee_id = request.POST.get("employee")
        to_dept_id = request.POST.get("to_department")
        to_position = request.POST.get("to_position", "")
        effective_date = request.POST.get("effective_date")
        reason = request.POST.get("reason", "")

        employee = get_object_or_404(EmployeeProfile, id=employee_id, company=company)
        to_department = get_object_or_404(Department, id=to_dept_id, company=company) if to_dept_id else None

        transfer = EmployeeTransfer.objects.create(
            company=company,
            employee=employee,
            from_department=employee.department,
            to_department=to_department,
            from_position=employee.job_title,
            to_position=to_position,
            effective_date=effective_date,
            reason=reason,
            requested_by=request.user,
        )
        messages.success(request, f"Transfer request created for {employee}.")
        return redirect("payroll:transfer_detail", pk=transfer.pk)

    return render(request, "employee/transfer_form.html", {
        "employees": employees,
        "departments": departments,
        "page_title": "Create Transfer",
    })


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def transfer_detail(request, pk):
    company = get_user_company(request.user)
    transfer = get_object_or_404(
        EmployeeTransfer.objects.select_related(
            "employee", "from_department", "to_department",
            "requested_by", "approved_by"
        ),
        pk=pk, company=company,
    )
    return render(request, "employee/transfer_detail.html", {
        "transfer": transfer,
        "page_title": "Transfer Details",
    })


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def transfer_approve(request, pk):
    company = get_user_company(request.user)
    transfer = get_object_or_404(EmployeeTransfer, pk=pk, company=company)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            approve_transfer(transfer=transfer, approved_by=request.user)
            execute_transfer(transfer=transfer, performed_by=request.user)
            messages.success(request, f"Transfer for {transfer.employee} approved and executed.")
        elif action == "reject":
            reject_transfer(transfer=transfer, approved_by=request.user)
            messages.warning(request, f"Transfer for {transfer.employee} rejected.")

    return redirect("payroll:transfer_detail", pk=pk)


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def promotion_list(request):
    company = get_user_company(request.user)
    promotions = Promotion.objects.filter(
        company=company
    ).select_related("employee", "approved_by")
    return render(request, "employee/promotion_list.html", {
        "promotions": promotions,
        "page_title": "Employee Promotions",
    })


@login_required
@permission_required("payroll.add_employeeprofile", raise_exception=True)
def promotion_create(request):
    company = get_user_company(request.user)
    employees = EmployeeProfile.objects.filter(company=company, status="active")

    if request.method == "POST":
        employee_id = request.POST.get("employee")
        new_title = request.POST.get("new_title", "")
        effective_date = request.POST.get("effective_date")
        reason = request.POST.get("reason", "")

        employee = get_object_or_404(EmployeeProfile, id=employee_id, company=company)

        promotion = Promotion.objects.create(
            company=company,
            employee=employee,
            old_title=employee.job_title,
            new_title=new_title,
            old_salary_config=employee.employee_pay,
            effective_date=effective_date,
            reason=reason,
            requested_by=request.user,
        )
        messages.success(request, f"Promotion request created for {employee}.")
        return redirect("payroll:promotion_detail", pk=promotion.pk)

    return render(request, "employee/promotion_form.html", {
        "employees": employees,
        "page_title": "Create Promotion",
    })


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def promotion_detail(request, pk):
    company = get_user_company(request.user)
    promotion = get_object_or_404(
        Promotion.objects.select_related("employee", "requested_by", "approved_by"),
        pk=pk, company=company,
    )
    return render(request, "employee/promotion_detail.html", {
        "promotion": promotion,
        "page_title": "Promotion Details",
    })


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def promotion_approve(request, pk):
    company = get_user_company(request.user)
    promotion = get_object_or_404(Promotion, pk=pk, company=company)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            approve_promotion(promotion=promotion, approved_by=request.user)
            execute_promotion(promotion=promotion, performed_by=request.user)
            messages.success(request, f"Promotion for {promotion.employee} approved and executed.")
        elif action == "reject":
            reject_promotion(promotion=promotion, approved_by=request.user)
            messages.warning(request, f"Promotion for {promotion.employee} rejected.")

    return redirect("payroll:promotion_detail", pk=pk)
