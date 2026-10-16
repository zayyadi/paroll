"""Domain-side enforcement for approval state and pending-source integrity."""
from __future__ import annotations
from typing import Any
from django.core.exceptions import ValidationError
from django.db import models

# These fields represent human authorization or financial/employment execution.
CONTROLLED_FIELDS = {
 'accounting.journal': {'status': {'APPROVED','POSTED','REVERSED','CANCELLED'}},
 'accounting.accountingperiod': {'is_closed': {True}},
 'accounting.fiscalyear': {'is_closed': {True}},
 'accounting.accountreconciliation': {'status': {'APPROVED'}},
 'accounting.budget': {'status': {'APPROVED','CLOSED'}},
 'accounting.taxreturn': {'status': {'FILED','SUBMITTED'}},
 'accounting.currencyrevaluation': {'status': {'POSTED','REVERSED'}},
 'accounting.disciplinarycase': {'status': {'DECIDED','CLOSED'}},
 'accounting.disciplinarysanction': {'status': {'ACTIVE','COMPLETED','REVOKED'}},
 'accounting.disciplinaryappeal': {'status': {'UPHELD','MODIFIED','OVERTURNED','REINVESTIGATION_ORDERED','REJECTED'}},
 'inventory.inventorydocument': {'status': {'APPROVED','POSTED','CANCELLED'}},
 'inventory.stockcount': {'status': {'APPROVED','POSTED'}},
 'inventory.stockcountline': {'investigation_status': {'APPROVED','REJECTED'}},
 'inventory.vendorbill': {'status': {'APPROVED','POSTED'}},
 'inventory.warrantyclaim': {'status': {'APPROVED','REJECTED','RESOLVED'}},
 'inventory.salesorder': {'status': {'CONFIRMED','SHIPPED','PARTIALLY_SHIPPED','INVOICED'}},
 'inventory.purchaseorder': {'status': {'APPROVED','RECEIVED','PARTIALLY_RECEIVED'}},
 'payroll.payrollrun': {'status': {'approved','locked','paid'},'closed': {True}},
 'payroll.bankpaymentfile': {'status': {'SUBMITTED','CONFIRMED'}},
}


def _controlled_parent_fields(model: Any) -> list:
    return [field for field in model._meta.concrete_fields if field.is_relation and
            field.remote_field.related_name in {'lines', 'entries'} and
            field.remote_field.model._meta.label_lower in CONTROLLED_FIELDS]


def _guard_parent_history(instance: Any) -> None:
    for field in _controlled_parent_fields(type(instance)):
        parent_id = getattr(instance, field.attname)
        if parent_id is None:
            continue
        parent_model = field.remote_field.model
        rules = CONTROLLED_FIELDS[parent_model._meta.label_lower]
        parent = parent_model._base_manager.filter(pk=parent_id).first()
        if parent is not None and any(getattr(parent, name) in states for name, states in rules.items()):
            raise ValidationError('Approved record details cannot be changed or removed. Use an approved correction.')


def approved_context(company: Any = None) -> bool:
    from .services import current_execution
    request = current_execution()
    return bool(request and (company is None or getattr(company, 'pk', company) == request.company_id))


def require_approved_context(source: Any, action: str | None = None) -> None:
    from .services import current_execution
    from .proposals import object_company
    request = current_execution()
    company = object_company(source)
    if not request or not company or company.pk != request.company_id or (action and request.action != action):
        raise ValidationError('Submit this action for independent approval before applying it.')


