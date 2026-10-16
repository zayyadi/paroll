from django import template
from django.contrib.contenttypes.models import ContentType
from approvals.models import ApprovalRequest
from approvals.permissions import can_decide, require_company_authority
from django.core.exceptions import PermissionDenied
from approvals.registry import get_action

register = template.Library()

@register.simple_tag
def may_decide_hr(source, action_key, actor):
    action = get_action(action_key)
    pending = ApprovalRequest.objects.filter(content_type=ContentType.objects.get_for_model(source),
        object_id=source.pk, action=action_key, status="PENDING").first()
    if pending:
        return can_decide(pending, actor)
    maker = action.requester(source) if action.requester else None
    beneficiaries = action.beneficiaries(source) if action.beneficiaries else []
    company = getattr(source, "company", None)
    if not company:
        employee = getattr(source, "employee", None) or getattr(source, "employee_id", None)
        company = getattr(employee, "company", None)
    if not maker or not actor or maker.pk == actor.pk or actor.pk in beneficiaries:
        return False
    try:
        require_company_authority(actor, company, action.permission)
    except PermissionDenied:
        return False
    return True
