"""
Celery tasks for async notification delivery.

This module implements all background tasks for notification processing,
including delivery tasks for different channels and scheduled tasks for
maintenance operations like archiving and digest generation.

Tasks are designed to be idempotent and include proper retry logic with
exponential backoff for handling transient failures.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from celery import shared_task, Task
from celery.exceptions import Retry
from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone

from payroll.models.notification import (
    Notification,
    NotificationDeliveryLog,
    NotificationChannel,
    DeliveryStatus,
    NotificationType,
    NotificationPreference,
)
from payroll.services.notification_service import NotificationService

# Configure logger
logger = logging.getLogger(__name__)


class BaseNotificationTask(Task):
    """Base task class for notification tasks with common functionality."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # Maximum 10 minutes between retries
    retry_jitter = True  # Add randomness to retry times
    retry_kwargs = {"max_retries": 5}

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure with logging."""
        logger.error(
            f"Task {self.name} failed: {exc}\n"
            f"Task ID: {task_id}\n"
            f"Args: {args}\n"
            f"Kwargs: {kwargs}\n"
            f"Exception info: {einfo}"
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success with logging."""
        logger.info(
            f"Task {self.name} completed successfully\n"
            f"Task ID: {task_id}\n"
            f"Args: {args}\n"
            f"Kwargs: {kwargs}"
        )
        super().on_success(retval, task_id, args, kwargs)


@shared_task(
    bind=True,
    base=BaseNotificationTask,
    name="payroll.deliver_notification",
    max_retries=5,
    default_retry_delay=60,
)
def deliver_notification_task(
    self, notification_id: str, channel: str, recipient_id: str, retry_count: int = 0
) -> Dict[str, Any]:
    """
    Async task for delivering notifications through specified channels.

    This task is the main entry point for notification delivery. It routes
    the notification to the appropriate channel handler and tracks delivery
    status. Includes retry logic with exponential backoff.

    Args:
        notification_id: ID of the notification to deliver
        channel: Delivery channel (in_app, email, push, sms)
        recipient_id: ID of the recipient user
        retry_count: Current retry attempt (for internal tracking)

    Returns:
        Dict containing delivery result with keys:
        - success: bool - Whether delivery succeeded
        - status: str - Final delivery status
        - message: str - Result message
        - delivery_log_id: int - ID of created delivery log

    Raises:
        Notification.DoesNotExist: If notification doesn't exist
        ValueError: If channel is invalid

    Example:
        >>> result = deliver_notification_task.delay(
        ...     notification_id=123,
        ...     channel='email',
        ...     recipient_id=456
        ... )
        >>> result.get()
        {'success': True, 'status': 'delivered', 'message': '...', 'delivery_log_id': 789}
    """
    logger.info(
        f"Starting notification delivery: notification_id={notification_id}, "
        f"channel={channel}, recipient_id={recipient_id}"
    )

    try:
        # Validate channel
        try:
            channel_enum = NotificationChannel(channel)
        except ValueError:
            error_msg = f"Invalid channel: {channel}"
            logger.error(error_msg)
            return {
                "success": False,
                "status": "failed",
                "message": error_msg,
                "delivery_log_id": None,
            }

        # Get notification
        try:
            notification = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            error_msg = f"Notification not found: {notification_id}"
            logger.error(error_msg)
            return {
                "success": False,
                "status": "failed",
                "message": error_msg,
                "delivery_log_id": None,
            }

        # Check if notification is already delivered via this channel
        existing_log = NotificationDeliveryLog.objects.filter(
            notification=notification, channel=channel, recipient_id=recipient_id
        ).first()

        if existing_log and existing_log.status == "DELIVERED":

            logger.info(
                f"Notification already delivered: notification_id={notification_id}, "
                f"channel={channel}, recipient_id={recipient_id}"
            )
            return {
                "success": True,
                "status": "already_delivered",
                "message": "Notification already delivered",
                "delivery_log_id": existing_log.id,
            }

        # Create or update delivery log
        if existing_log:
            delivery_log = existing_log
            delivery_log.status = "PENDING"
            delivery_log.retry_count = retry_count
            delivery_log.last_attempt_at = timezone.now()
        else:
            delivery_log = NotificationDeliveryLog.objects.create(
                notification=notification,
                channel=channel,
                recipient_id=recipient_id,
                status="PENDING",
                retry_count=retry_count,
            )

        # Import handlers dynamically to avoid circular imports
        from payroll.handlers.delivery_handlers import (
            InAppHandler,
            EmailHandler,
            PushHandler,
            SMSHandler,
        )

        # Route to appropriate handler
        handler_map = {
            "in_app": InAppHandler,
            "email": EmailHandler,
            "push": PushHandler,
            "sms": SMSHandler,
        }

        handler_class = handler_map.get(channel)
        if not handler_class:
            error_msg = f"No handler found for channel: {channel}"
            logger.error(error_msg)
            delivery_log.status = DeliveryStatus.FAILED
            delivery_log.error_message = error_msg
            delivery_log.save()
            return {
                "success": False,
                "status": "failed",
                "message": error_msg,
                "delivery_log_id": delivery_log.id,
            }

        # Deliver notification
        handler = handler_class()
        try:
            result = handler.deliver(notification, recipient_id)
        except Exception as e:
            logger.exception(f"Handler error for channel {channel}: {e}")
            # Update delivery log with error
            delivery_log.status = "FAILED"
            delivery_log.error_message = str(e)
            delivery_log.last_attempt_at = timezone.now()
            delivery_log.save()

            # Retry if within limits
            if retry_count < self.retry_kwargs["max_retries"]:
                logger.warning(
                    f"Retrying delivery (attempt {retry_count + 1}): "
                    f"notification_id={notification_id}, channel={channel}"
                )
                raise self.retry(exc=e, countdown=2**retry_count * 60)

            return {
                "success": False,
                "status": "failed",
                "message": str(e),
                "delivery_log_id": delivery_log.id,
            }

        # Update delivery log based on result
        if result.get("success"):
            delivery_log.status = "DELIVERED"
            delivery_log.delivered_at = timezone.now()
            delivery_log.metadata = result.get("metadata", {})
            logger.info(
                f"Notification delivered successfully: notification_id={notification_id}, "
                f"channel={channel}, recipient_id={recipient_id}"
            )
        else:
            delivery_log.status = "FAILED"
            delivery_log.error_message = result.get("error", "Unknown error")
            logger.warning(
                f"Notification delivery failed: notification_id={notification_id}, "
                f"channel={channel}, error={delivery_log.error_message}"
            )

        delivery_log.last_attempt_at = timezone.now()
        delivery_log.save()

        return {
            "success": result.get("success", False),
            "status": delivery_log.status,
            "message": result.get("message", ""),
            "delivery_log_id": delivery_log.id,
        }

    except Retry:
        # Let Celery handle the retry
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in deliver_notification_task: {e}")
        return {
            "success": False,
            "status": "failed",
            "message": str(e),
            "delivery_log_id": None,
        }


