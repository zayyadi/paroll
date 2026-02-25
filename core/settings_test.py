from __future__ import annotations

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

# Keep tests deterministic and quiet by disabling notification side effects.
NOTIFICATION_SIGNALS_ENABLED = False
