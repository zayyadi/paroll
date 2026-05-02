from decimal import Decimal
from django.utils import timezone
from payroll.forms import (
    AppraisalAssignmentForm,
    EmployeeProfileForm,
    EmployeeProfileUpdateForm,
    AppraisalForm,
    ReviewForm,
    RatingForm,
)
from payroll import models
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST


from django.db.models import Q, Count, Sum
from django.db.models import Avg
from django.views.generic.edit import FormView
from django.forms import inlineformset_factory
from django.db import transaction

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import (
    permission_required,
)  # Added permission_required
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    UpdateView,
    DeleteView,
    ListView,
    DetailView,
)
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)  # Added PermissionRequiredMixin, removed UserPassesTestMixin
from django.contrib import messages

# Removed user_passes_test as it's replaced by permission_required or custom logic in views
from django.http import (
    Http404,
    HttpResponseRedirect,
    HttpResponseForbidden,
)
from django.core.exceptions import PermissionDenied
import json

from users import forms as user_forms
from company.utils import get_user_company

# Removed is_hr_user and check_super helper functions as their use is replaced


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
def my_documents(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    documents = models.EmployeeDocument.objects.filter(
        company=company,
        employee=employee_profile,
    ).order_by("-created_at", "title")

    return render(
        request,
        "employee/my_documents.html",
        {
            "page_title": "My Documents",
            "documents": documents,
            "pending_count": documents.filter(
                acknowledgement_required=True,
                is_acknowledged=False,
            ).count(),
        },
    )


@login_required
def acknowledge_document(request, document_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    document = get_object_or_404(
        models.EmployeeDocument,
        id=document_id,
        company=company,
        employee=employee_profile,
    )

    if document.acknowledgement_required and not document.is_acknowledged:
        document.is_acknowledged = True
        document.acknowledged_at = timezone.now()
        document.save(update_fields=["is_acknowledged", "acknowledged_at", "updated_at"])
        messages.success(request, "Document acknowledged successfully.")
    else:
        messages.info(request, "This document is already acknowledged.")

    return redirect("payroll:my_documents")


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def document_overview(request):
    company = get_user_company(request.user)
    documents = (
        models.EmployeeDocument.objects.filter(company=company)
        .select_related("employee", "employee__user")
        .order_by("-created_at", "title")
    )

    return render(
        request,
        "employee/document_overview.html",
        {
            "page_title": "Document Operations",
            "documents": documents[:20],
            "document_count": documents.count(),
            "pending_count": documents.filter(
                acknowledgement_required=True,
                is_acknowledged=False,
            ).count(),
            "acknowledged_count": documents.filter(is_acknowledged=True).count(),
        },
    )


@login_required
def my_assets(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    assets = (
        models.EmployeeAsset.objects.filter(company=company, employee=employee_profile)
        .select_related("category")
        .order_by("asset_tag")
    )

    return render(
        request,
        "employee/my_assets.html",
        {
            "page_title": "My Assets",
            "assets": assets,
            "in_use_count": assets.filter(status=models.EmployeeAsset.Status.IN_USE).count(),
        },
    )


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def asset_overview(request):
    company = get_user_company(request.user)
    assets = (
        models.EmployeeAsset.objects.filter(company=company)
        .select_related("employee", "category")
        .order_by("asset_tag")
    )

    return render(
        request,
        "employee/asset_overview.html",
        {
            "page_title": "Asset Operations",
            "assets": assets[:25],
            "asset_count": assets.count(),
            "in_use_count": assets.filter(status=models.EmployeeAsset.Status.IN_USE).count(),
            "available_count": assets.filter(
                status=models.EmployeeAsset.Status.AVAILABLE
            ).count(),
            "returned_count": assets.filter(
                status=models.EmployeeAsset.Status.RETURNED
            ).count(),
        },
    )


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def return_asset(request, asset_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    asset = get_object_or_404(models.EmployeeAsset, id=asset_id, company=company)
    asset.status = models.EmployeeAsset.Status.RETURNED
    asset.returned_at = timezone.now()
    asset.employee = None
    asset.save(update_fields=["status", "returned_at", "employee", "updated_at"])
    messages.success(request, "Asset marked as returned.")
    return redirect("payroll:asset_overview")


@login_required
def my_performance(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    goals = models.Goal.objects.filter(company=company, employee=employee_profile).order_by(
        "-created_at"
    )
    one_on_ones = models.OneOnOne.objects.filter(
        company=company,
        employee=employee_profile,
    ).order_by("-scheduled_for")

    return render(
        request,
        "employee/my_performance.html",
        {
            "page_title": "My Performance",
            "goals": goals,
            "one_on_ones": one_on_ones,
            "active_goal_count": goals.filter(status=models.Goal.Status.ACTIVE).count(),
            "scheduled_count": one_on_ones.filter(
                status=models.OneOnOne.Status.SCHEDULED
            ).count(),
        },
    )


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def performance_overview(request):
    company = get_user_company(request.user)
    goals = (
        models.Goal.objects.filter(company=company)
        .select_related("employee", "manager")
        .order_by("-created_at")
    )
    one_on_ones = (
        models.OneOnOne.objects.filter(company=company)
        .select_related("employee", "manager")
        .order_by("-scheduled_for")
    )

    return render(
        request,
        "employee/performance_overview.html",
        {
            "page_title": "Performance Hub",
            "goals": goals[:20],
            "one_on_ones": one_on_ones[:12],
            "goal_count": goals.count(),
            "active_goal_count": goals.filter(status=models.Goal.Status.ACTIVE).count(),
            "scheduled_count": one_on_ones.filter(
                status=models.OneOnOne.Status.SCHEDULED
            ).count(),
            "completed_count": one_on_ones.filter(
                status=models.OneOnOne.Status.COMPLETED
            ).count(),
        },
    )


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def complete_one_on_one(request, meeting_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    meeting = get_object_or_404(models.OneOnOne, id=meeting_id, company=company)
    if meeting.status != models.OneOnOne.Status.COMPLETED:
        meeting.status = models.OneOnOne.Status.COMPLETED
        meeting.completed_at = timezone.now()
        meeting.save(update_fields=["status", "completed_at", "updated_at"])
        messages.success(request, "1:1 marked as completed.")
    else:
        messages.info(request, "This 1:1 is already completed.")
    return redirect("payroll:performance_overview")


@login_required
def my_surveys(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    surveys = (
        models.SurveyTemplate.objects.filter(company=company, is_active=True)
        .prefetch_related("questions")
        .order_by("name")
    )
    submitted_survey_ids = set(
        models.SurveyResponse.objects.filter(company=company, employee=employee_profile)
        .values_list("survey_id", flat=True)
        .distinct()
    )

    return render(
        request,
        "employee/my_surveys.html",
        {
            "page_title": "My Surveys",
            "surveys": surveys,
            "submitted_survey_ids": submitted_survey_ids,
        },
    )


@login_required
def submit_survey(request, survey_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    survey = get_object_or_404(
        models.SurveyTemplate.objects.prefetch_related("questions"),
        id=survey_id,
        company=company,
        is_active=True,
    )

    for question in survey.questions.all():
        field_name = f"question_{question.id}"
        raw_value = request.POST.get(field_name, "").strip()
        if not raw_value and question.is_required:
            continue

        response_defaults = {
            "company": company,
            "survey": survey,
            "question": question,
            "employee": None if survey.is_anonymous else employee_profile,
            "text_response": "",
            "numeric_response": None,
            "choice_response": [],
        }
        if question.question_type == models.SurveyQuestion.QuestionType.RATING:
            response_defaults["numeric_response"] = int(raw_value) if raw_value else None
        elif question.question_type == models.SurveyQuestion.QuestionType.TEXT:
            response_defaults["text_response"] = raw_value
        else:
            response_defaults["choice_response"] = [raw_value] if raw_value else []

        models.SurveyResponse.objects.update_or_create(
            company=company,
            survey=survey,
            question=question,
            employee=response_defaults["employee"],
            defaults=response_defaults,
        )

    messages.success(request, "Survey submitted successfully.")
    return redirect("payroll:my_surveys")


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def survey_overview(request):
    company = get_user_company(request.user)
    surveys = (
        models.SurveyTemplate.objects.filter(company=company)
        .prefetch_related("questions", "responses")
        .order_by("name")
    )

    return render(
        request,
        "employee/survey_overview.html",
        {
            "page_title": "Survey Center",
            "surveys": surveys,
            "survey_count": surveys.count(),
            "active_count": surveys.filter(is_active=True).count(),
            "response_count": models.SurveyResponse.objects.filter(company=company).count(),
        },
    )


@login_required
def my_learning(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    enrollments = (
        models.CourseEnrollment.objects.filter(company=company, employee=employee_profile)
        .select_related("course")
        .order_by("-created_at")
    )

    return render(
        request,
        "employee/my_learning.html",
        {
            "page_title": "My Learning",
            "enrollments": enrollments,
            "required_count": enrollments.filter(course__is_mandatory=True).count(),
            "completed_count": enrollments.filter(
                status=models.CourseEnrollment.Status.COMPLETED
            ).count(),
        },
    )


@login_required
def complete_learning_course(request, enrollment_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    enrollment = get_object_or_404(
        models.CourseEnrollment,
        id=enrollment_id,
        company=company,
        employee=employee_profile,
    )
    if enrollment.status != models.CourseEnrollment.Status.COMPLETED:
        enrollment.status = models.CourseEnrollment.Status.COMPLETED
        enrollment.completed_at = timezone.now()
        enrollment.save(update_fields=["status", "completed_at", "updated_at"])
        messages.success(request, "Course marked as completed.")
    else:
        messages.info(request, "This course is already completed.")
    return redirect("payroll:my_learning")


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def learning_overview(request):
    company = get_user_company(request.user)
    courses = (
        models.LearningCourse.objects.filter(company=company)
        .prefetch_related("enrollments")
        .order_by("title")
    )

    return render(
        request,
        "employee/learning_overview.html",
        {
            "page_title": "Learning Center",
            "courses": courses,
            "course_count": courses.count(),
            "mandatory_count": courses.filter(is_mandatory=True).count(),
            "completion_count": models.CourseEnrollment.objects.filter(
                company=company,
                status=models.CourseEnrollment.Status.COMPLETED,
            ).count(),
        },
    )


@login_required
def my_benefits(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    plans = list(
        models.BenefitPlan.objects.filter(company=company, is_active=True).order_by("name")
    )
    enrollments = {
        enrollment.plan_id: enrollment
        for enrollment in models.BenefitEnrollment.objects.filter(
            company=company,
            employee=employee_profile,
        ).select_related("plan")
    }
    for plan in plans:
        plan.employee_enrollment = enrollments.get(plan.id)

    return render(
        request,
        "employee/my_benefits.html",
        {
            "page_title": "My Benefits",
            "plans": plans,
        },
    )


@login_required
def enroll_benefit(request, plan_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    plan = get_object_or_404(models.BenefitPlan, id=plan_id, company=company, is_active=True)
    models.BenefitEnrollment.objects.update_or_create(
        company=company,
        plan=plan,
        employee=employee_profile,
        defaults={
            "status": models.BenefitEnrollment.Status.ENROLLED,
            "effective_date": timezone.localdate(),
        },
    )
    messages.success(request, "Benefit enrollment updated.")
    return redirect("payroll:my_benefits")


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def benefit_overview(request):
    company = get_user_company(request.user)
    plans = (
        models.BenefitPlan.objects.filter(company=company)
        .prefetch_related("enrollments")
        .order_by("name")
    )

    return render(
        request,
        "employee/benefit_overview.html",
        {
            "page_title": "Benefits Center",
            "plans": plans,
            "plan_count": plans.count(),
            "active_count": plans.filter(is_active=True).count(),
            "enrollment_count": models.BenefitEnrollment.objects.filter(company=company).count(),
        },
    )


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def workflow_overview(request):
    company = get_user_company(request.user)
    active_templates = models.WorkflowTemplate.objects.filter(
        company=company,
        is_active=True,
    ).order_by("workflow_type", "name")
    recent_executions = (
        models.WorkflowExecution.objects.filter(company=company)
        .select_related("template", "employee", "started_by")
        .order_by("-started_at")[:12]
    )

    return render(
        request,
        "employee/workflow_overview.html",
        {
            "page_title": "Workflow Operations",
            "active_templates": active_templates,
            "recent_executions": recent_executions,
            "execution_count": models.WorkflowExecution.objects.filter(
                company=company
            ).count(),
            "pending_count": models.WorkflowExecution.objects.filter(
                company=company,
                status=models.WorkflowExecution.Status.PENDING,
            ).count(),
            "completed_count": models.WorkflowExecution.objects.filter(
                company=company,
                status=models.WorkflowExecution.Status.COMPLETED,
            ).count(),
        },
    )


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


@login_required  # index and dashboard remain login_required for now, internal logic dictates content
def index(request):
    company = get_user_company(request.user)
    # Check if user is HR/Admin (superuser or has payroll permissions)
    if request.user.is_superuser or request.user.has_perm(
        "payroll.view_employeeprofile"
    ):
        # HR/Admin gets the current dashboard
        pay = models.PayrollRun.objects.filter(company=company, closed=True)

        closed_pay_periods = models.PayrollRun.objects.filter(
            company=company,
            closed=True,
        ).order_by("-paydays")

        # Use latest closed pay period for dashboard totals to avoid inflating values
        # with all historical payroll runs.
        recent_pay_period = closed_pay_periods.first()
        pending_leave_requests = models.LeaveRequest.objects.filter(
            employee__company=company,
            status="PENDING",
        )
        pending_iou_requests = models.IOU.objects.filter(
            employee_id__company=company,
            status="PENDING",
        )
        # Calculate totals for the most recent closed month
        if recent_pay_period:
            recent_period_entries = models.PayrollRunEntry.objects.filter(
                payroll_run=recent_pay_period,
                payroll_entry__company=company,
            )
            recent_month_total = (
                recent_period_entries.aggregate(total=Sum("payroll_entry__netpay"))["total"]
                or Decimal("0.00")
            )
            pay_count = recent_month_total
            processed_payments_count = recent_period_entries.count()
        else:
            recent_month_total = Decimal("0.00")
            pay_count = Decimal("0.00")
            processed_payments_count = 0

        previous_pay_period = closed_pay_periods[1:2].first()
        if previous_pay_period:
            previous_month_total = models.PayrollRunEntry.objects.filter(
                payroll_run=previous_pay_period,
                payroll_entry__company=company,
            ).aggregate(total=Sum("payroll_entry__netpay"))["total"] or Decimal("0.00")

            if previous_month_total > 0:
                percentage_increase = (
                    (recent_month_total - previous_month_total) / previous_month_total
                ) * 100
            else:
                percentage_increase = Decimal("0.00")
        else:
            previous_month_total = Decimal("0.00")
            percentage_increase = Decimal("0.00")

        pay_periods = models.PayrollRun.objects.filter(
            company=company,
            closed=True,
        ).order_by("paydays")
        pay_period_data = []
        pay_period_labels = []

        for period in pay_periods:
            total = models.PayrollRunEntry.objects.filter(
                payroll_run=period,
                payroll_entry__company=company,
            ).aggregate(
                total=Sum("payroll_entry__netpay")
            )["total"] or Decimal("0.00")

            if period.paydays:
                month_label = period.paydays.strftime("%b %Y")  # e.g., 'Jan 2025'

            pay_period_labels.append(month_label)
            pay_period_data.append(float(total))

        pay_period_trend_data = {
            "labels": json.dumps(pay_period_labels),
            "data": json.dumps(pay_period_data),
        }

        # Calculate total payee (tax) paid in the most recent pay period
        if recent_pay_period:
            total_payee_paid = models.PayrollRunEntry.objects.filter(
                payroll_run=recent_pay_period,
                payroll_entry__company=company,
            ).aggregate(total=Sum("payroll_entry__pays__employee_pay__payee"))[
                "total"
            ] or Decimal(
                "0.00"
            )
        else:
            total_payee_paid = Decimal("0.00")

        # Calculate total payee paid (net pay) in the most recent pay period
        if recent_pay_period:
            total_payee_net_paid = models.PayrollRunEntry.objects.filter(
                payroll_run=recent_pay_period,
                payroll_entry__company=company,
            ).aggregate(total=Sum("payroll_entry__netpay"))["total"] or Decimal("0.00")
        else:
            total_payee_net_paid = Decimal("0.00")

        # Calculate department distribution for the department chart
        department_distribution = models.EmployeeProfile.emp_objects.filter(
            company=company
        ).values("department__name").annotate(count=Count("id"))
        department_labels = json.dumps(
            [
                item["department__name"] if item["department__name"] else "Unassigned"
                for item in department_distribution
            ]
        )
        department_counts = json.dumps(
            [item["count"] for item in department_distribution]
        )

        emp = models.EmployeeProfile.emp_objects.filter(company=company)
        leave = models.LeaveRequest.objects.filter(employee__company=company)
        # iou = models.IOU.objects.all()
        count = emp.count()

        # print(f" leave: {leave.count()}")
        # print(f" graph data: {pay_period_data}")

        context = {
            "pay": pay,
            "emp": emp,
            "count": count,
            "pay_count": pay_count,
            "processed_payments_count": processed_payments_count,
            "leave": leave.count(),
            "recent_month_total": recent_month_total,
            "recent_pay_period": recent_pay_period,
            "previous_month_total": previous_month_total,
            "percentage_increase": percentage_increase,
            "total_payee_paid": total_payee_paid,
            "total_payee_net_paid": total_payee_net_paid,
            "pending": pending_leave_requests.count(),
            "pending_leave_requests_count": pending_leave_requests.count(),
            "pending_iou_requests_count": pending_iou_requests.count(),
            "pending_approvals_count": pending_leave_requests.count()
            + pending_iou_requests.count(),
            "pay_period_data": pay_period_trend_data["data"],
            "pay_period_labels": pay_period_trend_data["labels"],
            "department_labels": department_labels,
            "department_counts": department_counts,
            "recent_activities": get_recent_activities(limit=10, company=company),
        }
        return render(request, "index.html", context)
    else:
        # Regular employee gets their personal dashboard
        try:
            employee_profile = models.EmployeeProfile.emp_objects.get(user=request.user)

            # Get recent payslips for this employee
            recent_payslips = models.PayrollRunEntry.objects.filter(
                payroll_entry__pays__user=request.user,
                payroll_entry__company=company,
            ).order_by("-payroll_run__paydays")[:5]

            # Get notifications for this employee
            notifications = get_employee_notifications(employee_profile)

            # Get unread count
            unread_count = models.Notification.objects.filter(
                recipient=employee_profile, is_read=False
            ).count()

            # Count pending requests
            pending_requests_count = (
                models.LeaveRequest.objects.filter(
                    employee=employee_profile, status="PENDING"
                ).count()
                + models.IOU.objects.filter(
                    employee_id=employee_profile, status="PENDING"
                ).count()
            )

            context = {
                "emp": employee_profile,
                "recent_payslips": recent_payslips,
                "notifications": notifications,
                "pending_requests_count": pending_requests_count,
                "unread_count": unread_count,
            }
            return render(request, "employee_home.html", context)
        except models.EmployeeProfile.DoesNotExist:
            # If user has no employee profile, show a simple home page
            return render(request, "home_normal.html", {"employee_slug": None})


@login_required
def update_employee_profile(request):
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        raise Http404("Employee profile not found.")

    if request.method == "POST":
        form = EmployeeProfileUpdateForm(
            request.POST, request.FILES, instance=employee_profile
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("payroll:employee_profile")
    else:
        form = EmployeeProfileUpdateForm(instance=employee_profile)

    return render(request, "employee/update_profile.html", {"form": form})


@login_required
def dashboard(request):
    user = request.user
    company = get_user_company(user)

    if user.is_superuser:  # Superuser gets admin dashboard
        return render(request, "dashboard_admin_new.html")
    # Changed from group check to permission check for HR dashboard
    elif request.user.has_perm(
        "payroll.view_employeeprofile"
    ):  # Representative permission for HR
        employee_count = models.EmployeeProfile.objects.filter(company=company).count()
        leave_count = models.LeaveRequest.objects.filter(
            employee__company=company, status="PENDING"
        ).count()
        iou_count = models.IOU.objects.filter(
            employee_id__company=company, status="PENDING"
        ).count()
        allowance_count = models.Allowance.objects.filter(
            employee__company=company
        ).count()
        context = {
            "employee_count": employee_count,
            "leave_count": leave_count,
            "iou_count": iou_count,
            "allowance_count": allowance_count,
            "empty_list": [],  # For empty for loop handling in templates
        }
        return render(request, "employee/dashboard_new.html", context)
    else:  # Regular user dashboard
        reviewer_profile = getattr(request.user, "employee_user", None)
        assignments = models.AppraisalAssignment.objects.none()
        pending_assignment_count = 0
        completed_assignment_count = 0
        next_assignment = None
        recent_payslips = models.PayrollRunEntry.objects.none()
        recent_leaves = models.LeaveRequest.objects.none()
        pending_requests_count = 0
        net_salary = 0

        if reviewer_profile:
            recent_payslips = models.PayrollRunEntry.objects.filter(
                payroll_entry__pays=reviewer_profile,
                payroll_entry__company=company,
            ).order_by("-payroll_run__paydays")[:5]
            recent_leaves = models.LeaveRequest.objects.filter(
                employee=reviewer_profile
            ).order_by("-start_date")[:5]
            pending_requests_count = (
                models.LeaveRequest.objects.filter(
                    employee=reviewer_profile,
                    status="PENDING",
                ).count()
                + models.IOU.objects.filter(
                    employee_id=reviewer_profile,
                    status="PENDING",
                ).count()
            )
            net_salary = reviewer_profile.net_pay or 0
            assignments = (
                models.AppraisalAssignment.objects.filter(
                    appraiser=reviewer_profile,
                    appraisal__company=company,
                )
                .select_related("appraisal", "appraisee")
                .order_by("appraisal__end_date", "id")
            )
            reviewed_pairs = set(
                models.Review.objects.filter(
                    reviewer=reviewer_profile,
                    appraisal__company=company,
                ).values_list("appraisal_id", "employee_id")
            )

            pending_assignments = []
            for assignment in assignments:
                assignment.has_review = (
                    assignment.appraisal_id,
                    assignment.appraisee_id,
                ) in reviewed_pairs
                if not assignment.has_review:
                    pending_assignments.append(assignment)

            completed_assignment_count = assignments.count() - len(pending_assignments)
            pending_assignment_count = len(pending_assignments)
            next_assignment = pending_assignments[0] if pending_assignments else assignments.first()

        context = {
            "assignments": assignments,
            "pending_assignment_count": pending_assignment_count,
            "completed_assignment_count": completed_assignment_count,
            "next_assignment": next_assignment,
            "recent_payslips": recent_payslips,
            "recent_leaves": recent_leaves,
            "pending_requests": pending_requests_count,
            "net_salary": net_salary,
            "empty_list": [],  # For empty for loop handling in templates
        }
        return render(request, "dashboard_user_new.html", context)


@login_required
def standup_dashboard(request):
    return render(request, "standup/dashboard.html")


@permission_required(
    "payroll.view_employeeprofile", raise_exception=True
)  # Example permission for HR dashboard
def hr_dashboard(request):
    company = get_user_company(request.user)
    # Counts for new "Approvals" section links
    pending_leave_requests_count = models.LeaveRequest.objects.filter(
        employee__company=company,
        status="PENDING",
    ).count()
    pending_iou_requests_count = models.IOU.objects.filter(
        employee_id__company=company,
        status="PENDING",
    ).count()

    employee_qs = models.EmployeeProfile.objects.filter(company=company)
    total_employees = employee_qs.count()
    active_employees_count = employee_qs.filter(status="active").count()
    suspended_employees_count = employee_qs.filter(status="suspended").count()
    terminated_employees_count = employee_qs.filter(status="terminated").count()
    recent_performance_reviews = models.Appraisal.objects.order_by("-end_date")[:5]
    appraisal_qs = models.Appraisal.objects.filter(company=company)
    today = timezone.now().date()
    active_appraisal_count = appraisal_qs.filter(
        start_date__lte=today, end_date__gte=today
    ).count()
    total_appraisal_assignments = models.AppraisalAssignment.objects.filter(
        appraisal__company=company
    ).count()
    completed_appraisal_reviews = (
        models.Review.objects.filter(appraisal__company=company)
        .values("appraisal_id", "employee_id", "reviewer_id")
        .distinct()
        .count()
    )
    pending_appraisal_reviews = max(
        total_appraisal_assignments - completed_appraisal_reviews, 0
    )
    department_distribution = models.EmployeeProfile.objects.filter(company=company).values(
        "department__name"
    ).annotate(count=Count("id"))
    department_labels = json.dumps(
        [item["department__name"] for item in department_distribution]
    )
    department_counts = json.dumps([item["count"] for item in department_distribution])

    leave_status_chart_data = json.dumps(
        [
            pending_leave_requests_count,  # Use already computed value
            models.LeaveRequest.objects.filter(
                employee__company=company, status="APPROVED"
            ).count(),
            models.LeaveRequest.objects.filter(
                employee__company=company, status="REJECTED"
            ).count(),
        ]
    )

    # Calculate total salary amount paid
    from payroll.models import PayrollRunEntry

    total_salary_paid = (
        PayrollRunEntry.objects.filter(payroll_entry__company=company).aggregate(
            total=Sum("payroll_entry__netpay")
        )["total"]
        or 0
    )

    context = {
        "total_employees": total_employees,
        "active_employees_count": active_employees_count,
        "suspended_employees_count": suspended_employees_count,
        "terminated_employees_count": terminated_employees_count,
        "active_leave_requests": pending_leave_requests_count,  # Original name, kept for compatibility
        "leave_count": pending_leave_requests_count,  # Compatibility with dashboard template fallback
        "pending_leave_requests_count_for_link": pending_leave_requests_count,  # Explicit for new section
        "iou_count": pending_iou_requests_count,  # Compatibility with dashboard template fallback
        "pending_iou_requests_count_for_link": pending_iou_requests_count,  # Explicit for new section
        "allowance_count": models.Allowance.objects.filter(
            employee__company=company
        ).count(),  # Compatibility with HR widgets
        "recent_performance_reviews": recent_performance_reviews,
        "appraisal_count": appraisal_qs.count(),
        "active_appraisal_count": active_appraisal_count,
        "pending_appraisal_reviews": pending_appraisal_reviews,
        "department_labels": department_labels,
        "department_counts": department_counts,
        "leave_status_counts": leave_status_chart_data,  # For chart
        "iou_status_counts": pending_iou_requests_count,  # Original name, kept for compatibility
        "total_salary_paid": total_salary_paid,  # New field for total salary paid
        "empty_list": [],  # For empty for loop handling in templates
    }
    return render(request, "employee/dashboard_new.html", context)


@permission_required("payroll.view_employeeprofile", raise_exception=True)
def employee_list(request):
    company = get_user_company(request.user)
    query = request.GET.get("q")
    department_filter = request.GET.get("department")
    employees = models.EmployeeProfile.objects.filter(company=company)
    if query:
        employees = employees.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(job_title__icontains=query)
        )
    if department_filter:
        employees = employees.filter(department__id=department_filter)
    departments = models.Department.objects.filter(company=company)
    active_employees_count = employees.filter(status="active").count()
    suspended_employees_count = employees.filter(status="suspended").count()
    terminated_employees_count = employees.filter(status="terminated").count()
    return render(
        request,
        "employee/employee_list_new.html",
        {
            "employees": employees,
            "departments": departments,
            "active_employees_count": active_employees_count,
            "suspended_employees_count": suspended_employees_count,
            "terminated_employees_count": terminated_employees_count,
        },
    )


@permission_required(
    ["payroll.add_employeeprofile", "users.add_customuser"], raise_exception=True
)
def add_employee(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        user_form = user_forms.CustomUserCreationForm(request.POST)
        employee_form = EmployeeProfileForm(request.POST, request.FILES, user=request.user)
        if user_form.is_valid() and employee_form.is_valid():
            with transaction.atomic():
                submitted_profile = employee_form.save(commit=False)
                user = user_form.save(commit=False)
                user.company = company
                user.active_company = company
                user.first_name = employee_form.cleaned_data.get("first_name", "")
                user.last_name = employee_form.cleaned_data.get("last_name", "")
                user.save()

                employee_profile = getattr(user, "employee_user", None)
                if employee_profile is None:
                    employee_profile = submitted_profile

                for field_name in employee_form.fields:
                    setattr(
                        employee_profile,
                        field_name,
                        getattr(submitted_profile, field_name),
                    )

                employee_profile.company = company
                employee_profile.user = user
                employee_profile.email = user.email
                employee_profile.first_name = user.first_name
                employee_profile.last_name = user.last_name
                employee_profile.save()

                _start_workflow_execution(
                    company=company,
                    employee_profile=employee_profile,
                    workflow_type=models.WorkflowTemplate.WorkflowType.ONBOARDING,
                    started_by=request.user,
                    trigger_event="employee.created",
                )
            messages.success(request, "Employee added successfully!")
            return redirect("payroll:employee_list")
    else:
        user_form = user_forms.CustomUserCreationForm()
        employee_form = EmployeeProfileForm(user=request.user)
    context = {"user_form": user_form, "employee_form": employee_form}
    return render(request, "employee/add_employee.html", context)


def input_id(request):  # No specific permissions, seems like a generic utility page
    return render(request, "pay/input.html")


@permission_required("payroll.change_employeeprofile", raise_exception=True)
def update_employee(request, id):
    company = get_user_company(request.user)
    employee = get_object_or_404(models.EmployeeProfile, id=id, company=company)
    form = EmployeeProfileForm(request.POST or None, instance=employee, user=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "Employee updated successfully!!")
        return redirect(
            "payroll:employee_list"
        )  # Consider redirecting to employee list or profile
    return render(request, "employee/update_employee.html", {"form": form})


# class EmployeeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
#     model = models.EmployeeProfile
#     form_class = EmployeeProfileForm
#     template_name = (
#         "employee/add.html"  # This might conflict with FBV add_employee's template
#     )
#     success_url = reverse_lazy("payroll:employee_list")
#     permission_required = (
#         "payroll.add_employeeprofile",
#         "users.add_customuser",
#     )  # Assuming form also handles CustomUser creation

#     def form_valid(self, form):
#         messages.success(self.request, "Employee created successfully.")
#         return super().form_valid(form)


# class EmployeeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
#     model = models.EmployeeProfile
#     form_class = EmployeeProfileForm
#     template_name = (
#         "employee/update.html"  # May conflict with FBV update_employee template
#     )
#     success_url = reverse_lazy("payroll:employee_list")
#     permission_required = "payroll.change_employeeprofile"

#     def form_valid(self, form):
#         messages.success(self.request, "Employee updated successfully.")
#         return super().form_valid(form)


# class EmployeeDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
#     model = models.EmployeeProfile
#     template_name = "employee/delete.html"
#     success_url = reverse_lazy("payroll:employee_list")
#     permission_required = "payroll.delete_employeeprofile"

#     def delete(self, request, *args, **kwargs):
#         messages.success(self.request, "Employee deleted successfully.")
#         return super().delete(request, *args, **kwargs)


@permission_required("payroll.delete_employeeprofile", raise_exception=True)
@require_POST
def delete_employee(request, id=None):  # FBV for delete
    company = get_user_company(request.user)
    if id is None:
        raw_id = request.POST.get("id")
        try:
            id = int(raw_id) if raw_id is not None else None
        except (TypeError, ValueError):
            id = None
    if id is None:
        messages.error(request, "No employee selected for deletion.")
        return redirect("payroll:employee_list")
    employee_profile = get_object_or_404(models.EmployeeProfile, id=id, company=company)
    _start_workflow_execution(
        company=company,
        employee_profile=employee_profile,
        workflow_type=models.WorkflowTemplate.WorkflowType.OFFBOARDING,
        started_by=request.user,
        trigger_event="employee.deleted",
    )
    employee_profile.delete()
    messages.success(request, "Employee deleted Successfully!!")
    return redirect("payroll:employee_list")  # Ensure redirect after delete


@login_required
def employee(request, user_id: int):
    company = get_user_company(request.user)
    target_user_profile = get_object_or_404(
        models.EmployeeProfile, user_id=user_id, company=company
    )
    print(target_user_profile.user_id, request.user.id)

    # Check if request.user is viewing their own profile or has general view permission
    if request.user.id == user_id or request.user.has_perm(
        "payroll.view_employeeprofile"
    ):
        employee_profile_to_display = target_user_profile
    else:
        return HttpResponseForbidden("You are not authorized to view this profile.")

    pay = models.PayrollRunEntry.objects.filter(
        payroll_entry__pays__user_id=employee_profile_to_display.user.id,
        payroll_entry__company=company,
    )
    iou_slips = models.IOU.objects.filter(
        employee_id=employee_profile_to_display,
        employee_id__company=company,
    ).order_by("-created_at")
    context = {"emp": employee_profile_to_display, "pay": pay, "iou_slips": iou_slips}
    return render(request, "employee/profile_new.html", context)


class AppraisalListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = models.Appraisal
    template_name = "reviews/appraisal_list_new.html"
    permission_required = "payroll.view_appraisal"

    def get_queryset(self):
        company = get_user_company(self.request.user)
        queryset = (
            models.Appraisal.objects.annotate(
                overall_avg=Avg("review__rating__rating"),
                assignments_count=Count("appraisalassignment", distinct=True),
                reviews_count=Count("review", distinct=True),
            )
            .order_by("-start_date", "-id")
            .distinct()
        )
        if company:
            queryset = queryset.filter(company=company)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        appraisals = list(context["object_list"])
        completed = 0
        in_progress = 0

        for appraisal in appraisals:
            status_label = "Pending"
            status_css = "bg-secondary-100 text-secondary-800"
            if appraisal.start_date <= today <= appraisal.end_date:
                status_label = "In Progress"
                status_css = "bg-warning-100 text-warning-800"
                in_progress += 1
            elif appraisal.end_date < today:
                status_label = "Completed"
                status_css = "bg-success-100 text-success-800"
                completed += 1

            appraisal.status_label = status_label
            appraisal.status_css = status_css
            if appraisal.overall_avg is not None:
                appraisal.overall_avg_percentage = appraisal.overall_avg * 20
            else:
                appraisal.overall_avg_percentage = None

        avg_rating = [
            item.overall_avg for item in appraisals if item.overall_avg is not None
        ]
        context["total_appraisals"] = len(appraisals)
        context["completed_appraisals"] = completed
        context["in_progress_appraisals"] = in_progress
        context["average_score"] = round((sum(avg_rating) / len(avg_rating)) * 20, 1) if avg_rating else 0
        return context


class AppraisalDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = models.Appraisal
    template_name = "reviews/appraisal_detail.html"
    permission_required = "payroll.view_appraisal"

    def get_queryset(self):
        company = get_user_company(self.request.user)
        queryset = models.Appraisal.objects.all()
        if company:
            queryset = queryset.filter(company=company)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        appraisal = self.get_object()
        reviews = models.Review.objects.filter(appraisal=appraisal).select_related(
            "employee", "reviewer"
        )
        assignments = models.AppraisalAssignment.objects.filter(
            appraisal=appraisal
        ).select_related("appraisee", "appraiser")

        completed_reviews = reviews.count()
        pending_reviews = max(assignments.count() - completed_reviews, 0)

        ratings = models.Rating.objects.filter(review__in=reviews).select_related("metric")
        metrics = models.Metric.objects.all()

        metric_ratings = {}
        for metric in metrics:
            metric_ratings[metric.name] = {"ratings": [], "avg": 0}

        for rating in ratings:
            metric_ratings[rating.metric.name]["ratings"].append(rating.rating)

        for metric_name, data in metric_ratings.items():
            if data["ratings"]:
                data["avg"] = sum(data["ratings"]) / len(data["ratings"])

        overall_avg = 0
        if ratings:
            overall_avg = sum([rating.rating for rating in ratings]) / ratings.count()

        context["completed_reviews"] = completed_reviews
        context["pending_reviews"] = pending_reviews
        context["metric_ratings"] = metric_ratings
        context["overall_avg"] = overall_avg

        return context


class AppraisalCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = models.Appraisal
    form_class = AppraisalForm
    template_name = "reviews/appraisal_form.html"
    success_url = reverse_lazy("payroll:appraisal_list")
    permission_required = "payroll.add_appraisal"

    def form_valid(self, form):
        form.instance.company = get_user_company(self.request.user)
        return super().form_valid(form)


class AppraisalUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = models.Appraisal
    form_class = AppraisalForm
    template_name = "reviews/appraisal_form.html"
    success_url = reverse_lazy("payroll:appraisal_list")
    permission_required = "payroll.change_appraisal"

    def get_queryset(self):
        company = get_user_company(self.request.user)
        queryset = models.Appraisal.objects.all()
        if company:
            queryset = queryset.filter(company=company)
        return queryset


class AppraisalDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = models.Appraisal
    template_name = "reviews/appraisal_confirm_delete.html"
    success_url = reverse_lazy("payroll:appraisal_list")
    permission_required = "payroll.delete_appraisal"

    def get_queryset(self):
        company = get_user_company(self.request.user)
        queryset = models.Appraisal.objects.all()
        if company:
            queryset = queryset.filter(company=company)
        return queryset


class ReviewCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = models.Review
    form_class = ReviewForm
    template_name = "reviews/review_form.html"
    permission_required = "payroll.add_review"

    def _rating_formset_class(self):
        metric_count = max(models.Metric.objects.count(), 1)
        return inlineformset_factory(
            models.Review,
            models.Rating,
            form=RatingForm,
            extra=metric_count,
            can_delete=False,
        )

    def _rating_formset(self, data=None):
        rating_formset_class = self._rating_formset_class()
        initial = [{"metric": metric.pk} for metric in models.Metric.objects.all()]
        if data is not None:
            return rating_formset_class(data, prefix="ratings")
        return rating_formset_class(prefix="ratings", initial=initial)

    def _get_targets(self):
        appraisal = get_object_or_404(models.Appraisal, pk=self.kwargs["appraisal_pk"])
        employee = get_object_or_404(models.EmployeeProfile, pk=self.kwargs["employee_pk"])
        company = get_user_company(self.request.user)
        if company and (
            appraisal.company_id != company.id or employee.company_id != company.id
        ):
            raise Http404("Appraisal or employee not found in your company.")
        return appraisal, employee

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        appraisal, employee = self._get_targets()
        kwargs["instance"] = models.Review(
            appraisal=appraisal,
            employee=employee,
            reviewer=self.request.user.employee_user,
        )
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        appraisal, employee = self._get_targets()
        requester_profile = getattr(request.user, "employee_user", None)
        if requester_profile is None:
            raise PermissionDenied("Employee profile is required to submit a review.")

        has_assignment = models.AppraisalAssignment.objects.filter(
            appraisal=appraisal, appraisee=employee, appraiser=requester_profile
        ).exists()
        if not (request.user.has_perm("payroll.add_review") and has_assignment):
            raise PermissionDenied("You are not assigned to submit this review.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rating_formset"] = self._rating_formset(
            data=self.request.POST if self.request.POST else None
        )
        return context

    def _validate_unique_metrics(self, rating_formset):
        seen_metric_ids = set()
        for rating_form in rating_formset.forms:
            if rating_form.cleaned_data.get("DELETE"):
                continue
            metric = rating_form.cleaned_data.get("metric")
            if not metric:
                continue
            if metric.pk in seen_metric_ids:
                rating_form.add_error("metric", "Each metric can only be rated once.")
                return False
            seen_metric_ids.add(metric.pk)
        return True

    def form_valid(self, form):
        context = self.get_context_data()
        rating_formset = context["rating_formset"]
        if not rating_formset.is_valid() or not self._validate_unique_metrics(rating_formset):
            return self.render_to_response(self.get_context_data(form=form))
        appraisal, employee = self._get_targets()
        with transaction.atomic():
            review = form.save(commit=False)
            review.full_clean()
            review.save()
            rating_formset.instance = review
            rating_formset.save()
            self.object = review
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy(
            "payroll:appraisal_detail", kwargs={"pk": self.kwargs["appraisal_pk"]}
        )


class ReviewAccessMixin(LoginRequiredMixin):
    required_permission = None

    def _review_in_scope(self):
        queryset = models.Review.objects.select_related(
            "appraisal", "employee", "reviewer"
        )
        company = get_user_company(self.request.user)
        if company:
            queryset = queryset.filter(appraisal__company=company)
        return queryset

    def get_queryset(self):
        return self._review_in_scope()

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        is_owner = (
            getattr(request.user, "employee_user", None) in [obj.reviewer, obj.employee]
        )
        has_permission = (
            request.user.is_superuser
            or is_owner
            or (
                self.required_permission
                and request.user.has_perm(self.required_permission)
            )
        )
        if not has_permission:
            raise PermissionDenied("You are not allowed to access this review.")
        return super().dispatch(request, *args, **kwargs)


class ReviewUpdateView(ReviewAccessMixin, UpdateView):
    model = models.Review
    form_class = ReviewForm
    template_name = "reviews/review_form.html"
    required_permission = "payroll.change_review"

    def _rating_formset_class(self):
        return inlineformset_factory(
            models.Review,
            models.Rating,
            fields=("metric", "rating", "comments"),
            extra=0,
            can_delete=False,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rating_formset_class = self._rating_formset_class()
        if self.request.POST:
            context["rating_formset"] = rating_formset_class(
                self.request.POST, instance=self.object, prefix="ratings"
            )
        else:
            context["rating_formset"] = rating_formset_class(
                instance=self.object, prefix="ratings"
            )
        return context

    def _validate_unique_metrics(self, rating_formset):
        seen_metric_ids = set()
        for rating_form in rating_formset.forms:
            if rating_form.cleaned_data.get("DELETE"):
                continue
            metric = rating_form.cleaned_data.get("metric")
            if not metric:
                continue
            if metric.pk in seen_metric_ids:
                rating_form.add_error("metric", "Each metric can only be rated once.")
                return False
            seen_metric_ids.add(metric.pk)
        return True

    def form_valid(self, form):
        context = self.get_context_data()
        rating_formset = context["rating_formset"]
        if not rating_formset.is_valid() or not self._validate_unique_metrics(rating_formset):
            return self.render_to_response(self.get_context_data(form=form))
        with transaction.atomic():
            self.object = form.save()
            rating_formset.instance = self.object
            rating_formset.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "payroll:appraisal_detail", kwargs={"pk": self.object.appraisal.pk}
        )


class ReviewDetailView(ReviewAccessMixin, DetailView):
    model = models.Review
    template_name = "reviews/review_detail.html"
    required_permission = "payroll.view_review"


class ReviewDeleteView(ReviewAccessMixin, DeleteView):
    model = models.Review
    template_name = "reviews/review_confirm_delete.html"
    required_permission = "payroll.delete_review"

    def get_success_url(self):
        return reverse_lazy(
            "payroll:appraisal_detail", kwargs={"pk": self.object.appraisal.pk}
        )


class AssignAppraisalView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    form_class = AppraisalAssignmentForm
    template_name = "reviews/appraisal_assign.html"
    success_url = reverse_lazy("payroll:appraisal_list")
    permission_required = "payroll.add_appraisalassignment"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Appraisal assignment successful.")
        return super().form_valid(form)