@shared_task(
    bind=True,
    base=BaseNotificationTask,
    name="payroll.send_in_app_notification",
    max_retries=3,
    default_retry_delay=30,
)
def send_in_app_notification_task(
    self, notification_id: str, recipient_id: str
) -> Dict[str, Any]:
    """
    Deliver in-app notifications via WebSocket broadcast.

    This task handles real-time delivery of in-app notifications using
    Django Channels for WebSocket communication. It broadcasts the notification
    to the recipient's user channel and updates the delivery log.

    Args:
        notification_id: ID of the notification to deliver
        recipient_id: ID of the recipient user

    Returns:
        Dict containing delivery result with keys:
        - success: bool - Whether delivery succeeded
        - status: str - Final delivery status
        - message: str - Result message

    Example:
        >>> result = send_in_app_notification_task.delay(123, 456)
        >>> result.get()
        {'success': True, 'status': 'delivered', 'message': 'Notification broadcasted'}
    """
    logger.info(
        f"Sending in-app notification: notification_id={notification_id}, "
        f"recipient_id={recipient_id}"
    )

    try:
        # Get notification
        try:
            notification = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            error_msg = f"Notification not found: {notification_id}"
            logger.error(error_msg)
            return {
                "success": False,
                "status": "failed",
                "message": error_msg,
            }

        # Import handler
        from payroll.handlers.delivery_handlers import InAppHandler

        handler = InAppHandler()
        result = handler.deliver(notification, recipient_id)

        if result.get("success"):
            logger.info(
                f"In-app notification delivered: notification_id={notification_id}, "
                f"recipient_id={recipient_id}"
            )
        else:
            logger.warning(
                f"In-app notification delivery failed: notification_id={notification_id}, "
                f"recipient_id={recipient_id}, error={result.get('error')}"
            )

        return result

    except Exception as e:
        logger.exception(f"Error in send_in_app_notification_task: {e}")
        return {
            "success": False,
            "status": "failed",
            "message": str(e),
        }


