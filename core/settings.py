import os
from celery.schedules import crontab

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.environ.get("SECRET_KEY")

DEBUG = bool(os.environ.get("DEBUG"))

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
]

INSTALLED_APPS = [
    "tailwind",
    # "adminlte3_theme",
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "crispy_forms",
    "crispy_tailwind",
    "api",
    "rest_framework",
    "users",
    "users.email_backend",
    "payroll",
    "theme",
    "django_browser_reload",
    "widget_tweaks",
    "mathfilters",
    "django.contrib.humanize",
    "monthyear",
    "import_export",
    "social_django",
    "accounting",
    "company",
    # Channels for real-time notifications
    "channels",
    "channels_redis",
    # Celery Beat for scheduled tasks
    "django_celery_beat",
]

SITE_ID = 1

INTERNAL_IPS = [
    "127.0.0.1",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounting.middleware.AuditTrailMiddleware",
    "accounting.middleware.SystemUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "company.context_processors.tenant_context",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# ASGI application for WebSocket support
ASGI_APPLICATION = "core.asgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ.get("DB_NAME", "payroll_db"),
        "USER": os.environ.get("DB_USER", "payroll_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "payroll_password"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_LOCATION", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "payroll",
        "TIMEOUT": 300,  # 5 minutes default
    }
}

AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "social_core.backends.github.GithubOAuth2",
    "social_core.backends.twitter.TwitterOAuth",
    "social_core.backends.facebook.FacebookOAuth2",
)

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
]

SITE_TITLE = os.getenv("SITE_TITLE", "PAYROLL")

CACHE_TTL = 60 * 15

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": (
                "%(asctime)s [%(process)d] [%(levelname)s] "
                + "pathname=%(pathname)s lineno=%(lineno)s "
                + "funcname=%(funcName)s %(message)s"
            ),
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {"format": "%(levelname)s %(message)s"},
    },
    "handlers": {
        "null": {
            "level": "DEBUG",
            "class": "logging.NullHandler",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "testlogger": {
            "handlers": ["console"],
            "level": "INFO",
        }
    },
}

DEBUG_PROPAGATE_EXCEPTIONS = True

LANGUAGE_CODE = "en-ng"

TIME_ZONE = "Africa/Lagos"

USE_THOUSAND_SEPARATOR = True

USE_L10N = True

USE_I18N = True

USE_TZ = True

TAILWIND_APP_NAME = "theme"

CRISPY_ALLOWED_TEMPLATE_PACKS = ["tailwind"]

CRISPY_TEMPLATE_PACK = "tailwind"

STATIC_URL = "static/"
MEDIA_URL = "/media/"

MEDIA_ROOT = os.path.join(BASE_DIR, "media")

STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")


SOCIAL_AUTH_JSONFIELD_ENABLED = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_REDIRECT_URL = "payroll:index"

LOGIN_URL = "users:login"

LOGOUT_URL = "users:logout"

SOCIAL_AUTH_LOGIN_ERROR_URL = "users:settings"

SOCIAL_AUTH_LOGIN_REDIRECT_URL = "payroll:index"

SOCIAL_AUTH_RAISE_EXCEPTIONS = False

SOCIAL_AUTH_GITHUB_KEY = os.environ.get("client_id")

SOCIAL_AUTH_GITHUB_SECRET = os.environ.get("client_secret")

SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.user.get_username",
    "social_core.pipeline.social_auth.associate_by_email",
    "social_core.pipeline.user.create_user",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.user.user_details",
)

SOCIAL_AUTH_ADMIN_USER_SEARCH_FIELDS = ["username", "first_name", "email"]

X_FRAME_OPTIONS = "SAMEORIGIN"

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "users.email_backend.EmailBackend")

EMAIL_HOST = os.environ.get("EMAIL_HOST")

EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")

EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")

EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))

EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")

EMAIL_FILE_PATH = os.getenv("EMAIL_FILE_PATH", os.path.join(BASE_DIR, "test-emails"))

if not os.path.exists(EMAIL_FILE_PATH):
    os.makedirs(EMAIL_FILE_PATH)

MULTI_COMPANY_MEMBERSHIP_ENABLED = (
    os.getenv("MULTI_COMPANY_MEMBERSHIP_ENABLED", "False").lower() == "true"
)

