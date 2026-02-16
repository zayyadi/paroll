from django.conf import settings

from company.utils import can_switch_company, get_user_companies, get_user_company


def tenant_context(request):
    user = getattr(request, "user", None)
    return {
        "current_company": get_user_company(user),
        "user_companies": get_user_companies(user) if user else [],
        "can_switch_company": can_switch_company(user) if user else False,
        "multi_company_enabled": settings.MULTI_COMPANY_MEMBERSHIP_ENABLED,
    }
