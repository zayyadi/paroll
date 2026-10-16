from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .access import selected_company, can_manage_policies, visible_requests
from .models import ApprovalPolicy
from .permissions import can_decide
from .presentation import request_context, action_label
from .forms import PolicyForm, StageFormSet
from .registry import get_action
from .services import decide_approval, cancel_approval


@login_required
def inbox(request):
    rows = visible_requests(request.user)
    status = request.GET.get("status", "PENDING")
    if status in ("PENDING", "APPROVED", "REJECTED", "CANCELLED"):
        rows = rows.filter(status=status)
    company = selected_company(request.user)
    page = Paginator(rows, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "approvals/inbox.html",
        {
            "rows": [
                (row, action_label(row.action), can_decide(row, request.user))
                for row in page
            ],
            "page": page,
            "status": status,
            "can_manage": can_manage_policies(request.user, company),
        },
    )


@login_required
def detail(request, pk):
    approval = get_object_or_404(visible_requests(request.user), pk=pk)
    context = request_context(approval, user=request.user)
    context.update(
        can_approve=can_decide(approval, request.user),
        can_cancel=approval.status == "PENDING"
        and approval.requester_id == request.user.pk,
    )
    return render(request, "approvals/detail.html", context)


@login_required
@require_POST
def decision(request, pk, operation):
    approval = get_object_or_404(visible_requests(request.user), pk=pk)
    try:
        if operation == "cancel":
            cancel_approval(
                approval=approval,
                actor=request.user,
                reason=request.POST.get("comment", ""),
            )
        else:
            decide_approval(
                approval=approval,
                actor=request.user,
                decision=operation.upper(),
                comment=request.POST.get("comment", ""),
            )
    except ValidationError as exc:
        context = request_context(approval, user=request.user)
        context.update(
            error=" ".join(exc.messages),
            can_approve=can_decide(approval, request.user),
            can_cancel=approval.status == "PENDING"
            and approval.requester_id == request.user.pk,
        )
        return render(request, "approvals/detail.html", context, status=400)
    messages.success(request, "Approval request updated.")
    return redirect("approvals:detail", pk=pk)


@login_required
def policies(request, pk=None):
    company = selected_company(request.user)
    if not can_manage_policies(request.user, company):
        raise PermissionDenied("Company policy authority is required.")
    instance = get_object_or_404(ApprovalPolicy, pk=pk, company=company) if pk else None
    initial = (
        [
            {
                "name": s.get("name", ""),
                "require_authority": not bool(s.get("approver_ids")),
                "approvers": s.get("approver_ids", []),
                "ORDER": index + 1,
            }
            for index, s in enumerate(instance.stages)
        ]
        if instance
        else []
    )
    form = PolicyForm(request.POST or None, instance=instance, company=company)
    stages = StageFormSet(
        request.POST or None,
        initial=initial,
        prefix="stages",
        form_kwargs={"company": company},
    )
    if request.method == "POST" and form.is_valid() and stages.is_valid():
        permission = get_action(form.cleaned_data["action"]).permission
        policy = form.save(commit=False)
        policy.stages = [
            {
                "name": s.cleaned_data.get("name", ""),
                "permission": permission,
                "approver_ids": list(
                    s.cleaned_data["approvers"].values_list("pk", flat=True)
                ),
            }
            for s in stages.ordered_forms
        ]
        try:
            policy.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                "Approval policy saved. Submitted requests retain their original workflow.",
            )
            return redirect("approvals:policies")
    return render(
        request,
        "approvals/policies.html",
        {
            "form": form,
            "stages": stages,
            "policies": ApprovalPolicy.objects.filter(company=company),
            "editing": instance,
        },
    )
