from django.conf import settings
from django.db.models import QuerySet


def get_user_company(user):
    """Resolve the user's active company and establish it as the tenant context.

    Resolving a company also sets the contextvars-based company context (see
    ``company.tenancy``), so any tenant-scoped model queried afterwards in the
    same task/request is scoped to that company. Callers that need a different
    context should wrap their work in ``company_context(...)`` explicitly.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    if settings.MULTI_COMPANY_MEMBERSHIP_ENABLED:
        active_company = getattr(user, "active_company", None)
        if active_company and user.company_memberships.filter(company=active_company).exists():
            company = active_company
        else:
            primary_company = getattr(user, "company", None)
            if primary_company and user.company_memberships.filter(company=primary_company).exists():
                company = primary_company
            else:
                membership = user.company_memberships.select_related("company").first()
                company = membership.company if membership else None
    else:
        company = getattr(user, "company", None) or getattr(user, "active_company", None)

    if company is not None:
        from company.tenancy import set_current_company

        set_current_company(company)
    return company


def get_user_companies(user):
    if not getattr(user, "is_authenticated", False):
        return []
    if settings.MULTI_COMPANY_MEMBERSHIP_ENABLED:
        return [m.company for m in user.company_memberships.select_related("company").all()]
    company = get_user_company(user)
    return [company] if company else []


def can_switch_company(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if not settings.MULTI_COMPANY_MEMBERSHIP_ENABLED:
        return False
    return user.company_memberships.count() > 1


def set_active_company(user, company):
    if not settings.MULTI_COMPANY_MEMBERSHIP_ENABLED:
        return False
    if not user.company_memberships.filter(company=company).exists():
        return False
    user.active_company = company
    user.save(update_fields=["active_company"])
    return True


def company_filter(queryset: QuerySet, user):
    company = get_user_company(user)
    if company is None:
        return queryset.none()
    return queryset.filter(company=company)