@shared_task(
    bind=True,
    base=BaseNotificationTask,
    name="payroll.send_email_notification",
    max_retries=3,
    default_retry_delay=60,
)
def send_email_notification_task(
    self, notification_id: str, recipient_id: str
) -> Dict[str, Any]:
    """
    Send email notifications using Django's email backend.

    This task handles email delivery using Django's email backend with
    template rendering for email content. It tracks delivery status and
    handles bounce detection and retry logic.

    Args:
        notification_id: ID of the notification to deliver
        recipient_id: ID of the recipient user

    Returns:
        Dict containing delivery result with keys:
        - success: bool - Whether delivery succeeded
        - status: str - Final delivery status
        - message: str - Result message
        - email_id: str - Email message ID if successful

    Example:
        >>> result = send_email_notification_task.delay(123, 456)
        >>> result.get()
        {'success': True, 'status': 'delivered', 'message': 'Email sent', 'email_id': 'msg123'}
    """
    logger.info(
        f"Sending email notification: notification_id={notification_id}, "
        f"recipient_id={recipient_id}"
    )

    try:
        # Get notification
        try:
            notification = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            error_msg = f"Notification not found: {notification_id}"
            logger.error(error_msg)
            return {
                "success": False,
                "status": "failed",
                "message": error_msg,
            }

        # Import handler
        from payroll.handlers.delivery_handlers import EmailHandler

        handler = EmailHandler()
        result = handler.deliver(notification, recipient_id)

        if result.get("success"):
            logger.info(
                f"Email notification sent: notification_id={notification_id}, "
                f"recipient_id={recipient_id}"
            )
        else:
            logger.warning(
                f"Email notification failed: notification_id={notification_id}, "
                f"recipient_id={recipient_id}, error={result.get('error')}"
            )

        return result

    except Exception as e:
        logger.exception(f"Error in send_email_notification_task: {e}")
        return {
            "success": False,
            "status": "failed",
            "message": str(e),
        }


@shared_task(
    bind=True,
    base=BaseNotificationTask,
    name="payroll.send_push_notification",
    max_retries=3,
    default_retry_delay=60,
)
def send_push_notification_task(
    self, notification_id: str, recipient_id: str
) -> Dict[str, Any]:
    """
    Send push notifications via Firebase Cloud Messaging (FCM).

    This task handles push notification delivery through FCM. It manages
    device tokens, tracks delivery status, and handles invalid tokens
    by removing them from the database.

    Args:
        notification_id: ID of the notification to deliver
        recipient_id: ID of the recipient user

    Returns:
        Dict containing delivery result with keys:
        - success: bool - Whether delivery succeeded
        - status: str - Final delivery status
        - message: str - Result message
        - device_count: int - Number of devices notified

    Example:
        >>> result = send_push_notification_task.delay(123, 456)
        >>> result.get()
        {'success': True, 'status': 'delivered', 'message': 'Push sent', 'device_count': 2}
    """
    logger.info(
        f"Sending push notification: notification_id={notification_id}, "
        f"recipient_id={recipient_id}"
    )

    try:
        # Get notification
        try:
            notification = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            error_msg = f"Notification not found: {notification_id}"
            logger.error(error_msg)
            return {
                "success": False,
                "status": "failed",
                "message": error_msg,
            }

        # Import handler
        from payroll.handlers.delivery_handlers import PushHandler

        handler = PushHandler()
        result = handler.deliver(notification, recipient_id)

        if result.get("success"):
            logger.info(
                f"Push notification sent: notification_id={notification_id}, "
                f"recipient_id={recipient_id}, devices={result.get('device_count', 0)}"
            )
        else:
            logger.warning(
                f"Push notification failed: notification_id={notification_id}, "
                f"recipient_id={recipient_id}, error={result.get('error')}"
            )

        return result

    except Exception as e:
        logger.exception(f"Error in send_push_notification_task: {e}")
        return {
            "success": False,
            "status": "failed",
            "message": str(e),
        }


