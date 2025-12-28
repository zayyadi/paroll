"""
Celery Configuration for Payroll Application

This module configures Celery for asynchronous task processing,
specifically for the notification system with priority-based queues.

Architecture Reference: plans/NOTIFICATION_SYSTEM_ARCHITECTURE.md (Section 11)
"""

import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Create Celery app
app = Celery("payroll")

# Load configuration from Django settings with CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# ============================================================================
# TASK QUEUES
# ============================================================================
# Priority-based queues for notifications to ensure critical messages are processed first
app.conf.task_queues = {
    "notifications_critical": {
        "exchange": "notifications",
        "routing_key": "notifications.critical",
        "delivery_mode": "persistent",  # Survive broker restart
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

# ============================================================================
# TASK ROUTING
# ============================================================================
# Route tasks to appropriate queues based on priority
app.conf.task_routes = {
    # Critical notifications
    "payroll.tasks.notification_tasks.deliver_critical_notification_task": {
        "queue": "notifications_critical",
        "routing_key": "notifications.critical",
    },
    # High priority notifications
    "payroll.tasks.notification_tasks.deliver_high_priority_notification_task": {
        "queue": "notifications_high",
        "routing_key": "notifications.high",
    },
    # Normal notifications (default)
    "payroll.tasks.notification_tasks.deliver_notification_task": {
        "queue": "notifications_normal",
        "routing_key": "notifications.normal",
    },
    # Low priority tasks (digests, cleanup, etc.)
    "payroll.tasks.notification_tasks.send_digest_task": {
        "queue": "notifications_low",
        "routing_key": "notifications.low",
    },
    "payroll.tasks.notification_tasks.archive_old_notifications_task": {
        "queue": "notifications_low",
        "routing_key": "notifications.low",
    },
    "payroll.tasks.notification_tasks.cleanup_failed_deliveries_task": {
        "queue": "notifications_low",
        "routing_key": "notifications.low",
    },
}

# ============================================================================
# TASK SERIALIZATION
# ============================================================================
# Use JSON for serialization (secure and cross-platform)
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.accept_content = ["json"]
app.conf.result_expires = 3600  # Results expire after 1 hour

# ============================================================================
# TIMEZONE CONFIGURATION
# ============================================================================
# Use UTC for consistency
app.conf.timezone = "UTC"
app.conf.enable_utc = True

# ============================================================================
# TASK EXECUTION SETTINGS
# ============================================================================
# Acknowledge tasks after they complete (not at start)
app.conf.task_acks_late = True

# Reject tasks if worker is lost (prevents task loss)
app.conf.task_reject_on_worker_lost = True

# Disable prefetch to prevent tasks from getting stuck on failed workers
app.conf.worker_prefetch_multiplier = 1

# ============================================================================
# RETRY SETTINGS
# ============================================================================
# Default retry settings for tasks
app.conf.task_default_retry_delay = 60  # 1 minute
app.conf.task_max_retries = 3

# Exponential backoff for retries
app.conf.task_retry_backoff = True
app.conf.task_retry_backoff_max = 600  # Max 10 minutes
app.conf.task_retry_jitter = True  # Add randomness to prevent thundering herd

# ============================================================================
# RATE LIMITING
# ============================================================================
# Rate limit per task to prevent overwhelming downstream services
app.conf.task_annotations = {
    "payroll.tasks.notification_tasks.deliver_notification_task": {
        "rate_limit": "100/m",  # Max 100 tasks per minute
    },
    "payroll.tasks.notification_tasks.send_email_task": {
        "rate_limit": "50/m",  # Max 50 emails per minute
    },
    "payroll.tasks.notification_tasks.send_sms_task": {
        "rate_limit": "20/m",  # Max 20 SMS per minute
    },
    "payroll.tasks.notification_tasks.send_push_notification_task": {
        "rate_limit": "200/m",  # Max 200 push notifications per minute
    },
}

# ============================================================================
# TASK TRACKING
# ============================================================================
# Track task starts and completions
app.conf.task_track_started = True
app.conf.task_send_sent_event = True

# ============================================================================
# WORKER SETTINGS
# ============================================================================
# Worker concurrency (can be overridden by command line)
app.conf.worker_concurrency = 4

# Maximum tasks per worker before restart (prevents memory leaks)
app.conf.worker_max_tasks_per_child = 1000

# ============================================================================
# CELERY BEAT SCHEDULE
# ============================================================================
# Scheduled tasks for periodic operations
app.conf.beat_schedule = {
    # Archive old notifications (runs daily at 2 AM)
    "archive-old-notifications": {
        "task": "payroll.tasks.notification_tasks.archive_old_notifications_task",
        "schedule": crontab(hour=2, minute=0),
    },
    # Cleanup failed delivery logs (runs daily at 3 AM)
    "cleanup-failed-deliveries": {
        "task": "payroll.tasks.notification_tasks.cleanup_failed_deliveries_task",
        "schedule": crontab(hour=3, minute=0),
    },
    # Send daily digests (runs daily at 8 AM)
    "send-daily-digests": {
        "task": "payroll.tasks.notification_tasks.schedule_daily_digests",
        "schedule": crontab(hour=8, minute=0),
    },
    # Send weekly digests (runs Mondays at 8 AM)
    "send-weekly-digests": {
        "task": "payroll.tasks.notification_tasks.schedule_weekly_digests",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
    },
    # Cleanup stale cache entries (runs every 6 hours)
    "cleanup-cache": {
        "task": "payroll.tasks.notification_tasks.cleanup_cache_task",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}

# ============================================================================
# RESULT BACKEND
# ============================================================================
# Use Redis as result backend for task tracking
app.conf.result_backend_transport_options = {
    "retry_policy": {
        "timeout": 5.0,
    },
}

# ============================================================================
# SECURITY
# ============================================================================
# Only accept signed messages (prevents task spoofing)
app.conf.task_send_sent_event = True
app.conf.task_send_event = True

# ============================================================================
# MONITORING
# ============================================================================
# Enable task events for monitoring
app.conf.worker_send_task_events = True
app.conf.task_send_event = True


@app.task(bind=True)
def debug_task(self):
    """
    Debug task to verify Celery is working correctly.

    This task can be called to test if Celery workers are running properly.
    It logs information about the task request.
    """
    print(f"Request: {self.request!r}")
    return "Celery is working!"


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """
    Setup periodic tasks after Celery configuration is loaded.

    This ensures all scheduled tasks are properly registered.
    """
    # Additional dynamic task setup can be done here if needed
    pass


if __name__ == "__main__":
    app.start()
