"""Resolve employee conflicts through linked financial source records."""
from django.db import models, transaction
from django.core.exceptions import ValidationError


def employee_beneficiaries(value, company):
    from .proposals import object_company, decode_value
    seen = set()
    result = set()

    def visit(item):
        if isinstance(item, dict):
            if '__model__' in item:
                visit(decode_value(item, company))
            else:
                for key, child in item.items():
                    if key not in {'company', 'user', 'actor', 'requester', 'decided_by'}:
                        visit(child)
            return
        if isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
            return
        if not isinstance(item, models.Model) or not item.pk:
            return
        identity = (item._meta.label_lower, item.pk)
        if identity in seen:
            return
        seen.add(identity)
        owner = object_company(item)
        if owner is not None and owner.pk != company.pk:
            raise ValidationError('Financial sources and employee beneficiaries must belong to the same company.')
        if transaction.get_connection().in_atomic_block:
            item = type(item)._base_manager.select_for_update().get(pk=item.pk)
        label = item._meta.label_lower
        if label == 'payroll.employeeprofile':
            if item.user_id:
                result.add(item.user_id)
            return
        if label == 'payroll.payrollrun':
            for membership in item.payroll_run_entries.select_related('payroll_entry__pays'):
                visit(membership.payroll_entry)
        if label == 'approvals.approvalrequest':
            result.update(item.beneficiary_ids)
            visit(item.source)
        if label == 'company.actionproposal':
            visit(item.parameters)
        if label == 'accounting.disciplinarycase':
            result.update(pk for pk in (item.respondent_id, item.reporter_id) if pk)
        for name in ('employee', 'employee_id', 'pays', 'payee', 'payroll_entry', 'allowance', 'iou', 'source_leave_request'):
            related = getattr(item, name, None)
            if isinstance(related, models.Model):
                visit(related)
        if label == 'accounting.journal':
            if item.content_type_id and item.object_id:
                source = item.content_object
                if source is None:
                    raise ValidationError('The linked financial source is unavailable.')
                visit(source)
            if item.approval_request_id:
                visit(item.approval_request)

    visit(value)
    return sorted(result)
