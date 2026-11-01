"""Registered accounting approvals and approved deterministic journal provenance."""
from __future__ import annotations
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db.models import Sum
from approvals.registry import ApprovalAction, register_action
from approvals.proposals import proposal_operation
from approvals.services import current_execution
from accounting import models, utils


def journal_beneficiaries(source):
    from approvals.beneficiaries import employee_beneficiaries
    return employee_beneficiaries(source, source.company)


def journal_snapshot(source):
    snapshot = {'id':source.pk,'company_id':source.company_id,'date':source.date,'period_id':source.period_id,
            'description':source.description,'created_by_id':source.created_by_id,
            'content_type_id':source.content_type_id,'object_id':source.object_id,
            'beneficiary_ids': journal_beneficiaries(source),
            'entries':list(source.entries.order_by('pk').values('id','account_id','account__name','account__account_number','entry_type','amount','memo'))}
    # Preserve existing request hashes until a revocation actually occurs.
    from approvals.models import ApprovalRequest
    from django.contrib.contenttypes.models import ContentType
    revision = ApprovalRequest.objects.filter(
        company=source.company, content_type=ContentType.objects.get_for_model(source),
        object_id=source.pk, action='journal.revoke_approval', status='APPROVED',
    ).order_by('-pk').values_list('pk', flat=True).first()
    execution = current_execution()
    if (execution and execution.action == 'journal.revoke_approval'
            and execution.object_id == source.pk and execution.company_id == source.company_id):
        revision = execution.pk
    if revision:
        snapshot['approval_revision_id'] = revision
    return snapshot


def validate_journal(source, payload):
    if source.status != models.Journal.JournalStatus.PENDING_APPROVAL:
        raise ValidationError('Submit a draft journal before requesting approval.')
    source.validate_entries()
    utils.validate_period_status(source.period)


def apply_journal(source, actor, payload):
    source.approve(actor)


def reject_journal(source, actor, payload):
    source.status = models.Journal.JournalStatus.CANCELLED
    source.save(update_fields=['status','updated_at'])

register_action(ApprovalAction(
    key='journal.approve', model_label='accounting.Journal', permission='accounting.change_journal',
    apply=apply_journal, reject=reject_journal, validate=validate_journal, snapshot=journal_snapshot,
    requester=lambda source:source.created_by, beneficiaries=journal_beneficiaries,
    amount=lambda source,payload: source.entries.filter(entry_type='DEBIT').aggregate(total=Sum('amount'))['total'],
))


def revocation_snapshot(source):
    return {**journal_snapshot(source), 'approval_grant_id': source.approval_request_id,
            'approved_by_id': source.approved_by_id, 'approved_at': source.approved_at}


def validate_revocation(source, payload):
    if source.status != models.Journal.JournalStatus.APPROVED:
        raise ValidationError('Only approved, unposted journals can have approval revoked.')
    reason = payload.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError('An approval revocation reason is required.')


def apply_revocation(source, actor, payload):
    from approvals.guards import require_approved_context
    from approvals.services import _event
    require_approved_context(source, 'journal.revoke_approval')
    original_grant = source.approval_request_id
    source.status = models.Journal.JournalStatus.DRAFT
    source.approval_request = None
    source.approved_by = None
    source.approved_at = None
    source.save(update_fields=['status', 'approval_request', 'approved_by', 'approved_at', 'updated_at'])
    _event(current_execution(), actor, 'APPROVAL_REVOKED',
           original_approval_id=original_grant, reason=payload['reason'])
    models.AccountingAuditTrail.log_action(
        user=actor, action=models.AccountingAuditTrail.ActionType.UPDATE, instance=source,
        reason=f"Approval revoked; returned to Draft. {payload['reason']}",
    )


register_action(ApprovalAction(
    key='journal.revoke_approval', model_label='accounting.Journal',
    permission='accounting.change_journal', apply=apply_revocation,
    validate=validate_revocation, snapshot=revocation_snapshot,
    requester=lambda source: source.created_by, beneficiaries=journal_beneficiaries,
    amount=lambda source, payload: source.entries.filter(entry_type='DEBIT').aggregate(total=Sum('amount'))['total'],
))

# Parameter proposals bind amounts, source references and reasons before these public effects.
_OPERATIONS = {
 'create_journal_with_entries': ('accounting.journal.create_posted','accounting.change_journal'),
 'close_accounting_period': ('accounting.period.close','accounting.change_accountingperiod'),
 'close_fiscal_year': ('accounting.year.close','accounting.change_fiscalyear'),
 'approve_reconciliation': ('accounting.reconciliation.approve','accounting.change_accountreconciliation'),
 'post_fx_revaluation': ('accounting.fx_revaluation.post','accounting.change_currencyrevaluation'),
 'reverse_fx_revaluation': ('accounting.fx_revaluation.reverse','accounting.change_currencyrevaluation'),
 'file_tax_return': ('accounting.tax_return.file','accounting.change_taxreturn'),
 'post_accrual_template': ('accounting.accrual.post','accounting.change_accrualtemplate'),
 'post_journal': ('accounting.journal.post','accounting.change_journal'),
 'reverse_journal': ('accounting.journal.reverse','accounting.change_journal'),
 'reverse_journal_partial': ('accounting.journal.reverse_partial','accounting.change_journal'),
 'reverse_journal_with_correction': ('accounting.journal.reverse_correction','accounting.change_journal'),
 'batch_reverse_journals': ('accounting.journal.reverse_batch','accounting.change_journal'),
}
for function_name,(key,permission) in _OPERATIONS.items():
    operation = getattr(utils,function_name,None)
    if operation is None:
        continue
    wrapper = proposal_operation(key,permission)(operation)
    if function_name == 'create_journal_with_entries':
        original = operation
        def create_journal_with_entries(*args, _original=original, _wrapper=wrapper, **kwargs):
            if not kwargs.get('auto_post',False):
                return _original(*args,**kwargs)
            return _wrapper(*args,**kwargs)
        setattr(utils,function_name,create_journal_with_entries)
    else:
        setattr(utils,function_name,wrapper)

