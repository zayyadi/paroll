"""Bind parameter-based business operations to immutable approval proposals."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
import inspect
from typing import Any, Callable

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType

from .permissions import require_company_authority
from .registry import ApprovalAction, register_action
from .services import current_execution, submit_approval

_request_key: ContextVar[str | None] = ContextVar('approval_request_key', default=None)
_request_actor: ContextVar[Any] = ContextVar('approval_request_actor', default=None)
_OPERATIONS: dict[str, Callable] = {}
_SUBMISSION_PERMISSIONS: dict[str, str] = {}


def encode_value(value: Any) -> Any:
    if isinstance(value, models.Model):
        return {'__model__': value._meta.label_lower, 'pk': value.pk}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValidationError('Amounts must be finite.')
        return {'__decimal__': str(value)}
    if isinstance(value, datetime):
        return {'__datetime__': value.isoformat()}
    if isinstance(value, date):
        return {'__date__': value.isoformat()}
    if hasattr(value, 'first_day') and callable(value.first_day):
        return {'__month__':str(value)}
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            return {'__mapping__': [[encode_value(key), encode_value(item)] for key, item in value.items()]}
        return {key: encode_value(item) for key, item in value.items()}
    if isinstance(value, models.QuerySet):
        return [encode_value(v) for v in value]
    if isinstance(value, (list, tuple)):
        return [encode_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValidationError('Unsupported approval parameter.')


def object_company(obj: Any) -> Any:
    if obj._meta.label_lower == 'company.company':
        return obj
    company = getattr(obj, 'company', None)
    if company:
        return company
    for name in ('employee', 'employee_id', 'appraisal', 'account', 'payroll', 'payroll_run', 'stock_count', 'document', 'receipt', 'invoice', 'purchase_order', 'sales_order', 'shipment', 'customer_return', 'supplier_return', 'movement', 'case', 'journal', 'tax_return', 'revaluation', 'budget', 'period', 'fiscal_year'):
        related = getattr(obj, name, None)
        if isinstance(related, models.Model):
            company = object_company(related)
            if company:
                return company
    return None


def decode_value(value: Any, company: Any) -> Any:
    if isinstance(value, list):
        return [decode_value(v, company) for v in value]
    if not isinstance(value, dict):
        return value
    if '__mapping__' in value:
        return {decode_value(key, company): decode_value(item, company) for key, item in value['__mapping__']}
    if '__model__' in value:
        label = value['__model__']
        if not isinstance(label, str) or label.split('.')[0] not in {'company', 'inventory', 'accounting', 'users', 'payroll'}:
            raise ValidationError('Unsupported source reference.')
        model = apps.get_model(label)
        obj = model._base_manager.get(pk=value['pk'])
        if label != 'users.customuser':
            owner = object_company(obj)
            if owner is None or owner.pk != company.pk:
                raise PermissionDenied('Approval references must belong to the same company.')
        return obj
    if '__decimal__' in value:
        result = Decimal(value['__decimal__'])
        if not result.is_finite():
            raise ValidationError('Amounts must be finite.')
        return result
    if '__datetime__' in value:
        return datetime.fromisoformat(value['__datetime__'])
    if '__date__' in value:
        return date.fromisoformat(value['__date__'])
    if '__month__' in value:
        from monthyear import Month
        return Month.from_string(value['__month__'])
    return {k: decode_value(v, company) for k, v in value.items()}


def _reference_snapshots(value: Any, company: Any) -> list[dict]:
    if isinstance(value, list):
        return [item for v in value for item in _reference_snapshots(v, company)]
    if not isinstance(value, dict):
        return []
    if '__model__' in value:
        if value['__model__'] in {'users.customuser', 'company.company'}:
            return []
        obj = decode_value(value, company)
        data = {
            f.attname: encode_value(getattr(obj, f.attname))
            for f in obj._meta.concrete_fields
            if f.name not in {'created_at', 'updated_at', 'current_balance', 'balance'}
            and not isinstance(f, (models.FileField, models.BinaryField))
        }
        if obj._meta.label_lower == 'payroll.employeeprofile':
            data = {key:getattr(obj,key) for key in ('id','company_id','user_id','employee_pay_id','department_id','job_title','status')}
        if obj._meta.label_lower == 'accounting.journal':
            data['entries'] = list(obj.entries.order_by('pk').values('id','account_id','entry_type','amount','memo'))
        if hasattr(obj, 'lines'):
            data['lines'] = [
                {f.attname: encode_value(getattr(line, f.attname)) for f in line._meta.concrete_fields
                 if f.name not in {'created_at', 'updated_at'} and not isinstance(f, (models.FileField, models.BinaryField))}
                for line in obj.lines.all().order_by('pk')
            ]
        return [{'model': value['__model__'], 'pk': obj.pk, 'data': data}]
    return [item for v in value.values() for item in _reference_snapshots(v, company)]


def _lock_references(value: Any, company: Any) -> None:
    """Hold referenced sources and existing detail rows through final execution."""
    references = set()
    def collect(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                collect(child)
        elif isinstance(item, dict):
            if '__model__' in item:
                references.add((item['__model__'], item['pk']))
            else:
                for child in item.values():
                    collect(child)
    collect(value)
    for label, pk in sorted(references):
        # Resolve ownership before acquiring business record locks.
        obj = decode_value({'__model__':label, 'pk':pk}, company)
        type(obj)._base_manager.select_for_update().get(pk=pk)
        for relation in ('lines', 'entries'):
            manager = getattr(obj, relation, None)
            if manager is not None and hasattr(manager, 'select_for_update'):
                list(manager.select_for_update().order_by('pk'))


def proposal_snapshot(source: Any) -> dict:
    if transaction.get_connection().in_atomic_block:
        type(source.company)._base_manager.select_for_update().get(pk=source.company_id)
        _lock_references(source.parameters, source.company)
    return {'id': source.pk, 'company_id': source.company_id, 'action': source.action,
            'created_by_id': source.created_by_id, 'currency': source.currency, 'parameters': source.parameters,
            'references': _reference_snapshots(source.parameters, source.company)}


def _proposal_amount(source: Any, payload: dict) -> Decimal | None:
    parameters = source.parameters
    for key in ('amount', 'basic_salary', 'total_amount', 'total_cost', 'tax_amount'):
        if key in parameters:
            value = decode_value(parameters[key], source.company)
            if value is not None:
                return abs(Decimal(str(value)))
    journal_ref = parameters.get('journal') or parameters.get('self')
    if journal_ref and source.action in {'accounting.journal.reverse_partial', 'accounting.journal.reverse', 'accounting.journal.model_reverse', 'accounting.journal.reverse_correction', 'accounting.journal.post'}:
        journal = decode_value(journal_ref, source.company)
        entries = journal.entries.filter(entry_type='DEBIT')
        if source.action.endswith('reverse_partial'):
            amounts = decode_value(parameters.get('amounts'), source.company) or {}
            entry_ids = decode_value(parameters.get('entry_ids'), source.company)
            selected = entry_ids or list(amounts)
            entries = entries.filter(pk__in=selected)
            return sum((Decimal(str(amounts.get(entry.pk, entry.amount))) for entry in entries), Decimal('0'))
        original = sum((entry.amount for entry in entries), Decimal('0'))
        correction = decode_value(parameters.get('correction_entries'), source.company) or []
        return original + sum((Decimal(str(line['amount'])) for line in correction if line.get('entry_type') == 'DEBIT'), Decimal('0'))
    if 'journals' in parameters:
        journals = decode_value(parameters['journals'], source.company)
        return sum((entry.amount for journal in journals for entry in journal.entries.filter(entry_type='DEBIT')), Decimal('0'))
    if 'entries' in parameters:
        entries = decode_value(parameters['entries'], source.company) or []
        if not all(isinstance(line, dict) for line in entries):
            return None
        return sum((Decimal(str(line['amount'])) for line in entries if line.get('entry_type') == 'DEBIT'), Decimal('0'))
    if 'lines' in parameters:
        lines = decode_value(parameters['lines'], source.company)
        total = Decimal('0')
        for line in lines:
            reference = line.get('purchase_order_line') or line.get('sales_order_line')
            unit = line.get('unit_cost', line.get('unit_price'))
            if unit is None and reference is not None:
                unit = getattr(reference, 'unit_cost', getattr(reference, 'unit_price', None))
            if unit is None:
                return None
            total += Decimal(str(line.get('quantity',0))) * Decimal(str(unit))
        return total
    if 'quantity' in parameters and ('unit_cost' in parameters or 'unit_price' in parameters):
        quantity = decode_value(parameters['quantity'], source.company)
        price = decode_value(parameters.get('unit_cost', parameters.get('unit_price')), source.company)
        if price is not None:
            return abs(Decimal(str(quantity)) * Decimal(str(price)))
    for key in ('sales_order', 'purchase_order', 'landed_cost', 'tax_return', 'reval'):
        if key in parameters:
            obj = decode_value(parameters[key], source.company)
            if hasattr(obj, 'lines'):
                if key == 'tax_return':
                    return sum((abs(line.tax_amount) for line in obj.lines.all()), Decimal('0'))
                if key == 'reval':
                    return sum((abs(line.unrealized_gain_loss) for line in obj.lines.all()), Decimal('0'))
                return sum((Decimal(str(getattr(line,'quantity',1))) * Decimal(str(getattr(line,'unit_price',getattr(line,'unit_cost',getattr(line,'amount',0))))) for line in obj.lines.all()),Decimal('0'))
    return None


def _operation_currency(values: dict) -> str:
    for key in ('cash_account', 'reval', 'journal', 'self', 'payment_file', 'payroll_run', 'invoice', 'sales_order', 'purchase_order'):
        source = values.get(key)
        authoritative = (getattr(source, 'currency', None) or getattr(source, 'base_currency', None)) if source is not None else None
        if authoritative:
            if values.get('currency') and str(values['currency']).upper() != str(authoritative).upper():
                raise ValidationError('The currency must match the business source.')
            return str(authoritative).upper()
    return str(values.get('currency') or 'NGN').upper()


def proposal_operation(action: str, permission: str, submit_permission: str | None = None, amount: Callable | None = None, snapshot: Callable | None = None) -> Callable:
    """A human operation queues its reviewed parameters; approved callbacks execute it."""
    def decorate(operation: Callable) -> Callable:
        signature = inspect.signature(operation)
        _OPERATIONS[action] = operation
        _SUBMISSION_PERMISSIONS[action] = submit_permission or permission

        def validate(source: Any, payload: dict) -> None:
            if source.action != action or source.status != 'PENDING':
                raise ValidationError('This proposal is not pending for the selected action.')
            values = decode_value(source.parameters, source.company)
            signature.bind(**values)

        def apply(source: Any, actor: Any, payload: dict) -> None:
            values = decode_value(source.parameters, source.company)
            if 'user' in signature.parameters:
                values['user'] = actor
            try:
                result = operation(**values)
            except (ValueError, TypeError) as exc:
                raise ValidationError(str(exc)) from exc
            source.status = 'APPLIED'
            if isinstance(result, models.Model):
                source.result_type = result._meta.label_lower
                source.result_id = result.pk
            source.save(update_fields=['status', 'result_type', 'result_id'])

        def beneficiaries(source: Any) -> list[int]:
            from .beneficiaries import employee_beneficiaries
            return employee_beneficiaries(source.parameters, source.company)

        register_action(ApprovalAction(
            key=action, model_label='company.ActionProposal', permission=permission,
            apply=apply, snapshot=snapshot or proposal_snapshot, validate=validate,
            requester=lambda source: source.created_by, amount=amount or _proposal_amount, beneficiaries=beneficiaries,
        ))

        @wraps(operation)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            supplied_key = kwargs.pop('approval_key', None) or _request_key.get()
            actor = kwargs.pop('approval_actor', None) or _request_actor.get()
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            values = dict(bound.arguments)
            company = values.get('company')
            if company is None:
                for value in values.values():
                    if isinstance(value, models.Model):
                        company = object_company(value)
                        if company:
                            break
            execution = current_execution()
            if execution is not None:
                if company is None or company.pk != execution.company_id:
                    raise PermissionDenied('Derived actions must belong to the approved company.')
                return operation(*args, **kwargs)
            actor = actor or values.get('user')
            require_company_authority(actor, company, submit_permission or permission)
            Proposal = apps.get_model('company', 'ActionProposal')
            parameters = encode_value(values)
            import hashlib
            import json
            from .models import ApprovalRequest
            digest = hashlib.sha256(json.dumps(parameters, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            request_key = hashlib.sha256(str(supplied_key).encode()).hexdigest() if supplied_key else digest
            with transaction.atomic():
                proposal, created = Proposal.objects.get_or_create(company=company, action=action, created_by=actor, request_key=request_key,
                    defaults={'parameters': parameters, 'currency': _operation_currency(values)})
                if not created:
                    if proposal.parameters != parameters:
                        raise ValidationError('This submission key was already used with different details.')
                    previous = ApprovalRequest.objects.filter(content_type=ContentType.objects.get_for_model(proposal), object_id=proposal.pk, action=action).order_by('-pk').first()
                    if previous is not None:
                        if previous.status in ('REJECTED', 'CANCELLED'):
                            raise ValidationError('Use a new submission key for a revised request.')
                        return previous
                return submit_approval(source=proposal, action=action, requester=actor)
        return wrapped
    return decorate


def pending_response(request: Any, approval: Any) -> Any:
    from django.contrib import messages
    from django.shortcuts import redirect
    messages.success(request, 'Submitted for independent approval. No business changes have been applied.')
    return redirect('approvals:detail', pk=approval.pk)
