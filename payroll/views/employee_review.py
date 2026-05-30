"""
Review views.
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
from payroll.forms import ReviewForm, RatingForm, AppraisalAssignmentForm

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