REGISTRATION_OTP_TIMEOUT_SECONDS = int(
    os.getenv("REGISTRATION_OTP_TIMEOUT_SECONDS", "600")
)
REGISTRATION_RESEND_COOLDOWN_SECONDS = int(
    os.getenv("REGISTRATION_RESEND_COOLDOWN_SECONDS", "60")
)
REGISTRATION_RESEND_MAX_PER_HOUR = int(
    os.getenv("REGISTRATION_RESEND_MAX_PER_HOUR", "5")
)

# ============================================================================
# NOTIFICATION SYSTEM SETTINGS
# ============================================================================

# Notification retention and archiving
NOTIFICATION_RETENTION_DAYS = int(os.getenv("NOTIFICATION_RETENTION_DAYS", "90"))

NOTIFICATION_MAX_AGGREGATION_COUNT = int(
    os.getenv("NOTIFICATION_MAX_AGGREGATION_COUNT", "20")
)

NOTIFICATION_AGGREGATION_TIME_WINDOW = int(
    os.getenv("NOTIFICATION_AGGREGATION_TIME_WINDOW", "3600")
)

# Notification email settings
EMAIL_NOTIFICATION_FROM_EMAIL = os.getenv(
    "EMAIL_NOTIFICATION_FROM_EMAIL", DEFAULT_FROM_EMAIL
)

EMAIL_NOTIFICATION_REPLY_TO = os.getenv(
    "EMAIL_NOTIFICATION_REPLY_TO", DEFAULT_FROM_EMAIL
)

# ============================================================================
# CELERY CONFIGURATION
# ============================================================================

# Celery broker and backend (Redis)
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/2")

CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2"
)

# Celery timezone
CELERY_TIMEZONE = TIME_ZONE

CELERY_ENABLE_UTC = True

# Celery task settings
CELERY_TASK_SERIALIZER = "json"

CELERY_RESULT_SERIALIZER = "json"

CELERY_ACCEPT_CONTENT = ["json"]

CELERY_RESULT_EXPIRES = 3600  # 1 hour

# Celery task execution
CELERY_TASK_ACKS_LATE = True

CELERY_TASK_REJECT_ON_WORKER_LOST = True

CELERY_WORKER_PREFETCH_MULTIPLIER = 1

CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000

# Celery retry settings
CELERY_TASK_DEFAULT_RETRY_DELAY = 60

CELERY_TASK_MAX_RETRIES = 3

CELERY_TASK_RETRY_BACKOFF = True

CELERY_TASK_RETRY_JITTER = True

# Celery task tracking
CELERY_TASK_TRACK_STARTED = True

CELERY_TASK_SEND_SENT_EVENT = True

# Celery worker settings
CELERY_WORKER_CONCURRENCY = 4

# Celery task queues (priority-based)
CELERY_TASK_ROUTES = {
    "notifications_critical": {
        "exchange": "notifications",
        "routing_key": "notifications.critical",
        "delivery_mode": "persistent",
    },
    "notifications_high": {
        "exchange": "notifications",
        "routing_key": "notifications.high",
        "delivery_mode": "persistent",
    },
    "notifications_normal": {
        "exchange": "notifications",
        "routing_key": "notifications.normal",
        "delivery_mode": "persistent",
    },
    "notifications_low": {
        "exchange": "notifications",
        "routing_key": "notifications.low",
        "delivery_mode": "persistent",
    },
}

# Celery task routing
CELERY_TASK_ROUTES = {
    "payroll.deliver_notification": {
        "queue": "notifications_normal",
        "routing_key": "notifications.normal",
    },
    "payroll.send_in_app_notification": {
        "queue": "notifications_normal",
        "routing_key": "notifications.normal",
    },
    "payroll.send_email_notification": {
        "queue": "notifications_normal",
        "routing_key": "notifications.normal",
    },
    "payroll.send_push_notification": {
        "queue": "notifications_normal",
        "routing_key": "notifications.normal",
    },
    "payroll.send_sms_notification": {
        "queue": "notifications_normal",
        "routing_key": "notifications.normal",
    },
    "payroll.archive_old_notifications": {
        "queue": "notifications_low",
        "routing_key": "notifications.low",
    },
    "payroll.send_daily_digest": {
        "queue": "notifications_low",
        "routing_key": "notifications.low",
    },
    "payroll.send_weekly_digest": {
        "queue": "notifications_low",
        "routing_key": "notifications.low",
    },
}