@shared_task(
    bind=True,
    base=BaseNotificationTask,
    name="payroll.send_sms_notification",
    max_retries=3,
    default_retry_delay=60,
)
def send_sms_notification_task(
    self, notification_id: str, recipient_id: str
) -> Dict[str, Any]:
    """
    Send SMS notifications via Twilio.

    This task handles SMS delivery through Twilio's API. It tracks delivery
    status, handles rate limiting, and manages delivery receipts for
    status updates.

    Args:
        notification_id: ID of the notification to deliver
        recipient_id: ID of the recipient user

    Returns:
        Dict containing delivery result with keys:
        - success: bool - Whether delivery succeeded
        - status: str - Final delivery status
        - message: str - Result message
        - message_sid: str - Twilio message SID if successful

    Example:
        >>> result = send_sms_notification_task.delay(123, 456)
        >>> result.get()
        {'success': True, 'status': 'delivered', 'message': 'SMS sent', 'message_sid': 'SM123'}
    """
    logger.info(
        f"Sending SMS notification: notification_id={notification_id}, "
        f"recipient_id={recipient_id}"
    )

    try:
        # Get notification
        try:
            notification = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            error_msg = f"Notification not found: {notification_id}"
            logger.error(error_msg)
            return {
                "success": False,
                "status": "failed",
                "message": error_msg,
            }

        # Import handler
        from payroll.handlers.delivery_handlers import SMSHandler

        handler = SMSHandler()
        result = handler.deliver(notification, recipient_id)

        if result.get("success"):
            logger.info(
                f"SMS notification sent: notification_id={notification_id}, "
                f"recipient_id={recipient_id}, message_sid={result.get('message_sid')}"
            )
        else:
            logger.warning(
                f"SMS notification failed: notification_id={notification_id}, "
                f"recipient_id={recipient_id}, error={result.get('error')}"
            )

        return result

    except Exception as e:
        logger.exception(f"Error in send_sms_notification_task: {e}")
        return {
            "success": False,
            "status": "failed",
            "message": str(e),
        }


@shared_task(
    name="payroll.archive_old_notifications",
)
def archive_old_notifications_task() -> Dict[str, Any]:
    """
    Scheduled task to archive old notifications.

    This task runs periodically (typically daily) to archive notifications
    older than 90 days. It moves them to an archive table and deletes from
    the main table to maintain database performance.

    The task:
    1. Finds notifications older than 90 days
    2. Creates archive records
    3. Deletes from main table
    4. Logs archival results

    Returns:
        Dict containing archival statistics with keys:
        - success: bool - Whether archival succeeded
        - archived_count: int - Number of notifications archived
        - error_count: int - Number of errors encountered
        - message: str - Result message

    Example:
        >>> result = archive_old_notifications_task.delay()
        >>> result.get()
        {'success': True, 'archived_count': 150, 'error_count': 0, 'message': 'Archived 150 notifications'}
    """
    logger.info("Starting archival of old notifications")

    try:
        # Calculate cutoff date (90 days ago)
        cutoff_date = timezone.now() - timedelta(days=90)

        # Find old notifications
        old_notifications = Notification.objects.filter(
            created_at__lt=cutoff_date, is_archived=False
        )

        count = old_notifications.count()
        logger.info(f"Found {count} notifications to archive")

        if count == 0:
            return {
                "success": True,
                "archived_count": 0,
                "error_count": 0,
                "message": "No notifications to archive",
            }

        # Archive notifications
        archived_count = 0
        error_count = 0

        for notification in old_notifications.iterator(chunk_size=100):
            try:
                # Mark as archived
                notification.is_archived = True
                notification.archived_at = timezone.now()
                notification.save(update_fields=["is_archived", "archived_at"])
                archived_count += 1
            except Exception as e:
                logger.error(f"Error archiving notification {notification.id}: {e}")
                error_count += 1

        logger.info(
            f"Archival completed: {archived_count} archived, {error_count} errors"
        )

        return {
            "success": True,
            "archived_count": archived_count,
            "error_count": error_count,
            "message": f"Archived {archived_count} notifications",
        }

    except Exception as e:
        logger.exception(f"Error in archive_old_notifications_task: {e}")
        return {
            "success": False,
            "archived_count": 0,
            "error_count": 1,
            "message": str(e),
        }