# Model entry points delegate to the same canonical utility action. Inside
# validated execution, utilities call the original model effects directly.
from functools import wraps


def canonical_model_entry(original, utility):
    @wraps(original)
    def entry(source, *args, **kwargs):
        if current_execution() is not None:
            from approvals.guards import require_approved_context

            require_approved_context(source)
            kwargs.pop("approval_actor", None)
            kwargs.pop("approval_key", None)
            return original(source, *args, **kwargs)
        return utility(source, *args, **kwargs)

    return entry


models.Journal.reverse = canonical_model_entry(
    models.Journal.reverse, utils.reverse_journal
)
models.AccountingPeriod.close = canonical_model_entry(
    models.AccountingPeriod.close, utils.close_accounting_period
)
if hasattr(utils, "close_fiscal_year"):
    models.FiscalYear.close = canonical_model_entry(
        models.FiscalYear.close, utils.close_fiscal_year
    )
else:
    models.FiscalYear.close = proposal_operation(
        "accounting.year.close", "accounting.change_fiscalyear"
    )(models.FiscalYear.close)
from accounting import discipline_approval_actions  # Register reviewed findings and appeal outcomes.
from payroll.models import DisciplinaryCase  # noqa: E402
DisciplinaryCase.close_case = proposal_operation('discipline.close','payroll.change_disciplinarycase')(DisciplinaryCase.close_case)


def sanction_snapshot(source):
    return {'id':source.pk,'case_id':source.case_id,'case_company_id':source.case.company_id,
            'respondent_id':source.case.respondent_id,'sanction_type':source.sanction_type,
            'effective_date':source.effective_date,'duration_days':source.duration_days,'rationale':source.rationale,
            'created_by_id':source.created_by_id,'case_status':source.case.status,'case_finding':source.case.finding,
            'case_summary':source.case.findings_summary,'case_decided_by':source.case.decided_by_id,
            'employment_effect_snapshot':source.employment_effect_snapshot}


def validate_sanction(source,payload):
    if source.status != source.Status.PENDING:
        raise ValidationError('Only pending sanctions can be activated.')
    if source.case.status not in {source.case.Status.DECIDED, source.case.Status.CLOSED} or source.case.finding not in {source.case.Finding.SUBSTANTIATED, source.case.Finding.PARTIALLY_SUBSTANTIATED}:
        raise ValidationError('A substantiated approved finding is required before sanction approval.')
    if source.case.appeals.filter(status__in=['SUBMITTED','UNDER_REVIEW']).exists():
        raise ValidationError('Resolve the pending appeal before activating sanctions.')
    source.full_clean()


def apply_sanction(source,actor,payload):
    source.status=source.Status.ACTIVE
    source.save(update_fields=['status','updated_at'])

register_action(ApprovalAction(key='discipline.sanction',model_label='payroll.DisciplinarySanction',
    permission='payroll.change_disciplinarysanction',apply=apply_sanction,
    snapshot=sanction_snapshot,validate=validate_sanction,company=lambda source:source.case.company,
    requester=lambda source:source.created_by,beneficiaries=lambda source:[source.case.respondent_id]))


def budget_snapshot(source):
    return {'id':source.pk,'company_id':source.company_id,'name':source.name,'fiscal_year_id':source.fiscal_year_id,
            'fiscal_year':source.fiscal_year.year,
            'lines':list(source.lines.select_for_update().order_by('pk').values('id','account_id','account__name','account__account_number','period_id','amount'))}


def validate_budget(source, payload):
    if source.status != 'DRAFT':
        raise ValidationError('Only draft budgets can be approved.')
    if source.fiscal_year.company_id != source.company_id:
        raise ValidationError('Budget and fiscal year must belong to the same company.')
    for line in source.lines.select_related('account','period'):
        if line.account.company_id != source.company_id or (line.period and
                (line.period.company_id != source.company_id or line.period.fiscal_year_id != source.fiscal_year_id)):
            raise ValidationError('Budget lines must use accounts and periods in the reviewed company and fiscal year.')


def approve_budget(source,actor,payload):
    validate_budget(source,payload)
    source.status='APPROVED'
    source.save(update_fields=['status','updated_at'])

register_action(ApprovalAction(key='accounting.budget.approve',model_label='accounting.Budget',
    permission='accounting.change_budget',apply=approve_budget,validate=validate_budget,snapshot=budget_snapshot,
    amount=lambda source,payload:sum((abs(line.amount) for line in source.lines.all()),Decimal('0'))))
