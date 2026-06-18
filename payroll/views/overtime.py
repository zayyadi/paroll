from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from company.utils import get_user_company
from payroll.models import EmployeeProfile
from payroll.models.workforce import OvertimePolicy, OvertimeEntry
from payroll.services.overtime_service import (
    approve_overtime,
    reject_overtime,
)


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def overtime_policy_form(request):
    company = get_user_company(request.user)
    policy = OvertimePolicy.objects.filter(company=company, is_active=True).first()

    if request.method == "POST":
        daily = request.POST.get("daily_threshold_hours", 8)
        weekly = request.POST.get("weekly_threshold_hours", 40)
        weekday_rate = request.POST.get("weekday_rate_multiplier", 1.5)
        weekend_rate = request.POST.get("weekend_rate_multiplier", 2.0)
        holiday_rate = request.POST.get("holiday_rate_multiplier", 2.0)
        max_daily = request.POST.get("max_daily_overtime_hours", 4)
        requires_approval = request.POST.get("requires_approval") == "on"

        if policy:
            policy.daily_threshold_hours = daily
            policy.weekly_threshold_hours = weekly
            policy.weekday_rate_multiplier = weekday_rate
            policy.weekend_rate_multiplier = weekend_rate
            policy.holiday_rate_multiplier = holiday_rate
            policy.max_daily_overtime_hours = max_daily
            policy.requires_approval = requires_approval
            policy.save()
        else:
            policy = OvertimePolicy.objects.create(
                company=company,
                daily_threshold_hours=daily,
                weekly_threshold_hours=weekly,
                weekday_rate_multiplier=weekday_rate,
                weekend_rate_multiplier=weekend_rate,
                holiday_rate_multiplier=holiday_rate,
                max_daily_overtime_hours=max_daily,
                requires_approval=requires_approval,
            )
        messages.success(request, "Overtime policy saved.")
        return redirect("payroll:overtime_policy")

    return render(request, "payroll/overtime_policy.html", {
        "policy": policy,
        "page_title": "Overtime Policy",
    })


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def overtime_entries_list(request):
    company = get_user_company(request.user)
    status_filter = request.GET.get("status", "")
    entries = OvertimeEntry.objects.filter(
        company=company
    ).select_related("employee", "approved_by")
    if status_filter:
        entries = entries.filter(status=status_filter)
    return render(request, "payroll/overtime_entries.html", {
        "entries": entries,
        "status_filter": status_filter,
        "page_title": "Overtime Entries",
    })


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def overtime_approve(request, pk):
    company = get_user_company(request.user)
    entry = get_object_or_404(OvertimeEntry, pk=pk, company=company)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            approve_overtime(entry=entry, approved_by=request.user)
            messages.success(request, f"Overtime for {entry.employee} approved.")
        elif action == "reject":
            reject_overtime(entry=entry, approved_by=request.user)
            messages.warning(request, f"Overtime for {entry.employee} rejected.")

    return redirect("payroll:overtime_entries")
