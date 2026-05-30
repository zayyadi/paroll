"""
Surveys views.
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

