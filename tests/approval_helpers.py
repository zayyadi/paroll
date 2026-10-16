"""Build test fixtures through genuine independent workflow decisions."""
import uuid
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.db import models
from approvals.models import ApprovalRequest
from approvals.proposals import object_company
from approvals.services import decide_approval, submit_approval


def approval_user(company, permissions=()):
    user = get_user_model().objects.create_user(
        email=f"approval-fixture-{uuid.uuid4().hex}@example.test", password="fixture",
        company=company, active_company=company,
    )
    permissions = list(permissions)
    if "inventory.change_inventorydocument" in permissions:
        permissions.append("inventory.add_inventorydocument")
    if any(permission.startswith("accounting.") for permission in permissions):
        for role in ("Accountant", "Auditor"):
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)
    for permission in permissions:
        app, codename = permission.split(".", 1)
        user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))
    return user


def approve_request(request, checker=None):
    """Complete real stages with distinct actors and resolve a deferred model result."""
    if not isinstance(request, ApprovalRequest):
        return request
    while request.status == "PENDING":
        stage = request.policy_snapshot["stages"][request.current_stage]
        actor = checker or approval_user(request.company, [stage["permission"]])
        request = decide_approval(approval=request, actor=actor)
        checker = None
    if request.status != "APPROVED":
        raise AssertionError(f"Fixture approval ended in {request.status}")
    source = request.source
    source.refresh_from_db()
    if source._meta.label_lower == "company.actionproposal":
        if source.result_type and source.result_id:
            return apps.get_model(source.result_type).objects.get(pk=source.result_id)
        return source
    return source


def reject_request(request, checker=None, comment="Rejected in test fixture"):
    """Reject an already-submitted approval (distinct permissioned checker).

    Mirrors :func:`approve_request` for sources that were submitted through
    their own service (so the pending request already exists and must be
    reused rather than re-submitted).
    """
    if not isinstance(request, ApprovalRequest):
        return request
    stage = request.policy_snapshot["stages"][request.current_stage]
    actor = checker or approval_user(request.company, [stage["permission"]])
    return decide_approval(
        approval=request, actor=actor, decision="REJECT", comment=comment
    )


def _company_in(value):
    if isinstance(value, models.Model):
        return object_company(value)
    values = value.values() if isinstance(value, dict) else value if isinstance(value, (tuple, list)) else ()
    for item in values:
        company = _company_in(item)
        if company is not None:
            return company
    return None


def approved_operation(operation, *args, maker=None, checker=None, permission="accounting.change_journal", **kwargs):
    """Request an operation and perform independent decisions; never bypass guards."""
    company = kwargs.get("company") or _company_in([args, kwargs])
    if company is None:
        bound_source = getattr(operation, "__self__", None)
        company = _company_in(bound_source)
    explicit_maker = maker is not None
    if maker is None:
        maker = kwargs.get("user")
    if maker is None:
        maker = next((arg for arg in args if isinstance(arg, get_user_model())), None)
    if maker is None or (not explicit_maker and (not maker.has_perm(permission) or maker.company_id != company.pk or (maker.active_company_id or maker.company_id) != company.pk)):
        maker = approval_user(company, [permission])
    if operation.__name__ == "create_journal_with_entries" and not kwargs.get("auto_post", False):
        return operation(*args, **kwargs)
    kwargs.setdefault("approval_key", uuid.uuid4().hex)
    kwargs["approval_actor"] = maker
    result = approve_request(operation(*args, **kwargs), checker=checker)
    def refresh(value):
        if isinstance(value, models.Model):
            value.refresh_from_db()
        elif isinstance(value, dict):
            for item in value.values():
                refresh(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                refresh(item)
    refresh([args, kwargs])
    bound_source = getattr(operation, "__self__", None)
    if isinstance(bound_source, models.Model):
        bound_source.refresh_from_db()
    return result


def approve_journal(journal, checker=None):
    """Approve a real journal request with a checker distinct from its creator."""
    if not journal.created_by_id:
        journal.created_by = approval_user(journal.company, ["accounting.change_journal"])
        journal.save(update_fields=["created_by"])
    if journal.status == "DRAFT":
        journal.submit_for_approval()
    request = submit_approval(source=journal, action="journal.approve", requester=journal.created_by)
    approved = approve_request(request, checker=checker)
    journal.refresh_from_db()
    return journal


def post_journal(journal, maker=None, checker=None):
    from accounting.utils import post_journal as operation
    maker = maker or journal.created_by or approval_user(journal.company, ["accounting.change_journal"])
    return approved_operation(operation, journal, maker, maker=maker, checker=checker)


def approved_operation_for(permission):
    from functools import partial
    return partial(approved_operation, permission=permission)


def reject_source(source, action, maker=None, checker=None, comment="Rejected in test fixture"):
    """Drive a real workflow rejection (distinct checker, required comment)."""
    from approvals.registry import get_action
    from approvals.services import decide_approval

    adapter = get_action(action)
    company = adapter.company(source) if adapter.company else object_company(source)
    maker = maker or (adapter.requester(source) if adapter.requester else None) or approval_user(company, [adapter.permission])
    if checker is None:
        checker = approval_user(company, [adapter.permission])
    request = submit_approval(source=source, action=action, requester=maker)
    request = decide_approval(approval=request, actor=checker, decision="REJECT", comment=comment)
    source.refresh_from_db()
    return request


def approve_source(source, action, maker=None, checker=None):
    from approvals.registry import get_action
    adapter = get_action(action)
    company = adapter.company(source) if adapter.company else object_company(source)
    maker = maker or (adapter.requester(source) if adapter.requester else None) or approval_user(company, [adapter.permission])
    request = submit_approval(source=source, action=action, requester=maker)
    result = approve_request(request, checker=checker)
    source.refresh_from_db()
    return result
