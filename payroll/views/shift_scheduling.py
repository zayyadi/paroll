from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from company.utils import get_user_company
from payroll.models import EmployeeProfile
from payroll.models.workforce import Shift, ShiftTemplate, ShiftAssignment


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def shift_list(request):
    company = get_user_company(request.user)
    shifts = Shift.objects.filter(company=company)
    return render(request, "payroll/shift_list.html", {
        "shifts": shifts,
        "page_title": "Shifts",
    })


@login_required
@permission_required("payroll.add_employeeprofile", raise_exception=True)
def shift_create(request):
    company = get_user_company(request.user)

    if request.method == "POST":
        name = request.POST.get("name")
        start_time = request.POST.get("start_time")
        end_time = request.POST.get("end_time")
        break_minutes = request.POST.get("break_minutes", 60)

        Shift.objects.create(
            company=company,
            name=name,
            start_time=start_time,
            end_time=end_time,
            break_minutes=break_minutes,
        )
        messages.success(request, f"Shift '{name}' created.")
        return redirect("payroll:shift_list")

    return render(request, "payroll/shift_form.html", {
        "page_title": "Create Shift",
    })


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def shift_template_list(request):
    company = get_user_company(request.user)
    templates = ShiftTemplate.objects.filter(company=company).prefetch_related(
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    )
    return render(request, "payroll/shift_template_list.html", {
        "templates": templates,
        "page_title": "Shift Templates",
    })


@login_required
@permission_required("payroll.add_employeeprofile", raise_exception=True)
def shift_template_create(request):
    company = get_user_company(request.user)
    shifts = Shift.objects.filter(company=company, is_active=True)

    if request.method == "POST":
        name = request.POST.get("name")
        days = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        chosen = {day: request.POST.get(day) or None for day in days}
        allowed = {str(pk) for pk in shifts.values_list("pk", flat=True)}
        if any(value is not None and value not in allowed for value in chosen.values()):
            messages.error(request, "Choose shifts from your company only.")
            return redirect("payroll:shift_template_create")
        template = ShiftTemplate.objects.create(
            company=company,
            name=name,
            **{f"{day}_id": value for day, value in chosen.items()},
        )
        messages.success(request, f"Shift template '{name}' created.")
        return redirect("payroll:shift_template_list")

    return render(request, "payroll/shift_template_form.html", {
        "shifts": shifts,
        "page_title": "Create Shift Template",
    })


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def shift_assignment_list(request):
    company = get_user_company(request.user)
    assignments = ShiftAssignment.objects.filter(
        company=company
    ).select_related("employee", "shift_template")
    employees = EmployeeProfile.objects.filter(company=company, status="active")
    templates = ShiftTemplate.objects.filter(company=company, is_active=True)

    return render(request, "payroll/shift_assignment_list.html", {
        "assignments": assignments,
        "employees": employees,
        "templates": templates,
        "page_title": "Shift Assignments",
    })


@login_required
@permission_required("payroll.add_employeeprofile", raise_exception=True)
def shift_assignment_create(request):
    company = get_user_company(request.user)

    if request.method == "POST":
        employee_id = request.POST.get("employee")
        template_id = request.POST.get("shift_template")
        effective_from = request.POST.get("effective_from")
        effective_to = request.POST.get("effective_to") or None

        employee = get_object_or_404(EmployeeProfile, id=employee_id, company=company)
        template = get_object_or_404(ShiftTemplate, id=template_id, company=company)

        ShiftAssignment.objects.create(
            company=company,
            employee=employee,
            shift_template=template,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        messages.success(request, f"Shift assigned to {employee}.")
        return redirect("payroll:shift_assignment_list")

    return redirect("payroll:shift_assignment_list")
