"""
Appraisal views.
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
from payroll.forms import AppraisalForm, AppraisalAssignmentForm

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
            status_css = "bg-info"
            if appraisal.start_date <= today <= appraisal.end_date:
                status_label = "In Progress"
                status_css = "bg-warning"
                in_progress += 1
            elif appraisal.end_date < today:
                status_label = "Completed"
                status_css = "bg-success"
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