# Celery task rate limiting
CELERY_TASK_ANNOTATIONS = {
    "payroll.deliver_notification": {
        "rate_limit": "100/m",
    },
    "payroll.send_email_notification": {
        "rate_limit": "50/m",
    },
    "payroll.send_sms_notification": {
        "rate_limit": "20/m",
    },
    "payroll.send_push_notification": {
        "rate_limit": "200/m",
    },
}

# Celery Beat schedule (scheduled tasks)
CELERY_BEAT_SCHEDULE = {
    "archive-old-notifications": {
        "task": "payroll.archive_old_notifications",
        "schedule": crontab(hour=2, minute=0),
    },
    "send-daily-digests": {
        "task": "payroll.send_daily_digest",
        "schedule": crontab(hour=8, minute=0),
    },
    "send-weekly-digests": {
        "task": "payroll.send_weekly_digest",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
    },
}

# Celery Beat scheduler
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ============================================================================
# DJANGO CHANNELS CONFIGURATION
# ============================================================================

# Channel layers for WebSocket communication
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                (
                    os.environ.get("REDIS_HOST", "127.0.0.1"),
                    int(os.environ.get("REDIS_PORT", "6379")),
                )
            ],
            "db": int(os.environ.get("REDIS_DB", "3")),
        },
    },
}

# ============================================================================
# PUSH NOTIFICATION CONFIGURATION (FCM)
# ============================================================================

FCM_DJANGO_SETTINGS = {
    "FCM_SERVER_KEY": os.environ.get("FCM_SERVER_KEY"),
    "ONE_DEVICE_PER_USER": False,
}

# ============================================================================
# SMS CONFIGURATION (Twilio)
# ============================================================================

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")

TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")

TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")

TWILIO_DEFAULT_FROM = TWILIO_PHONE_NUMBER

# ============================================================================
# NOTIFICATION LOGGING
# ============================================================================

# Update logging configuration to include notifications
LOGGING["loggers"]["notifications"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}

LOGGING["loggers"]["celery"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}

LOGGING["loggers"]["channels"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}

AUTH_USER_MODEL = "users.CustomUser"

AUTH_USER_DEFAULT_GROUP = "payroll-members"

DEFAULT_EMAIL_DOMAIN = "example.com"

SITE_TAGLINE = os.getenv("SITE_TAGLINE", "Demo Site")

SITE_DESCRIPTION = "SITE_DESCRIPTION"

SITE_LOGO = os.getenv("SITE_LOGO", "http://localhost:8000/static/logo.png")

JAZZMIN_SETTINGS = {
    "site_title": "Payroll Admin",
    "site_header": "Payroll",
    "site_brand": "Payroll",
    "site_logo": "images/logo.png",
    "login_logo": "images/logo.png",
    "login_logo_dark": "images/logo.png",
    "site_logo_classes": "img-circle",
    "site_icon": "images/logo.png",
    "welcome_sign": "Welcome to Payroll Admin",
    "copyright": "Payroll Ltd",
    "search_model": "auth.User",
    "user_avatar": "employee_user.photo",
    "topmenu_links": [
        {"name": "Home", "url": "admin:index", "permissions": ["auth.view_user"]},
        {
            "name": "Support",
            "url": "https://github.com/farridav/django-jazzmin/issues",
            "new_window": True,
        },
        {"model": "auth.User"},
    ],
    "usermenu_links": [
        {
            "name": "Support",
            "url": "https://github.com/farridav/django-jazzmin/issues",
            "new_window": True,
        },
        {"model": "auth.User"},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    "order_with_respect_to": [
        "auth",
        "payroll",
        "payroll.EmployeeProfile",
        "payroll.Payroll",
        "accounting",
        "accounting.Account",
        "accounting.Journal",
        "accounting.FiscalYear",
        "accounting.AccountingPeriod",
        "accounting.JournalEntry",
        "accounting.AccountingAuditTrail",
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "payroll.EmployeeProfile": "fas fa-user-tie",
        "payroll.Payroll": "fas fa-money-check-alt",
        "accounting": "fas fa-calculator",
        "accounting.Account": "fas fa-wallet",
        "accounting.Journal": "fas fa-book",
        "accounting.FiscalYear": "fas fa-calendar-alt",
        "accounting.AccountingPeriod": "fas fa-calendar-week",
        "accounting.JournalEntry": "fas fa-receipt",
        "accounting.AccountingAuditTrail": "fas fa-history",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": False,
    "custom_css": None,
    "custom_js": None,
    "use_google_fonts_cdn": True,
    "show_ui_builder": True,
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs",
    },
}