def guard_source_save(instance: Any, update_fields: Any = None) -> None:
    from .services import current_execution
    from .proposals import object_company
    from .models import ApprovalRequest
    from django.contrib.contenttypes.models import ContentType
    label = instance._meta.label_lower
    rules = CONTROLLED_FIELDS.get(label, {})
    old = type(instance)._base_manager.filter(pk=instance.pk).first() if instance.pk else None
    execution = current_execution()
    company = object_company(instance)
    allowed = bool(execution and company and company.pk == execution.company_id)
    if not allowed:
        _guard_parent_history(instance)
        if old is not None:
            _guard_parent_history(old)
    elif old is not None:
        old_company = object_company(old)
        if old_company is not None and old_company.pk != execution.company_id:
            raise ValidationError('Approved effects cannot move a source from another company.')
    for field, states in rules.items():
        if update_fields is not None and field not in update_fields:
            continue
        value = getattr(instance, field)
        if (value in states or (old is not None and getattr(old,field) in states)) and (old is None or getattr(old, field) != value) and not allowed:
            raise ValidationError('Approval states cannot be set directly. Use the approval workflow.')
    if old and not allowed:
        changed = any(
            f.name not in {'created_at','updated_at'} and (update_fields is None or f.name in update_fields or f.attname in update_fields) and getattr(old,f.attname) != getattr(instance,f.attname)
            for f in instance._meta.concrete_fields
        )
        if changed and (any(getattr(old,field) in states for field,states in rules.items()) or ApprovalRequest.objects.filter(
            content_type=ContentType.objects.get_for_model(instance), object_id=instance.pk, status='PENDING'
        ).exists()):
            raise ValidationError('Withdraw the pending approval before changing its source.')


class ApprovalControlledQuerySet(models.QuerySet):
    def update(self, **kwargs):
        rules = CONTROLLED_FIELDS.get(self.model._meta.label_lower, {})
        if any(field in kwargs for field in rules):
            raise ValidationError('Workflow state changes must use the approval service.')
        if rules or _controlled_parent_fields(self.model):
            for instance in self:
                for name, value in kwargs.items():
                    setattr(instance, name, value)
                guard_source_save(instance)
        return super().update(**kwargs)

    def delete(self):
        from .models import ApprovalRequest
        from django.contrib.contenttypes.models import ContentType
        if self.model._meta.label_lower in CONTROLLED_FIELDS:
            if ApprovalRequest.objects.filter(content_type=ContentType.objects.get_for_model(self.model),object_id__in=self.values('pk')).exists():
                raise ValidationError('Reviewed sources must be retained for their audit history.')
            for instance in self:
                if any(getattr(instance,field) in states for field,states in CONTROLLED_FIELDS[self.model._meta.label_lower].items()):
                    raise ValidationError('Approved sources cannot be deleted.')
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValidationError("Workflow records cannot be replaced through bulk conflict updates.")
        objs = list(objs)
        for instance in objs:
            guard_source_save(instance)
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if set(fields) & set(CONTROLLED_FIELDS.get(self.model._meta.label_lower, {})):
            raise ValidationError('Workflow state changes must use the approval service.')
        for instance in objs:
            guard_source_save(instance)
        return super().bulk_update(objs, fields, **kwargs)


def install_history_guards() -> None:
    """Django parent cascades must not discard reviewed source history."""
    from django.apps import apps
    from django.contrib.contenttypes.models import ContentType
    from django.db.models.signals import pre_delete
    from .models import ApprovalRequest
    from .registry import registered_actions

    def protect_source(sender, instance, **kwargs):
        persisted = sender._base_manager.filter(pk=instance.pk).first() or instance
        _guard_parent_history(persisted)
        ct = ContentType.objects.get_for_model(sender)
        if ApprovalRequest.objects.filter(content_type=ct, object_id=instance.pk).exists():
            raise ValidationError('Reviewed source history cannot be deleted, including through a parent.')
        rules = CONTROLLED_FIELDS.get(instance._meta.label_lower, {})
        if any(getattr(persisted,field) in states for field,states in rules.items()):
            raise ValidationError('Approved financial or employment records cannot be deleted.')

    labels = set(CONTROLLED_FIELDS) | {action.model_label for action in registered_actions().values()}
    labels.update(model._meta.label for model in apps.get_models() if _controlled_parent_fields(model))
    for label in labels:
        pre_delete.connect(protect_source, sender=apps.get_model(label), weak=False, dispatch_uid='approval-history-' + label.lower())
