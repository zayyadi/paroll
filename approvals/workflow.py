"""Read-only approval timelines shared by business documents and request pages."""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Q

from .models import ApprovalRequest
from .permissions import has_company_permission, user_in_company
from .presentation import _can_view_business_content, action_label
from .registry import registered_actions


def person_name(user):
    name = ' '.join(part for part in (user.first_name, user.last_name) if part).strip()
    return name or user.email


def workflow_context(approval, user, document=None):
    """Use the submitted snapshot; policy edits must never rewrite history."""
    source = approval.source
    from .registry import get_action
    from .services import _company
    try:
        if source is None or _company(source, get_action(approval.action)).pk != approval.company_id:
            return None
    except (ValidationError, ObjectDoesNotExist):
        return None
    can_open_request = _can_view_business_content(approval, user, source)
    if not can_open_request:
        # Document readers may see routing metadata without gaining access to
        # private approval payloads, decision notes, or decision controls.
        if document is None:
            return None
        from .proposals import object_company
        document_company = object_company(document)
        permission = f'{document._meta.app_label}.view_{document._meta.model_name}'
        visibility = get_action(approval.action).source_visibility
        if (document_company is None or document_company.pk != approval.company_id
                or not has_company_permission(user, document_company, permission)
                or (visibility is not None and not visibility(source, user))):
            return None
    decisions = list(approval.decisions.select_related('actor').order_by('created_at'))
    excluded = {approval.requester_id, *approval.beneficiary_ids, *(d.actor_id for d in decisions)}
    relevant = Q(is_superuser=True)
    for stage in approval.policy_snapshot.get('stages', []):
        relevant |= Q(pk__in=stage.get('approver_ids', []))
        if not stage.get('approver_ids'):
            app, codename = stage['permission'].split('.', 1)
            relevant |= Q(user_permissions__content_type__app_label=app, user_permissions__codename=codename)
            relevant |= Q(groups__permissions__content_type__app_label=app, groups__permissions__codename=codename)
    # Narrow by assignment/permission before running the canonical authority
    # checks, rather than checking every employee in a large company.
    candidates = list(get_user_model().objects.filter(is_active=True).filter(
        Q(company_id=approval.company_id) | Q(company_memberships__company_id=approval.company_id)
    ).filter(relevant).distinct()) if approval.status == 'PENDING' else []
    by_id = {candidate.pk: candidate for candidate in candidates}
    stages = []
    for index, stage in enumerate(approval.policy_snapshot.get('stages', [])):
        decision = next((d for d in decisions if d.stage == index), None)
        current = approval.status == 'PENDING' and index == approval.current_stage
        assigned = stage.get('approver_ids', [])
        eligible = []
        if not decision and approval.status == 'PENDING':
            for candidate in candidates:
                if candidate.pk in excluded:
                    continue
                # Match can_decide(), including selected-company membership and
                # the designated-approver exception to permission-based routing.
                allowed = (candidate.pk in assigned if assigned else
                           has_company_permission(candidate, approval.company, stage['permission']))
                if allowed and user_in_company(candidate, approval.company):
                    eligible.append(person_name(candidate))
        if decision:
            state = 'Approved' if decision.decision == 'APPROVE' else 'Rejected'
        elif current:
            state = 'Awaiting approval'
        elif approval.status == 'PENDING':
            state = 'Upcoming'
        else:
            state = 'Not reached'
        stages.append({
            'number': index + 1, 'name': stage.get('name') or 'Independent approval',
            'state': state, 'current': current, 'decision': decision,
            'actor_name': person_name(decision.actor) if decision else '',
            'eligible': sorted(eligible, key=str.casefold),
            'assigned': [person_name(by_id[pk]) if pk in by_id else 'Unavailable approver' for pk in assigned],
        })
    current_stage = next((stage for stage in stages if stage['current']), None)
    blocked_reason = ''
    if current_stage and not current_stage['eligible']:
        assigned = approval.policy_snapshot['stages'][approval.current_stage].get('approver_ids', [])
        if assigned and set(assigned) == {approval.requester_id}:
            blocked_reason = (
                'The requester is the only assigned approver and cannot approve their own request. '
                'A different company user must submit, or an administrator must revise the policy '
                'before a new request is submitted.'
            )
    document_url = ''
    if approval.action == 'accounting.journal.post' and source._meta.label_lower == 'company.actionproposal':
        from accounting.models import Journal
        from django.urls import reverse
        reference = source.parameters.get('journal', {})
        if isinstance(reference, dict) and reference.get('__model__') == 'accounting.journal':
            journal = Journal.objects.filter(pk=reference.get('pk'), company_id=approval.company_id).first()
            if journal and has_company_permission(user, approval.company, 'accounting.view_journal'):
                document_url = reverse('accounting:journal_detail', args=[journal.pk])
    return {
        'approval': approval, 'label': action_label(approval.action),
        'requester_name': person_name(approval.requester), 'stages': stages,
        'next_approvers': current_stage['eligible'] if current_stage else [],
        'waiting': current_stage is not None, 'can_open_request': can_open_request,
        'blocked_reason': blocked_reason, 'document_url': document_url,
    }


