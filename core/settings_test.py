from __future__ import annotations

import importlib.util

from core.settings import *  # noqa: F401,F403


# Use SQLite for local/unit tests when PostgreSQL is unavailable.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR + "/test_db.sqlite3",  # noqa: F405
    }
}

# Speed up tests.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Ensure tests do not require external Redis services.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Avoid cache-backed throttle dependencies in test environment.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},
}

# Surface raw exceptions in tests instead of rendering 500 templates.
DEBUG_PROPAGATE_EXCEPTIONS = True
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
ACCOUNTING_SUPERUSER_ONLY_UNTIL_TENANT_SCOPED = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# Keep tests deterministic and quiet by disabling notification side effects.
NOTIFICATION_SIGNALS_ENABLED = False


def _is_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


if _is_installed("channels"):
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }


OPTIONAL_APPS = {
    "api": "rest_framework",
    "rest_framework": "rest_framework",
    "drf_spectacular": "drf_spectacular",
    "tailwind": "tailwind",
    "jazzmin": "jazzmin",
    "crispy_forms": "crispy_forms",
    "crispy_tailwind": "crispy_tailwind",
    "theme": "theme",
    "django_browser_reload": "django_browser_reload",
    "widget_tweaks": "widget_tweaks",
    "mathfilters": "mathfilters",
    "import_export": "import_export",
    "social_django": "social_django",
    "channels": "channels",
    "channels_redis": "channels_redis",
    "django_celery_beat": "django_celery_beat",
}

INSTALLED_APPS = [
    app
    for app in INSTALLED_APPS  # noqa: F405
    if app not in OPTIONAL_APPS or _is_installed(OPTIONAL_APPS[app])
]

MIDDLEWARE = [
    middleware
    for middleware in MIDDLEWARE  # noqa: F405
    if not (
        middleware == "social_django.middleware.SocialAuthExceptionMiddleware"
        and not _is_installed("social_django")
    )
]

AUTHENTICATION_BACKENDS = tuple(
    backend
    for backend in AUTHENTICATION_BACKENDS  # noqa: F405
    if backend == "django.contrib.auth.backends.ModelBackend"
    or (
        backend.startswith("social_core.backends.")
        and _is_installed("social_core")
        and _is_installed("social_django")
    )
)
