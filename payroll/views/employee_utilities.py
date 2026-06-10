"""
Utilities views.
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

def _start_workflow_execution(
    *,
    company,
    employee_profile,
    workflow_type,
    started_by,
    trigger_event,
):
    """
    Start the first active company workflow matching the employee lifecycle event.
    """
    if company is None or employee_profile is None:
        return None

    templates = models.WorkflowTemplate.objects.filter(
        company=company,
        workflow_type=workflow_type,
        is_active=True,
    )
    template = templates.filter(trigger_event=trigger_event).first() or templates.filter(
        trigger_event=""
    ).first()
    if template is None:
        return None

    employee_name = " ".join(
        part for part in [employee_profile.first_name, employee_profile.last_name] if part
    ).strip()
    return models.WorkflowExecution.objects.create(
        company=company,
        template=template,
        employee=employee_profile,
        started_by=started_by,
        context={
            "trigger_event": trigger_event,
            "employee_id": employee_profile.pk,
            "employee_email": employee_profile.email,
            "employee_name": employee_name,
        },
    )



def get_employee_notifications(employee_profile):
    """
    Get notifications for an employee from Notification model
    """
    # Get notifications from database model
    notifications = models.Notification.objects.filter(
        recipient=employee_profile
    ).select_related("leave_request", "iou", "payroll", "appraisal")[
        :10
    ]  # Get 10 most recent notifications

    return notifications


def get_recent_activities(limit=10, company=None):
    """
    Get recent activities across the system for the dashboard.
    Aggregates data from multiple sources to show a comprehensive activity feed.
    """
    from datetime import datetime, date, time
    from monthyear import Month

    def to_datetime(timestamp):
        """Convert various timestamp types to datetime.datetime for consistent comparison."""
        if timestamp is None:
            return timezone.now()
        if isinstance(timestamp, datetime):
            return timestamp
        # Explicitly handle Month objects first (before date check since Month is a date subclass)
        if isinstance(timestamp, Month):
            return datetime.combine(timestamp.first_day(), time.min)
        if isinstance(timestamp, date):
            return datetime.combine(timestamp, time.min)
        # If it's already a datetime-like object, return as is
        return timestamp

    def to_sort_key(timestamp):
        """Convert timestamp to a numeric value for sorting (Unix timestamp)."""
        dt = to_datetime(timestamp)
        # Handle Month objects that don't have timestamp() method
        if hasattr(dt, "timestamp"):
            return dt.timestamp()
        # For datetime objects without timestamp method, convert manually
        import calendar

        return calendar.timegm(dt.utctimetuple())

    activities = []

    recent_employees_qs = models.EmployeeProfile.objects
    if company is not None:
        recent_employees_qs = recent_employees_qs.filter(company=company)
    recent_employees = recent_employees_qs.order_by("-created")[:5]
    for emp in recent_employees:
        emp_timestamp = to_datetime(emp.created)
        activities.append(
            {
                "type": "employee_added",
                "icon": "user-plus",
                "icon_color": "blue",
                "title": "New employee added",
                "description": f"{emp.first_name} {emp.last_name} joined the team",
                "timestamp": emp_timestamp,
                "link": f"/payroll/employee/{emp.user_id}" if emp.user else None,
            }
        )

    # Get recent payroll processed (closed payroll periods only)
    recent_payrolls_qs = models.PayrollRun.objects.filter(closed=True)
    if company is not None:
        recent_payrolls_qs = recent_payrolls_qs.filter(company=company)
    recent_payrolls = recent_payrolls_qs.order_by("-paydays")[:5]
    for payroll in recent_payrolls:
        payroll_timestamp = to_datetime(payroll.paydays)
        activities.append(
            {
                "type": "payroll_processed",
                "icon": "check-circle",
                "icon_color": "green",
                "title": "Payment processed",
                "description": f"Payroll for {payroll.paydays.strftime('%B %Y') if payroll.paydays else 'recent period'} completed",
                "timestamp": payroll_timestamp,
                "link": f"/payroll/pay-period/{payroll.slug}" if payroll.slug else None,
            }
        )

    # Get recent leave requests
    recent_leaves_qs = models.LeaveRequest.objects
    if company is not None:
        recent_leaves_qs = recent_leaves_qs.filter(employee__company=company)
    recent_leaves = recent_leaves_qs.order_by("-created_at")[:5]
    for leave in recent_leaves:
        leave_timestamp = to_datetime(leave.created_at)
        activities.append(
            {
                "type": "leave_request",
                "icon": "calendar",
                "icon_color": "yellow",
                "title": f"Leave request {leave.status.lower()}",
                "description": f"{leave.employee.first_name} {leave.employee.last_name} requested {leave.get_leave_type_display()}",
                "timestamp": leave_timestamp,
                "link": "/payroll/leave-requests",
            }
        )

    # Get recent IOU requests
    recent_ious_qs = models.IOU.objects
    if company is not None:
        recent_ious_qs = recent_ious_qs.filter(employee_id__company=company)
    recent_ious = recent_ious_qs.order_by("-created_at")[:5]
    for iou in recent_ious:
        iou_timestamp = to_datetime(iou.created_at)
        activities.append(
            {
                "type": "iou_request",
                "icon": "dollar-sign",
                "icon_color": "purple",
                "title": f"IOU {iou.status.lower()}",
                "description": f"{iou.employee_id.first_name} {iou.employee_id.last_name} requested IOU of {iou.amount}",
                "timestamp": iou_timestamp,
                "link": "/payroll/iou-list",
            }
        )

    # Sort all activities by timestamp (most recent first)
    # Use numeric timestamp for sorting to avoid Month comparison issues
    activities.sort(key=lambda x: to_sort_key(x["timestamp"]), reverse=True)

    # Return limited number of activities
    return activities[:limit]



def _get_or_create_today_attendance(employee_profile, company):
    return models.AttendanceRecord.objects.get_or_create(
        company=company,
        employee=employee_profile,
        work_date=timezone.localdate(),
        defaults={"status": models.AttendanceRecord.Status.PRESENT},
    )
