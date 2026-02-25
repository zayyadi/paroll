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
