from django.core.exceptions import PermissionDenied
from company.models import CompanyMembership


def user_in_company(user, company) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    company_id = getattr(company, "pk", company)
    from company.models import Company
    if not Company.objects.filter(pk=company_id, is_active=True).exists():
        return False
    selected = getattr(user, "active_company_id", None) or getattr(
        user, "company_id", None
    )
    if not company_id or selected != company_id:
        return False
    return (
        user.company_id == company_id
        or CompanyMembership.objects.filter(user=user, company_id=company_id).exists()
    )


def require_company_authority(user, company, permission) -> None:
    if not has_company_permission(user, company, permission):
        raise PermissionDenied("Company-scoped approval authority is required.")


def has_company_permission(user, company, permission) -> bool:
    company_id = getattr(company, "pk", company)
    if not user_in_company(user, company_id) or not user.has_perm(permission):
        return False
    if user.company_id == company_id:
        return True
    return CompanyMembership.objects.filter(
        user=user, company_id=company_id, role__in=["owner", "admin"]
    ).exists()


def can_decide(approval, user) -> bool:
    if approval.status != "PENDING" or not user_in_company(user, approval.company_id):
        return False
    if user.pk == approval.requester_id or user.pk in approval.beneficiary_ids:
        return False
    if approval.decisions.filter(actor=user).exists():
        return False
    stages = approval.policy_snapshot["stages"]
    if approval.current_stage >= len(stages):
        return False
    stage = stages[approval.current_stage]
    designated = stage.get("approver_ids", [])
    return (
        user.pk in designated
        if designated
        else has_company_permission(user, approval.company_id, stage["permission"])
    )


def scope_to_company(queryset, user):
    company_id = getattr(user, "active_company_id", None) or getattr(
        user, "company_id", None
    )
    return (
        queryset.filter(company_id=company_id)
        if user_in_company(user, company_id)
        else queryset.none()
    )
