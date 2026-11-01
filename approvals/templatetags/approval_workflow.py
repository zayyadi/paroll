from django import template
from approvals.models import ApprovalRequest
from approvals.workflow import document_workflows, is_approval_document, workflow_context

register = template.Library()


@register.inclusion_tag('approvals/_workflow.html', takes_context=True)
def approval_workflow(context, source=None, collapsed=False):
    request = context.get('request')
    if request is None or not request.user.is_authenticated:
        return {}
    if source is None:
        # Generic detail/update views expose object; function views use domain
        # names. Inspect only scalar model instances, never querysets or lists.
        source = context.get('approval_document') or context.get('object') or getattr(context.get('view'), 'object', None)
        if source is None:
            for name in ('approval', 'journal', 'payroll_run', 'pay_period', 'run', 'document', 'order',
                         'invoice', 'bill', 'stock_count', 'iou', 'leave_request', 'leave', 'transfer',
                         'promotion', 'offboarding', 'checklist', 'contract', 'disciplinary_case',
                         'appeal', 'timesheet', 'offer', 'candidate', 'settlement', 'bank_payment_file', 'reconciliation', 'budget', 'tax_return', 'period', 'fiscal_year'):
                candidate = context.get(name)
                if isinstance(candidate, ApprovalRequest) or is_approval_document(candidate):
                    source = candidate
                    break
    if source is None:
        instance = getattr(context.get('form'), 'instance', None)
        if is_approval_document(instance):
            source = instance
    if isinstance(source, ApprovalRequest):
        workflow = workflow_context(source, request.user)
        return {'workflows': [workflow] if workflow else [], 'collapsed': collapsed}
    if not is_approval_document(source):
        return {}
    workflows = document_workflows(source, request.user)
    # Do not disclose whether hidden requests exist or their policy metadata.
    return {'workflows': workflows, 'collapsed': collapsed}
