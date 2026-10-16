"""Atomic, company-scoped maker/checker decisions and trusted domain execution."""
import hashlib
import json
from contextlib import contextmanager
from decimal import Decimal
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .context import _execution, internal_write
from .models import ApprovalPolicy, ApprovalRequest, ApprovalDecision, ApprovalEvent
from .permissions import can_decide, user_in_company, has_company_permission
from .registry import get_action


def _json(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True))


def _snapshot(source, action):
    raw = (
        action.snapshot(source)
        if action.snapshot
        else {
            field.attname: getattr(source, field.attname)
            for field in source._meta.concrete_fields
        }
    )
    return _json(raw)


def _hash(snapshot, payload):
    return hashlib.sha256(
        json.dumps(
            {"source": snapshot, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _company(source, action):
    if action.company:
        company = action.company(source)
        if company:
            return company
    # Import lazily: parameter proposals depend on workflow services.
    from .proposals import object_company
    company = object_company(source)
    if company:
        return company
    raise ValidationError("Approval source requires an explicit company.")


def _locked_source(source, action):
    if not source.pk or source._meta.label_lower != action.model_label.lower():
        raise ValidationError("Wrong or unsaved approval source.")
    return type(source)._base_manager.select_for_update().get(pk=source.pk)


def _policy(company, action, source, payload):
    amount = action.amount(source, payload) if action.amount else None
    currency = getattr(source, "currency", "") or ("NGN" if amount is not None else "")
    supplied_currency = payload.get("currency")
    if supplied_currency and currency and supplied_currency != currency:
        raise ValidationError("The approval currency must match the business source.")
    currency = currency or supplied_currency or ""
    eligible = []
    policies = list(
        ApprovalPolicy.objects.filter(company=company, action=action.key, enabled=True)
    )
    if amount is not None:
        amount = Decimal(str(amount))
        if not amount.is_finite() or amount < 0:
            raise ValidationError("Approval amount must be finite and nonnegative.")
    if any(p.minimum_amount is not None for p in policies) and (
        amount is None or not currency
    ):
        raise ValidationError(
            "Configured monetary approvals require an amount and currency."
        )
    for policy in policies:
        if policy.currency and policy.currency != currency:
            continue
        if policy.minimum_amount is not None:
            if amount is None:
                raise ValidationError("A reviewed monetary amount is required for this approval policy.")
            if Decimal(str(amount)) < policy.minimum_amount:
                continue
        eligible.append(policy)
    if eligible:
        chosen = max(
            eligible,
            key=lambda p: (
                p.minimum_amount if p.minimum_amount is not None else Decimal("-1"),
                bool(p.currency),
                p.pk,
            ),
        )
        chosen.full_clean()
        return _json(
            {
                "policy_id": chosen.pk,
                "stages": chosen.stages,
                "currency": currency,
                "amount": amount,
            }
        )
    stages = action.default_stages or [
        {"permission": action.permission, "approver_ids": []}
    ]
    # Adapters are trusted code; persisted overrides receive full model validation.
    return _json(
        {"policy_id": None, "stages": stages, "currency": currency, "amount": amount}
    )


def current_execution():
    return _execution.get()


def execution_authorized(source, action) -> bool:
    request = current_execution()
    return bool(
        request
        and request.action == action
        and request.object_id == source.pk
        and request.content_type.model_class() == type(source)
    )


@contextmanager
def _execute(request):
    token = _execution.set(request)
    try:
        yield
    finally:
        _execution.reset(token)


def _event(request, actor, kind, **detail):
    ApprovalEvent.objects.create(
        request=request, actor=actor, kind=kind, detail=_json(detail)
    )


@transaction.atomic
def submit_approval(*, source, action, requester, payload=None):
    adapter = get_action(action)
    source = _locked_source(source, adapter)
    company = _company(source, adapter)
    if not user_in_company(requester, company):
        raise PermissionDenied("Requester must belong to the source company.")
    maker = adapter.requester(source) if adapter.requester else None
    if maker is not None and maker.pk != requester.pk:
        raise PermissionDenied("Only the original requester may submit this action.")
    if payload is not None and not isinstance(payload, dict):
        raise ValidationError("Approval payload must be an object.")
    payload = _json(payload or {})
    if adapter.validate:
        adapter.validate(source, payload)
    snapshot = _snapshot(source, adapter)
    digest = _hash(snapshot, payload)
    ct = ContentType.objects.get_for_model(source)
    key = f"{company.pk}:{action}:{ct.pk}:{source.pk}"
    pending = (
        ApprovalRequest.objects.select_for_update().filter(pending_key=key).first()
    )
    if pending:
        if pending.source_hash == digest and pending.requester_id == requester.pk:
            return pending
        raise ValidationError(
            "A different pending approval already exists; cancel it before resubmitting."
        )
    if ApprovalRequest.objects.filter(
        company=company,
        action=action,
        content_type=ct,
        object_id=source.pk,
        status="APPROVED",
        source_hash=digest,
    ).exists():
        raise ValidationError("This action has already been approved.")
    beneficiaries = list(adapter.beneficiaries(source)) if adapter.beneficiaries else []
    beneficiaries = sorted(
        {getattr(value, "pk", value) for value in beneficiaries if value is not None}
    )
    with internal_write():
        request = ApprovalRequest.objects.create(
            company=company,
            action=action,
            content_type=ct,
            object_id=source.pk,
            requester=requester,
            payload=payload,
            source_snapshot=snapshot,
            source_hash=digest,
            beneficiary_ids=beneficiaries,
            policy_snapshot=_policy(company, adapter, source, payload),
            pending_key=key,
        )
        _event(request, requester, "SUBMITTED")
    return request


@transaction.atomic
def decide_approval(*, approval, actor, decision="APPROVE", comment=""):
    tentative = ApprovalRequest.objects.get(pk=getattr(approval, "pk", approval))
    source = (
        tentative.content_type.model_class()
        ._base_manager.select_for_update()
        .filter(pk=tentative.object_id)
        .first()
    )
    request = ApprovalRequest.objects.select_for_update().get(pk=tentative.pk)
    if decision not in ("APPROVE", "REJECT"):
        raise ValidationError("Invalid approval decision.")
    if decision == "REJECT" and not comment.strip():
        raise ValidationError("A rejection reason is required.")
    if not can_decide(request, actor):
        raise PermissionDenied(
            "Independent company-scoped stage authority is required."
        )
    adapter = get_action(request.action)
    if source is None:
        raise ValidationError(
            "The approval source no longer exists; cancel this request."
        )
    if (
        _company(source, adapter).pk != request.company_id
        or _hash(_snapshot(source, adapter), request.payload) != request.source_hash
    ):
        raise ValidationError(
            "The source changed after submission. Cancel and submit a new request."
        )
    maker = adapter.requester(source) if adapter.requester else None
    beneficiaries = list(adapter.beneficiaries(source)) if adapter.beneficiaries else []
    current_beneficiaries = sorted(
        {getattr(value, "pk", value) for value in beneficiaries if value is not None}
    )
    if (
        maker is not None and maker.pk != request.requester_id
    ) or current_beneficiaries != request.beneficiary_ids:
        raise ValidationError(
            "Requester or beneficiaries changed after submission; resubmit the request."
        )
    if adapter.validate:
        adapter.validate(source, request.payload)
    with internal_write():
        ApprovalDecision.objects.create(
            request=request,
            actor=actor,
            stage=request.current_stage,
            decision=decision,
            comment=comment,
        )
        _event(request, actor, decision, stage=request.current_stage, comment=comment)
        if decision == "REJECT":
            if adapter.reject:
                with _execute(request):
                    adapter.reject(source, actor, request.payload)
            request.status = "REJECTED"
        elif request.current_stage + 1 < len(request.policy_snapshot["stages"]):
            request.current_stage += 1
        else:
            with _execute(request):
                adapter.apply(source, actor, request.payload)
            source.refresh_from_db()
            request.execution_snapshot = _snapshot(source, adapter)
            request.status = "APPROVED"
        if request.status != "PENDING":
            request.pending_key = None
            request.completed_at = timezone.now()
        request.save()
    return request


@transaction.atomic
def cancel_approval(*, approval, actor, reason=""):
    if not reason.strip():
        raise ValidationError("A cancellation reason is required.")
    tentative = ApprovalRequest.objects.get(pk=getattr(approval, "pk", approval))
    source = (
        tentative.content_type.model_class()
        ._base_manager.select_for_update()
        .filter(pk=tentative.object_id)
        .first()
    )
    request = ApprovalRequest.objects.select_for_update().get(pk=tentative.pk)
    if (
        request.status != "PENDING"
        or actor.pk != request.requester_id
        or not user_in_company(actor, request.company_id)
    ):
        raise PermissionDenied("Only the requester may cancel a pending approval.")
    adapter = get_action(request.action)
    with internal_write():
        if (
            source is not None
            and adapter.cancel
            and _company(source, adapter).pk == request.company_id
            and _hash(_snapshot(source, adapter), request.payload)
            == request.source_hash
        ):
            with _execute(request):
                adapter.cancel(source, actor, request.payload)
        request.status = "CANCELLED"
        request.pending_key = None
        request.completed_at = timezone.now()
        request.save()
        _event(request, actor, "CANCELLED", reason=reason)
    return request


@transaction.atomic
def request_or_decide(
    *, source, action, actor, payload=None, decision="APPROVE", comment=""
):
    adapter = get_action(action)
    source = _locked_source(source, adapter)
    company = _company(source, adapter)
    if not user_in_company(actor, company):
        raise PermissionDenied("Company-scoped authority is required.")
    ct = ContentType.objects.get_for_model(source)
    request = (
        ApprovalRequest.objects.select_for_update()
        .filter(
            company=company,
            action=action,
            content_type=ct,
            object_id=source.pk,
            status="PENDING",
        )
        .first()
    )
    if request is None:
        maker = adapter.requester(source) if adapter.requester else None
        if maker is None:
            raise ValidationError(
                "Original maker is unknown. Explicit submission is required."
            )
        request = submit_approval(
            source=source, action=action, requester=maker, payload=payload
        )
    elif payload is not None and _json(payload) != request.payload:
        raise ValidationError("Decision payload differs from the submitted request.")
    return decide_approval(
        approval=request, actor=actor, decision=decision, comment=comment
    )


@contextmanager
def authorize_approved_execution(approval, actor):
    """Deferred business execution; only the final checker can resume this action.

    The source must match its completed snapshot; the adapter must enforce its
    domain one-time/effective-date rules.
    """
    with transaction.atomic():
        tentative = ApprovalRequest.objects.get(pk=getattr(approval, "pk", approval))
        source = (
            tentative.content_type.model_class()
            ._base_manager.select_for_update()
            .filter(pk=tentative.object_id)
            .first()
        )
        request = ApprovalRequest.objects.select_for_update().get(pk=tentative.pk)
        final = request.decisions.filter(decision="APPROVE").order_by("-stage").first()
        if (
            request.status != "APPROVED"
            or not final
            or final.actor_id != actor.pk
            or not user_in_company(actor, request.company_id)
        ):
            raise PermissionDenied(
                "Only the original final checker may execute this approved action."
            )
        adapter = get_action(request.action)
        stage = request.policy_snapshot["stages"][final.stage]
        designated = stage.get("approver_ids", [])
        if (designated and actor.pk not in designated) or (
            not designated
            and not has_company_permission(
                actor, request.company_id, stage["permission"]
            )
        ):
            raise PermissionDenied("Final checker no longer has execution authority.")
        if source is None:
            raise ValidationError("The approved source no longer exists.")
        if (
            _company(source, adapter).pk != request.company_id
            or _snapshot(source, adapter) != request.execution_snapshot
        ):
            raise ValidationError(
                "Approved source has changed; a new approval is required."
            )
        beneficiaries = (
            list(adapter.beneficiaries(source)) if adapter.beneficiaries else []
        )
        ids = sorted(
            {
                getattr(value, "pk", value)
                for value in beneficiaries
                if value is not None
            }
        )
        maker = adapter.requester(source) if adapter.requester else None
        if ids != request.beneficiary_ids or (
            maker is not None and maker.pk != request.requester_id
        ):
            raise ValidationError(
                "Approved participants have changed; a new approval is required."
            )
        with _execute(request):
            yield request