def document_workflows(source, user):
    if not source or not source.pk or not getattr(user, 'is_authenticated', False):
        return []
    from .proposals import object_company
    company = object_company(source)
    if company is None or not user_in_company(user, company):
        return []
    ct = ContentType.objects.get_for_model(source)
    query = Q(content_type=ct, object_id=source.pk)
    # Some operations create their document only after a proposal is approved.
    from company.models import ActionProposal
    proposal_query = Q(result_type=source._meta.label_lower, result_id=source.pk)
    if source._meta.label_lower == 'accounting.journal':
        # Pending/cancelled posting proposals have no result yet, but still
        # belong on the journal's workflow timeline.
        proposal_query |= Q(parameters__journal={'__model__': 'accounting.journal', 'pk': source.pk})
    proposal_ids = ActionProposal.objects.filter(proposal_query, company=company).values('pk')
    query |= Q(content_type=ContentType.objects.get_for_model(ActionProposal), object_id__in=proposal_ids)
    linked = getattr(source, 'approval_request_id', None)
    if linked:
        query |= Q(pk=linked)
    requests = ApprovalRequest.objects.filter(query, company=company).select_related(
        'requester', 'company', 'content_type',
    ).prefetch_related('decisions__actor')
    requests = list(requests)
    if not requests:
        return document_previews(source, user)
    workflows = [workflow for approval in requests if (workflow := workflow_context(approval, user, document=source))]
    workflows.sort(key=lambda workflow: (workflow['approval'].status != 'PENDING', -workflow['approval'].pk))
    return workflows


def is_approval_document(source):
    """Keep the global layout quiet on dashboards, lists, and unrelated records."""
    from django.db.models import Model
    if not isinstance(source, Model) or not source.pk:
        return False
    labels = {action.model_label.lower() for action in registered_actions().values()}
    return (source._meta.label_lower in labels or hasattr(source, 'approval_request_id')
            or source._meta.app_label in {'accounting', 'inventory', 'payroll'})


def document_previews(source, user):
    """Draft routing is a preview, never an approval request or audit write."""
    from .services import _company, _policy
    if str(getattr(source, 'status', '')).upper() in {
        'APPROVED', 'POSTED', 'REVERSED', 'CANCELLED', 'REJECTED', 'PAID',
        'COMPLETED', 'CLOSED', 'SIGNED', 'CONFIRMED',
    }:
        return []
    previews = []
    for action in registered_actions().values():
        if action.model_label.lower() != source._meta.label_lower:
            continue
        if action.key == 'journal.revoke_approval':
            continue
        company = _company(source, action)
        if not user_in_company(user, company):
            continue
        maker = action.requester(source) if action.requester else None
        view_permission = f'{source._meta.app_label}.view_{source._meta.model_name}'
        if not (maker == user or has_company_permission(user, company, view_permission)):
            continue
        if action.source_visibility and not action.source_visibility(source, user):
            continue
        try:
            policy = _policy(company, action, source, {})
        except (ValidationError, ObjectDoesNotExist):
            continue
        # Draft previews show the configured assignees; eligibility is evaluated
        # against the immutable request once actually submitted.
        ids = {pk for stage in policy['stages'] for pk in stage.get('approver_ids', [])}
        people = {p.pk: person_name(p) for p in get_user_model().objects.filter(pk__in=ids, is_active=True).filter(
            Q(company_id=company.pk) | Q(company_memberships__company_id=company.pk)
        )}
        previews.append({'preview': True, 'label': action_label(action.key), 'stages': [
            {'number': i+1, 'name': stage.get('name') or 'Independent approval',
             'state': 'Not started', 'assigned': [people.get(pk, 'Unavailable approver') for pk in stage.get('approver_ids', [])]}
            for i, stage in enumerate(policy['stages'])
        ]})
    return previews
