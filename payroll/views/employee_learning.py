"""
Learning views.
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

