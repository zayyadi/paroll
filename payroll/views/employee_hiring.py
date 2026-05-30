"""
Hiring views.
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
from payroll.forms import HiringRequisitionForm, HiringCandidateForm, HiringScorecardForm, JobOfferForm

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
    open_requisitions = (
        models.JobRequisition.objects.filter(
            company=company,
            status=models.JobRequisition.Status.OPEN,
        )
        .select_related("position", "hiring_manager")
        .order_by("-opened_at")[:8]
    )
    active_candidate_statuses = [
        models.HiringCandidate.Status.NEW,
        models.HiringCandidate.Status.IN_PROCESS,
        models.HiringCandidate.Status.OFFER,
    ]
    active_candidates = (
        models.HiringCandidate.objects.filter(
            company=company,
            status__in=active_candidate_statuses,
        )
        .select_related("requisition", "current_stage")
        .order_by("-applied_at")[:10]
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
            "open_requisition_count": models.JobRequisition.objects.filter(
                company=company,
                status=models.JobRequisition.Status.OPEN,
            ).count(),
            "active_candidate_count": models.HiringCandidate.objects.filter(
                company=company,
                status__in=active_candidate_statuses,
            ).count(),
            "open_offer_count": models.JobOffer.objects.filter(
                company=company,
                status=models.JobOffer.Status.SENT,
            ).count(),
            "open_requisitions": open_requisitions,
            "active_candidates": active_candidates,
        },
    )


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def hiring_workspace(request):
    company = get_user_company(request.user)
    models.create_standard_hiring_stages(company)
    active_candidate_statuses = [
        models.HiringCandidate.Status.NEW,
        models.HiringCandidate.Status.IN_PROCESS,
        models.HiringCandidate.Status.OFFER,
    ]
    requisitions = (
        models.JobRequisition.objects.filter(company=company)
        .select_related("position", "hiring_manager")
        .prefetch_related("candidates")
        .order_by("-opened_at")[:25]
    )
    candidates = (
        models.HiringCandidate.objects.filter(company=company)
        .select_related("requisition", "current_stage")
        .prefetch_related("scorecards", "offers")
        .order_by("-applied_at")[:50]
    )
    active_stages = models.HiringStage.objects.filter(
        company=company,
        is_active=True,
    ).order_by("sequence", "name")
    offers = (
        models.JobOffer.objects.filter(company=company)
        .select_related("candidate", "created_by")
        .order_by("-created_at")[:20]
    )

    return render(
        request,
        "employee/hiring_workspace.html",
        {
            "page_title": "Hiring Workspace",
            "requisitions": requisitions,
            "candidates": candidates,
            "active_stages": active_stages,
            "offers": offers,
            "open_requisition_count": models.JobRequisition.objects.filter(
                company=company,
                status=models.JobRequisition.Status.OPEN,
            ).count(),
            "active_candidate_count": models.HiringCandidate.objects.filter(
                company=company,
                status__in=active_candidate_statuses,
            ).count(),
            "open_offer_count": models.JobOffer.objects.filter(
                company=company,
                status=models.JobOffer.Status.SENT,
            ).count(),
            "requisition_form": HiringRequisitionForm(company=company),
            "candidate_form": HiringCandidateForm(company=company),
            "scorecard_form": HiringScorecardForm(company=company),
            "offer_form": JobOfferForm(),
        },
    )


@login_required
@require_POST
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def hiring_requisition_create(request):
    company = get_user_company(request.user)
    form = HiringRequisitionForm(request.POST, company=company)
    if form.is_valid():
        requisition = form.save(commit=False)
        requisition.company = company
        requisition.opened_by = request.user
        requisition.save()
        messages.success(request, "Job requisition opened.")
    else:
        messages.error(request, "Could not open requisition. Check the hiring form.")
    return redirect("payroll:hiring_workspace")


@login_required
@require_POST
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def hiring_candidate_create(request):
    company = get_user_company(request.user)
    form = HiringCandidateForm(request.POST, company=company)
    if form.is_valid():
        stages = models.create_standard_hiring_stages(company)
        sourced_stage = next(
            stage
            for stage in stages
            if stage.stage_type == models.HiringStage.StageType.SOURCED
        )
        candidate = form.save(commit=False)
        candidate.company = company
        candidate.current_stage = sourced_stage
        candidate.status = models.HiringCandidate.Status.NEW
        candidate.save()
        messages.success(request, "Candidate added to the hiring pipeline.")
    else:
        messages.error(request, "Could not add candidate. Check consent and required fields.")
    return redirect("payroll:hiring_workspace")


@login_required
@require_POST
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def hiring_scorecard_create(request, candidate_id):
    company = get_user_company(request.user)
    candidate = get_object_or_404(models.HiringCandidate, pk=candidate_id, company=company)
    form = HiringScorecardForm(request.POST, company=company)
    if form.is_valid():
        models.record_candidate_scorecard(
            candidate=candidate,
            stage=form.cleaned_data["stage"],
            interviewer=request.user,
            competency_scores=form.cleaned_data["competency_scores"],
            recommendation=form.cleaned_data["recommendation"],
            notes=form.cleaned_data["notes"],
        )
        messages.success(request, "Structured scorecard submitted.")
    else:
        messages.error(request, "Could not submit scorecard. Use numeric 1-5 JSON scores.")
    return redirect("payroll:hiring_workspace")


@login_required
@require_POST
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def hiring_candidate_advance(request, candidate_id):
    company = get_user_company(request.user)
    candidate = get_object_or_404(models.HiringCandidate, pk=candidate_id, company=company)
    next_stage = get_object_or_404(
        models.HiringStage,
        pk=request.POST.get("next_stage"),
        company=company,
        is_active=True,
    )
    try:
        models.advance_candidate(candidate, next_stage, advanced_by=request.user)
        messages.success(request, f"Candidate moved to {next_stage.name}.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("payroll:hiring_workspace")


@login_required
@require_POST
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def hiring_offer_create(request, candidate_id):
    company = get_user_company(request.user)
    candidate = get_object_or_404(models.HiringCandidate, pk=candidate_id, company=company)
    form = JobOfferForm(request.POST)
    if form.is_valid():
        offer = models.create_job_offer(
            candidate=candidate,
            title=form.cleaned_data["title"],
            employment_type=form.cleaned_data["employment_type"],
            salary_amount=form.cleaned_data["salary_amount"],
            currency=form.cleaned_data["currency"],
            start_date=form.cleaned_data["start_date"],
            created_by=request.user,
            terms=form.cleaned_data["terms"],
        )
        offer.expires_at = form.cleaned_data["expires_at"]
        offer.save(update_fields=["expires_at", "updated_at"])
        messages.success(request, "Offer created and candidate marked as offer stage.")
    else:
        messages.error(request, "Could not create offer. Check the offer fields.")
    return redirect("payroll:hiring_workspace")


@login_required
@require_POST
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def hiring_offer_accept(request, offer_id):
    company = get_user_company(request.user)
    offer = get_object_or_404(models.JobOffer, pk=offer_id, company=company)
    models.accept_job_offer(offer, accepted_by=request.user)
    messages.success(request, "Offer accepted and onboarding workflow started.")
    return redirect("payroll:hiring_workspace")