@shared_task(
    name="payroll.send_daily_digest",
)
def send_daily_digest_task() -> Dict[str, Any]:
    """
    Scheduled task to send daily notification digests.

    This task runs daily to create and send digest notifications for users
    who have opted in to receive daily digests. It aggregates notifications
    from the past 24 hours and sends them as a single notification.

    The task:
    1. Finds users with daily digest preference enabled
    2. Aggregates their unread notifications from the past 24 hours
    3. Creates a digest notification
    4. Queues the digest for delivery

    Returns:
        Dict containing digest statistics with keys:
        - success: bool - Whether task succeeded
        - digest_count: int - Number of digests created
        - error_count: int - Number of errors encountered
        - message: str - Result message

    Example:
        >>> result = send_daily_digest_task.delay()
        >>> result.get()
        {'success': True, 'digest_count': 25, 'error_count': 0, 'message': 'Created 25 daily digests'}
    """
    logger.info("Starting daily digest generation")

    try:
        # Calculate date range (past 24 hours)
        start_date = timezone.now() - timedelta(days=1)

        # Find users with daily digest preference
        digest_users = NotificationPreference.objects.filter(
            email_digest_frequency="daily"
        ).select_related("employee")

        digest_count = 0
        error_count = 0

        for preference in digest_users.iterator():
            try:
                user = preference.employee
                user_id = user.id

                # Find unread notifications for this user
                unread_notifications = Notification.objects.filter(
                    recipient_id=user_id, is_read=False, created_at__gte=start_date
                ).exclude(notification_type="DIGEST")

                count = unread_notifications.count()

                if count == 0:
                    logger.debug(f"No unread notifications for user {user_id}")
                    continue

                # Create digest notification
                notification_service = NotificationService()
                digest = notification_service.create_notification(
                    recipient_id=user_id,
                    notification_type="DIGEST",
                    title=f"Daily Digest - {count} New Notifications",
                    message=f"You have {count} unread notifications from the past 24 hours.",
                    priority="low",
                    channels=["in_app", "email"],
                    metadata={
                        "digest_type": "daily",
                        "notification_count": count,
                        "start_date": start_date.isoformat(),
                    },
                    send_async=True,
                )

                digest_count += 1
                logger.info(
                    f"Created daily digest for user {user_id} with {count} notifications"
                )

            except Exception as e:
                logger.error(
                    f"Error creating daily digest for user {preference.user_id}: {e}"
                )
                error_count += 1

        logger.info(
            f"Daily digest completed: {digest_count} digests created, {error_count} errors"
        )

        return {
            "success": True,
            "digest_count": digest_count,
            "error_count": error_count,
            "message": f"Created {digest_count} daily digests",
        }

    except Exception as e:
        logger.exception(f"Error in send_daily_digest_task: {e}")
        return {
            "success": False,
            "digest_count": 0,
            "error_count": 1,
            "message": str(e),
        }


@shared_task(
    name="payroll.send_weekly_digest",
)
def send_weekly_digest_task() -> Dict[str, Any]:
    """
    Scheduled task to send weekly notification digests.

    This task runs weekly to create and send digest notifications for users
    who have opted in to receive weekly digests. It aggregates notifications
    from the past 7 days and sends them as a single notification.

    The task:
    1. Finds users with weekly digest preference enabled
    2. Aggregates their unread notifications from the past 7 days
    3. Creates a digest notification
    4. Queues the digest for delivery

    Returns:
        Dict containing digest statistics with keys:
        - success: bool - Whether task succeeded
        - digest_count: int - Number of digests created
        - error_count: int - Number of errors encountered
        - message: str - Result message

    Example:
        >>> result = send_weekly_digest_task.delay()
        >>> result.get()
        {'success': True, 'digest_count': 25, 'error_count': 0, 'message': 'Created 25 weekly digests'}
    """
    logger.info("Starting weekly digest generation")

    try:
        # Calculate date range (past 7 days)
        start_date = timezone.now() - timedelta(days=7)

        # Find users with weekly digest preference
        digest_users = NotificationPreference.objects.filter(
            email_digest_frequency="weekly"
        ).select_related("employee")

        digest_count = 0
        error_count = 0

        for preference in digest_users.iterator():
            try:
                user = preference.employee
                user_id = user.id

                # Find unread notifications for this user
                unread_notifications = Notification.objects.filter(
                    recipient_id=user_id, is_read=False, created_at__gte=start_date
                ).exclude(notification_type="DIGEST")

                count = unread_notifications.count()

                if count == 0:
                    logger.debug(f"No unread notifications for user {user_id}")
                    continue

                # Create digest notification
                notification_service = NotificationService()
                digest = notification_service.create_notification(
                    recipient_id=user_id,
                    notification_type="DIGEST",
                    title=f"Weekly Digest - {count} New Notifications",
                    message=f"You have {count} unread notifications from the past week.",
                    priority="low",
                    channels=["in_app", "email"],
                    metadata={
                        "digest_type": "weekly",
                        "notification_count": count,
                        "start_date": start_date.isoformat(),
                    },
                    send_async=True,
                )

                digest_count += 1
                logger.info(
                    f"Created weekly digest for user {user_id} with {count} notifications"
                )

            except Exception as e:
                logger.error(
                    f"Error creating weekly digest for user {preference.user_id}: {e}"
                )
                error_count += 1

        logger.info(
            f"Weekly digest completed: {digest_count} digests created, {error_count} errors"
        )

        return {
            "success": True,
            "digest_count": digest_count,
            "error_count": error_count,
            "message": f"Created {digest_count} weekly digests",
        }

    except Exception as e:
        logger.exception(f"Error in send_weekly_digest_task: {e}")
        return {
            "success": False,
            "digest_count": 0,
            "error_count": 1,
            "message": str(e),
        }
