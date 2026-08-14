"""
Attendance views.
"""

from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q, Count, Sum, Avg
from django.views.generic.edit import FormView
from django.forms import inlineformset_factory
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import permission_required
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.http import Http404, HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
import json

from company.utils import get_user_company
from payroll import models
from payroll.views.employee_utilities import _get_or_create_today_attendance


@login_required
def attendance_my_day(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    today_record = (
        models.AttendanceRecord.objects.filter(
            company=company,
            employee=employee_profile,
            work_date=timezone.localdate(),
        )
        .order_by("-created_at")
        .first()
    )
    recent_records = models.AttendanceRecord.objects.filter(
        company=company,
        employee=employee_profile,
    ).order_by("-work_date")[:10]

    return render(
        request,
        "employee/attendance_my_day.html",
        {
            "page_title": "My Attendance",
            "today": timezone.localdate(),
            "today_record": today_record,
            "recent_records": recent_records,
        },
    )


@login_required

def attendance_clock(request):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    attendance, _ = _get_or_create_today_attendance(employee_profile, company)
    action = request.POST.get("action")
    now = timezone.now()

    if action == "clock_in":
        if attendance.clock_in is None:
            attendance.clock_in = now
        attendance.status = models.AttendanceRecord.Status.PRESENT
        attendance.save(update_fields=["clock_in", "status", "updated_at"])
        messages.success(request, "You have been clocked in for today.")
    elif action == "clock_out":
        if attendance.clock_in is None:
            attendance.clock_in = now
        attendance.clock_out = now
        duration = attendance.clock_out - attendance.clock_in
        attendance.hours_worked = max(
            Decimal("0.00"),
            Decimal(duration.total_seconds() / 3600).quantize(Decimal("0.01")),
        )
        attendance.save(
            update_fields=["clock_in", "clock_out", "hours_worked", "updated_at"]
        )
        messages.success(request, "You have been clocked out for today.")
    else:
        messages.error(request, "Unknown attendance action.")

    return redirect(request.POST.get("next") or "payroll:attendance_my_day")


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def attendance_overview(request):
    company = get_user_company(request.user)
    today = timezone.localdate()
    today_records = (
        models.AttendanceRecord.objects.select_related("employee", "employee__user")
        .filter(company=company, work_date=today)
        .order_by("employee__first_name", "employee__last_name")
    )
    present_count = today_records.filter(
        status=models.AttendanceRecord.Status.PRESENT
    ).count()
    remote_count = today_records.filter(
        status=models.AttendanceRecord.Status.REMOTE
    ).count()
    out_count = today_records.filter(
        status__in=[
            models.AttendanceRecord.Status.ABSENT,
            models.AttendanceRecord.Status.LEAVE,
            models.AttendanceRecord.Status.HALF_DAY,
        ]
    ).count() + models.LeaveRequest.objects.filter(
        employee__company=company,
        status="APPROVED",
        start_date__lte=today,
        end_date__gte=today,
    ).count()
    recent_records = (
        models.AttendanceRecord.objects.select_related("employee", "employee__user")
        .filter(company=company)
        .order_by("-work_date", "employee__first_name")[:20]
    )

    return render(
        request,
        "employee/attendance_overview.html",
        {
            "page_title": "Attendance Overview",
            "today_records": today_records,
            "recent_records": recent_records,
            "present_count": present_count,
            "remote_count": remote_count,
            "out_count": out_count,
            "today": today,
        },
    )


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def who_is_out(request):
    company = get_user_company(request.user)
    today = timezone.localdate()

    approved_leave = models.LeaveRequest.objects.select_related("employee").filter(
        employee__company=company,
        status="APPROVED",
        start_date__lte=today,
        end_date__gte=today,
    )
    attendance_out = models.AttendanceRecord.objects.select_related("employee").filter(
        company=company,
        work_date=today,
        status__in=[
            models.AttendanceRecord.Status.ABSENT,
            models.AttendanceRecord.Status.LEAVE,
            models.AttendanceRecord.Status.HALF_DAY,
        ],
    )

    entries = []
    seen = set()
    for leave in approved_leave:
        key = ("leave", leave.employee_id)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "employee": leave.employee,
                "reason": leave.get_leave_type_display(),
                "source": "Approved leave",
            }
        )

    for record in attendance_out:
        key = ("attendance", record.employee_id)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "employee": record.employee,
                "reason": record.get_status_display(),
                "source": "Attendance",
            }
        )

    entries.sort(key=lambda item: (item["employee"].first_name or "", item["employee"].last_name or ""))

    return render(
        request,
        "employee/who_is_out.html",
        {
            "page_title": "Who's Out",
            "out_entries": entries,
            "today": today,
        },
    )
