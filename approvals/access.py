"""Visibility and policy administration share the same company boundary."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from company.models import CompanyMembership
from .models import ApprovalRequest
from .permissions import user_in_company, has_company_permission, can_decide


def selected_company(user):
    company = getattr(user, "active_company", None) or getattr(user, "company", None)
    if not user_in_company(user, company):
        raise PermissionDenied("Select a company you belong to.")
    return company


def company_administrator(user, company) -> bool:
    return (
        user_in_company(user, company)
        and CompanyMembership.objects.filter(
            user=user, company=company, role__in=["owner", "admin"]
        ).exists()
    )


def can_manage_policies(user, company) -> bool:
    return company_administrator(user, company) or has_company_permission(
        user, company, "approvals.configure_policy"
    )


def visible_requests(user):
    company = selected_company(user)
    scoped = (
        ApprovalRequest.objects.filter(company=company)
        .select_related("requester", "company", "content_type")
        .prefetch_related("decisions", "events")
    )
    if company_administrator(user, company):
        return scoped
    own = list(
        scoped.filter(Q(requester=user) | Q(decisions__actor=user)).values_list(
            "pk", flat=True
        )
    )
    eligible = [
        request.pk
        for request in scoped.filter(status="PENDING")
        if can_decide(request, user)
    ]
    return scoped.filter(pk__in=set(own + eligible))


def visible_source_requests(user):
    """Limit full audit snapshots using domain confidentiality rules."""
    from .registry import get_action

    visible = visible_requests(user)
    hidden_ids = []
    for approval in visible:
        try:
            visibility = get_action(approval.action).source_visibility
        except ValidationError:
            hidden_ids.append(approval.pk)
            continue
        if visibility is not None:
            source = approval.source
            if source is None or not visibility(source, user):
                hidden_ids.append(approval.pk)
    return visible.exclude(pk__in=hidden_ids)
