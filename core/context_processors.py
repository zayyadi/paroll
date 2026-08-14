from django.conf import settings


def branding(request):
    app_name = getattr(settings, "APP_NAME", "PayNest")
    app_tagline = getattr(settings, "APP_TAGLINE", "Employee Management System")
    logo_path = getattr(settings, "APP_LOGO_PATH", "images/paynest-logo.svg")
    logo_url = getattr(settings, "APP_LOGO_URL", f"{settings.MEDIA_URL}branding/paynest-logo.svg")

    return {
        "APP_NAME": app_name,
        "APP_TAGLINE": app_tagline,
        "APP_LOGO_PATH": logo_path,
        "APP_LOGO_URL": logo_url,
    }


def user_roles(request):
    """
    Inject role flags for every request so templates can render role-specific
    navigation without reaching into user.groups directly.

    Flags:
      - is_super_admin_user: superuser or "Super Admin" group
      - is_finance_user: superuser or "Finance" group
      - is_hr_user: superuser, staff, or "HR" group
      - is_payroll_processor_user: superuser or "Payroll Processor" group
      - is_employee_user: authenticated and none of the above
    """
    user = getattr(request, "user", None)
    flags = {
        "is_super_admin_user": False,
        "is_hr_user": False,
        "is_finance_user": False,
        "is_payroll_processor_user": False,
        "is_employee_user": False,
    }
    if not getattr(user, "is_authenticated", False):
        return flags

    # Single query for all role groups instead of one .exists() per role.
    group_names = set(
        user.groups.filter(
            name__in=["Super Admin", "Finance", "HR", "Payroll Processor"]
        ).values_list("name", flat=True)
    )
    is_super = user.is_superuser or "Super Admin" in group_names
    is_finance = is_super or "Finance" in group_names
    is_hr = is_super or user.is_staff or "HR" in group_names
    is_payroll_processor = is_super or "Payroll Processor" in group_names

    flags.update(
        {
            "is_super_admin_user": is_super,
            "is_finance_user": is_finance,
            "is_hr_user": is_hr,
            "is_payroll_processor_user": is_payroll_processor,
            "is_employee_user": not (
                is_super or is_finance or is_hr or is_payroll_processor
            ),
        }
    )
    return flags
