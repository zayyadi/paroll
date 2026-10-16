from django.core.exceptions import ValidationError, ObjectDoesNotExist, PermissionDenied


def action_label(key):
    return key.replace(".", " · ").replace("_", " ").title()


def business_fields(payload, prefix='', company=None):
    fields=[]
    for key,value in payload.items():
        if not prefix and key in ('company','user'):
            continue
        label=(prefix+str(key)).replace('__','_').replace('_',' ').capitalize()
        if isinstance(value,dict) and '__model__' in value:
            from .proposals import decode_value
            try:
                display=str(decode_value(value,company)) if company else 'Referenced record'
            except (ValidationError,ObjectDoesNotExist,PermissionDenied):
                display='Record no longer available'
            fields.append((label,display))
        elif isinstance(value,dict) and '__mapping__' in value:
            from .proposals import decode_value
            mapping = decode_value(value, company)
            fields.extend(business_fields(mapping, label+' / ', company))
        elif isinstance(value,dict) and any(name in value for name in ('__decimal__','__date__','__datetime__','__month__')):
            fields.append((label,str(next(iter(value.values())))))
        elif isinstance(value,dict):
            fields.extend(business_fields(value,label+' / ',company))
        elif isinstance(value,list):
            for index,item in enumerate(value,1):
                if isinstance(item,dict):
                    fields.extend(business_fields(item,f'{label} {index} / ',company))
                else:
                    fields.append((f'{label} {index}',str(item)))
        else:
            fields.append((label,'—' if value is None else str(value)))
    return fields


_AUDIT_METADATA = {
    "id", "pk", "company", "company_id", "user", "user_id", "created_by_id",
    "requested_by_id", "requester_id", "approved_by_id", "published_by_id",
    "created_at", "updated_at", "approved_at", "published_at", "completed_at",
    "content_type_id", "object_id", "status", "source_hash", "policy_snapshot",
    "source_snapshot", "execution_snapshot", "references", "beneficiary_ids",
}


def _reviewed_business_data(value):
    if isinstance(value, list):
        return [_reviewed_business_data(item) for item in value]
    if not isinstance(value, dict):
        return value
    if "__model__" in value:
        return value
    return {
        key: _reviewed_business_data(item)
        for key, item in value.items()
        if str(key).lower() not in _AUDIT_METADATA
        and not str(key).endswith("_id")
        and not str(key) + "_name" in value
        and not any(secret in str(key).lower() for secret in ("password", "secret", "token", "hash", "private_key"))
    }


def _can_view_business_content(approval, user, source):
    from .access import company_administrator
    from .permissions import user_in_company, can_decide
    from .registry import get_action

    if user is None or not user_in_company(user, approval.company_id):
        return False
    eligible = (approval.requester_id == user.pk or company_administrator(user, approval.company)
                or can_decide(approval, user) or approval.decisions.filter(actor=user).exists())
    if not eligible:
        return False
    try:
        visibility = get_action(approval.action).source_visibility
    except ValidationError:
        return False
    return visibility is None or (source is not None and visibility(source, user))


def request_context(approval, user=None):
    source = approval.source
    if source is not None:
        from .registry import get_action
        from .services import _company

        try:
            if _company(source, get_action(approval.action)).pk != approval.company_id:
                source = None
        except (ValidationError, ObjectDoesNotExist):
            source = None
    payload = {}
    can_view_business_content = _can_view_business_content(approval, user, source)
    if can_view_business_content:
        payload = dict(approval.payload)
        snapshot = approval.source_snapshot
        if isinstance(snapshot, dict):
            parameters = snapshot.get("parameters") or snapshot.get("params")
            if isinstance(parameters, dict):
                payload = {**_reviewed_business_data(parameters), **_reviewed_business_data(payload)}
            else:
                payload = {**_reviewed_business_data(snapshot), **_reviewed_business_data(payload)}
    fields = business_fields(payload, company=approval.company)
    reviewed_amount = approval.policy_snapshot.get('amount')
    if can_view_business_content and reviewed_amount is not None:
        from decimal import Decimal
        currency = approval.policy_snapshot.get('currency', '')
        fields.insert(0, ('Reviewed amount', f"{currency} {Decimal(str(reviewed_amount)):,.2f}".strip()))
    label = action_label(approval.action)
    source_label = f'{label} #{approval.object_id}' if source is not None and source._meta.label_lower == 'company.actionproposal' else str(source) if source is not None else 'Source no longer available'
    return {
        "approval": approval,
        "action_label": action_label(approval.action),
        "source_label": source_label,
        "business_fields": fields,
        "can_view_business_content": can_view_business_content,
        "stages": approval.policy_snapshot.get("stages", []),
    }
