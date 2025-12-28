"""
Celery tasks for the payroll application.

This module exports all async tasks for notification delivery and other
background processing operations.
"""

from payroll.tasks.notification_tasks import (
    deliver_notification_task,
    send_in_app_notification_task,
    send_email_notification_task,
    send_push_notification_task,
    send_sms_notification_task,
    archive_old_notifications_task,
    send_daily_digest_task,
    send_weekly_digest_task,
)

__all__ = [
    "deliver_notification_task",
    "send_in_app_notification_task",
    "send_email_notification_task",
    "send_push_notification_task",
    "send_sms_notification_task",
    "archive_old_notifications_task",
    "send_daily_digest_task",
    "send_weekly_digest_task",
]
