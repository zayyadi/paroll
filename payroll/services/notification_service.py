"""
Notification Service Layer

This module provides comprehensive services for managing notifications in the payroll system.
It includes services for:
- Creating and managing notifications
- Dispatching events to handlers
- Aggregating similar notifications
- Creating notification digests
- Managing user preferences
- Caching notification data

Based on the architecture design in plans/NOTIFICATION_SYSTEM_ARCHITECTURE.md
"""

import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Q, Count
from django.conf import settings

from payroll.models.notification import (
    Notification,
    NotificationPreference,
    NotificationDeliveryLog,
    NotificationTemplate,
)
from payroll.models.employee_profile import EmployeeProfile

logger = logging.getLogger(__name__)


class NotificationCacheService:
    """
    Service for caching notification-related data using Redis.

    Provides methods for caching notifications, unread counts, and preferences
    to reduce database load and improve performance.
    """

    CACHE_PREFIX = "notifications"
    DEFAULT_TIMEOUT = 300  # 5 minutes

    def __init__(self):
        """Initialize the cache service."""
        self.prefix = self.CACHE_PREFIX

    def _get_cache_key(self, *parts: str) -> str:
        """
        Generate a cache key from parts.

        Args:
            *parts: Variable number of strings to combine into a key

        Returns:
            str - Generated cache key
        """
        return f"{self.prefix}:{':'.join(str(p) for p in parts)}"

    def get_notifications(
        self,
        recipient_id: str,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Optional[List[Notification]]:
        """
        Get cached notifications for a recipient.

        Args:
            recipient_id: UUID of the recipient
            unread_only: Whether to only return unread notifications
            notification_type: Filter by notification type
            priority: Filter by priority
            limit: Maximum number of notifications to return
            offset: Pagination offset

        Returns:
            List of Notification objects or None if not cached
        """
        try:
            cache_key = self._get_cache_key(
                recipient_id,
                "unread" if unread_only else "all",
                notification_type or "all",
                priority or "all",
                str(limit),
                str(offset),
            )

            cached = cache.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for notifications: {cache_key}")
                return cached

            logger.debug(f"Cache miss for notifications: {cache_key}")
            return None

        except Exception as e:
            logger.error(f"Error getting cached notifications: {e}")
            return None

    def set_notifications(
        self,
        recipient_id: str,
        notifications: List[Notification],
        unread_only: bool = False,
        notification_type: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        timeout: Optional[int] = None,
    ) -> bool:
        """
        Cache notifications for a recipient.

        Args:
            recipient_id: UUID of the recipient
            notifications: List of Notification objects to cache
            unread_only: Whether these are unread-only notifications
            notification_type: Notification type filter
            priority: Priority filter
            limit: Maximum number cached
            offset: Pagination offset
            timeout: Cache timeout in seconds (uses DEFAULT_TIMEOUT if None)

        Returns:
            bool - True if cached successfully, False otherwise
        """
        try:
            cache_key = self._get_cache_key(
                recipient_id,
                "unread" if unread_only else "all",
                notification_type or "all",
                priority or "all",
                str(limit),
                str(offset),
            )

            if timeout is None:
                timeout = self.DEFAULT_TIMEOUT

            cache.set(cache_key, notifications, timeout)
            logger.debug(f"Cached notifications: {cache_key}")
            return True

        except Exception as e:
            logger.error(f"Error caching notifications: {e}")
            return False

    def get_unread_count(self, recipient_id: str) -> Optional[int]:
        """
        Get cached unread notification count for a recipient.

        Args:
            recipient_id: UUID of the recipient

        Returns:
            int - Unread count or None if not cached
        """
        try:
            cache_key = self._get_cache_key(recipient_id, "unread_count")
            cached = cache.get(cache_key)

            if cached is not None:
                logger.debug(f"Cache hit for unread count: {cache_key}")
                return cached

            logger.debug(f"Cache miss for unread count: {cache_key}")
            return None

        except Exception as e:
            logger.error(f"Error getting cached unread count: {e}")
            return None

    def set_unread_count(
        self, recipient_id: str, count: int, timeout: Optional[int] = None
    ) -> bool:
        """
        Cache unread notification count for a recipient.

        Args:
            recipient_id: UUID of the recipient
            count: Unread count to cache
            timeout: Cache timeout in seconds (uses DEFAULT_TIMEOUT if None)

        Returns:
            bool - True if cached successfully, False otherwise
        """
        try:
            cache_key = self._get_cache_key(recipient_id, "unread_count")

            if timeout is None:
                timeout = self.DEFAULT_TIMEOUT

            cache.set(cache_key, count, timeout)
            logger.debug(f"Cached unread count: {cache_key} = {count}")
            return True

        except Exception as e:
            logger.error(f"Error caching unread count: {e}")
            return False

    def get_preferences(self, recipient_id: str) -> Optional[Dict]:
        """
        Get cached notification preferences for a recipient.

        Args:
            recipient_id: UUID of the recipient

        Returns:
            dict - Preferences or None if not cached
        """
        try:
            cache_key = self._get_cache_key(recipient_id, "preferences")
            cached = cache.get(cache_key)

            if cached:
                logger.debug(f"Cache hit for preferences: {cache_key}")
                return cached

            logger.debug(f"Cache miss for preferences: {cache_key}")
            return None

        except Exception as e:
            logger.error(f"Error getting cached preferences: {e}")
            return None

    def set_preferences(
        self, recipient_id: str, preferences: Dict, timeout: Optional[int] = None
    ) -> bool:
        """
        Cache notification preferences for a recipient.

        Args:
            recipient_id: UUID of the recipient
            preferences: Preferences dictionary to cache
            timeout: Cache timeout in seconds (uses DEFAULT_TIMEOUT if None)

        Returns:
            bool - True if cached successfully, False otherwise
        """
        try:
            cache_key = self._get_cache_key(recipient_id, "preferences")

            if timeout is None:
                timeout = 3600  # 1 hour for preferences

            cache.set(cache_key, preferences, timeout)
            logger.debug(f"Cached preferences: {cache_key}")
            return True

        except Exception as e:
            logger.error(f"Error caching preferences: {e}")
            return False

    def invalidate_user_cache(self, recipient_id: str) -> bool:
        """
        Invalidate all cache entries for a specific user.

        Args:
            recipient_id: UUID of the recipient

        Returns:
            bool - True if invalidated successfully, False otherwise
        """
        try:
            # Try to use Redis pattern deletion if available
            try:
                from django_redis import get_redis_connection

                redis = get_redis_connection("default")
                pattern = f"{self.prefix}:{recipient_id}:*"
                keys = redis.keys(pattern)

                if keys:
                    redis.delete(*keys)
                    logger.debug(
                        f"Invalidated {len(keys)} cache entries for user {recipient_id}"
                    )
                    return True

            except Exception:
                # Fallback to simple key deletion
                patterns = [
                    self._get_cache_key(recipient_id, "unread_count"),
                    self._get_cache_key(recipient_id, "preferences"),
                    self._get_cache_key(recipient_id, "recent"),
                ]

                for key in patterns:
                    cache.delete(key)

                logger.debug(f"Invalidated cache entries for user {recipient_id}")
                return True

        except Exception as e:
            logger.error(f"Error invalidating user cache: {e}")
            return False

        return False

    def delete(self, key: str) -> bool:
        """
        Delete a specific cache entry.

        Args:
            key: Cache key to delete

        Returns:
            bool - True if deleted successfully, False otherwise
        """
        try:
            cache.delete(key)
            logger.debug(f"Deleted cache entry: {key}")
            return True

        except Exception as e:
            logger.error(f"Error deleting cache entry: {e}")
            return False


class PreferenceService:
    """
    Service for managing notification preferences.

    Provides methods for retrieving, updating, and validating
    user notification preferences.
    """

    def __init__(self):
        """Initialize the preference service."""
        self.cache_service = NotificationCacheService()

    def get_preferences(self, employee: EmployeeProfile) -> NotificationPreference:
        """
        Get or create notification preferences for an employee.

        Args:
            employee: EmployeeProfile instance

        Returns:
            NotificationPreference instance
        """
        try:
            # Try cache first
            cached = self.cache_service.get_preferences(str(employee.id))
            if cached:
                # Convert cached dict back to model-like object
                preference, _ = NotificationPreference.objects.get_or_create(
                    employee=employee
                )
                return preference

            # Get from database
            preference, created = NotificationPreference.objects.get_or_create(
                employee=employee
            )

            if created:
                logger.info(f"Created default preferences for employee {employee.id}")

            # Cache the preferences
            self.cache_service.set_preferences(
                str(employee.id),
                {
                    "notifications_enabled": preference.notifications_enabled,
                    "in_app_enabled": preference.in_app_enabled,
                    "email_enabled": preference.email_enabled,
                    "push_enabled": preference.push_enabled,
                    "sms_enabled": preference.sms_enabled,
                    "in_app_priority_threshold": preference.in_app_priority_threshold,
                    "email_priority_threshold": preference.email_priority_threshold,
                    "push_priority_threshold": preference.push_priority_threshold,
                    "sms_priority_threshold": preference.sms_priority_threshold,
                    "email_digest_frequency": preference.email_digest_frequency,
                    "push_digest_frequency": preference.push_digest_frequency,
                    "quiet_hours_enabled": preference.quiet_hours_enabled,
                    "quiet_hours_start": (
                        preference.quiet_hours_start.isoformat()
                        if preference.quiet_hours_start
                        else None
                    ),
                    "quiet_hours_end": (
                        preference.quiet_hours_end.isoformat()
                        if preference.quiet_hours_end
                        else None
                    ),
                    "quiet_hours_timezone": preference.quiet_hours_timezone,
                    "type_preferences": preference.type_preferences,
                },
            )

            return preference

        except Exception as e:
            logger.error(f"Error getting preferences for employee {employee.id}: {e}")
            # Return default preferences on error
            return NotificationPreference(employee=employee)

    def update_preferences(
        self, employee: EmployeeProfile, updates: Dict[str, Any]
    ) -> NotificationPreference:
        """
        Update notification preferences for an employee.

        Args:
            employee: EmployeeProfile instance
            updates: Dictionary of preference updates

        Returns:
            Updated NotificationPreference instance

        Raises:
            ValueError: If invalid preference field is provided
        """
        try:
            preference = self.get_preferences(employee)

            # Update allowed fields
            allowed_fields = [
                "notifications_enabled",
                "in_app_enabled",
                "email_enabled",
                "push_enabled",
                "sms_enabled",
                "in_app_priority_threshold",
                "email_priority_threshold",
                "push_priority_threshold",
                "sms_priority_threshold",
                "email_digest_frequency",
                "push_digest_frequency",
                "quiet_hours_enabled",
                "quiet_hours_start",
                "quiet_hours_end",
                "quiet_hours_timezone",
                "type_preferences",
                "max_notifications_per_hour",
            ]

            for field, value in updates.items():
                if field not in allowed_fields:
                    logger.warning(f"Invalid preference field: {field}")
                    continue

                setattr(preference, field, value)

            preference.save()
            logger.info(f"Updated preferences for employee {employee.id}")

            # Invalidate cache
            self.cache_service.invalidate_user_cache(str(employee.id))

            return preference

        except Exception as e:
            logger.error(f"Error updating preferences for employee {employee.id}: {e}")
            raise

    def get_type_preferences(
        self, employee: EmployeeProfile, notification_type: str
    ) -> Dict[str, bool]:
        """
        Get type-specific preferences for a notification type.

        Args:
            employee: EmployeeProfile instance
            notification_type: Notification type string

        Returns:
            Dictionary of channel preferences for the type
        """
        try:
            preference = self.get_preferences(employee)

            # Check if type-specific preference exists
            if notification_type in preference.type_preferences:
                return preference.type_preferences[notification_type]

            # Return default preferences
            return {
                "in_app": preference.in_app_enabled,
                "email": preference.email_enabled,
                "push": preference.push_enabled,
                "sms": preference.sms_enabled,
            }

        except Exception as e:
            logger.error(f"Error getting type preferences: {e}")
            # Return defaults on error
            return {"in_app": True, "email": True, "push": False, "sms": False}

    def should_send_notification(
        self,
        employee: EmployeeProfile,
        notification_type: str,
        channel: str,
        priority: str,
    ) -> bool:
        """
        Check if a notification should be sent based on preferences.

        Args:
            employee: EmployeeProfile instance
            notification_type: Type of notification
            channel: Channel name (in_app, email, push, sms)
            priority: Priority level (CRITICAL, HIGH, MEDIUM, LOW)

        Returns:
            bool - True if should send, False otherwise
        """
        try:
            preference = self.get_preferences(employee)
            return preference.should_send(notification_type, channel, priority)

        except Exception as e:
            logger.error(f"Error checking if notification should be sent: {e}")
            # Default to sending on error
            return True

    def _is_quiet_hours(self, employee: EmployeeProfile) -> bool:
        """
        Check if current time is within quiet hours for an employee.

        Args:
            employee: EmployeeProfile instance

        Returns:
            bool - True if in quiet hours, False otherwise
        """
        try:
            preference = self.get_preferences(employee)

            if not preference.quiet_hours_enabled:
                return False

            if not preference.quiet_hours_start or not preference.quiet_hours_end:
                return False

            from pytz import timezone as tz

            user_tz = tz(preference.quiet_hours_timezone)
            current_time = timezone.now().astimezone(user_tz).time()

            return (
                preference.quiet_hours_start
                <= current_time
                <= preference.quiet_hours_end
            )

        except Exception as e:
            logger.error(f"Error checking quiet hours: {e}")
            return False


class AggregationService:
    """
    Service for aggregating similar notifications.

    Groups similar notifications within time windows to reduce
    notification fatigue for users.
    """

    # Aggregation rules per notification type
    AGGREGATION_RULES = {
        "LEAVE_PENDING": {
            "enabled": True,
            "time_window": 3600,  # 1 hour
            "group_by": ["recipient"],
            "max_count": 10,
        },
        "IOU_PENDING": {
            "enabled": True,
            "time_window": 3600,  # 1 hour
            "group_by": ["recipient"],
            "max_count": 10,
        },
        "INFO": {
            "enabled": True,
            "time_window": 7200,  # 2 hours
            "group_by": ["recipient", "notification_type"],
            "max_count": 20,
        },
        "WARNING": {
            "enabled": True,
            "time_window": 3600,
            "group_by": ["recipient", "notification_type"],
            "max_count": 15,
        },
    }

    def should_aggregate(self, notification_type: str) -> bool:
        """
        Check if notification type should be aggregated.

        Args:
            notification_type: Type of notification

        Returns:
            bool - True if should aggregate, False otherwise
        """
        rule = self.AGGREGATION_RULES.get(notification_type, {})
        return rule.get("enabled", False)

    def get_aggregation_key(self, notification: Notification) -> str:
        """
        Generate aggregation key for a notification.

        Args:
            notification: Notification instance

        Returns:
            str - Aggregation key
        """
        try:
            rule = self.AGGREGATION_RULES.get(notification.notification_type, {})
            group_by = rule.get("group_by", ["recipient"])

            key_parts = []
            for field in group_by:
                if field == "recipient":
                    key_parts.append(str(notification.recipient.id))
                elif field == "notification_type":
                    key_parts.append(notification.notification_type)
                elif hasattr(notification, field):
                    key_parts.append(str(getattr(notification, field)))

            return ":".join(key_parts)

        except Exception as e:
            logger.error(f"Error generating aggregation key: {e}")
            return f"{notification.recipient.id}:{notification.notification_type}"

    def should_aggregate_notification(self, notification: Notification) -> bool:
        """
        Determine if a notification should be aggregated with existing ones.

        Args:
            notification: Notification instance

        Returns:
            bool - True if should aggregate, False otherwise
        """
        if not self.should_aggregate(notification.notification_type):
            return False

        rule = self.AGGREGATION_RULES[notification.notification_type]
        time_window = timedelta(seconds=rule["time_window"])
        cutoff_time = timezone.now() - time_window

        try:
            # Check for existing aggregatable notifications
            existing_count = (
                Notification.objects.filter(
                    recipient=notification.recipient,
                    notification_type=notification.notification_type,
                    is_aggregated=False,
                    is_deleted=False,
                    created_at__gte=cutoff_time,
                )
                .exclude(id=notification.id)
                .count()
            )

            return existing_count > 0 and existing_count < rule["max_count"]

        except Exception as e:
            logger.error(f"Error checking if notification should aggregate: {e}")
            return False

    def find_aggregatable_notifications(
        self, notification: Notification
    ) -> List[Notification]:
        """
        Find existing notifications that can be aggregated with this one.

        Args:
            notification: Notification instance

        Returns:
            List of aggregatable Notification instances
        """
        if not self.should_aggregate(notification.notification_type):
            return []

        try:
            rule = self.AGGREGATION_RULES[notification.notification_type]
            time_window = timedelta(seconds=rule["time_window"])
            cutoff_time = timezone.now() - time_window

            notifications = list(
                Notification.objects.filter(
                    recipient=notification.recipient,
                    notification_type=notification.notification_type,
                    is_aggregated=False,
                    is_deleted=False,
                    created_at__gte=cutoff_time,
                )
                .exclude(id=notification.id)
                .order_by("-created_at")[: rule["max_count"]]
            )

            return notifications

        except Exception as e:
            logger.error(f"Error finding aggregatable notifications: {e}")
            return []

    def aggregate_notifications(
        self, notifications: List[Notification]
    ) -> Optional[Notification]:
        """
        Aggregate multiple notifications into a single notification.

        Args:
            notifications: List of Notification instances to aggregate

        Returns:
            Aggregated Notification instance or None if aggregation failed
        """
        if len(notifications) < 2:
            logger.warning("Cannot aggregate less than 2 notifications")
            return None

        try:
            primary = notifications[0]

            # Create aggregated notification
            aggregated = Notification.objects.create(
                recipient=primary.recipient,
                notification_type=primary.notification_type,
                priority=primary.priority,
                title=f"{len(notifications)} {primary.notification_type.replace('_', ' ').title()}",
                message=f"You have {len(notifications)} pending {primary.notification_type.lower().replace('_', ' ')}.",
                is_aggregated=True,
                aggregation_key=self.get_aggregation_key(primary),
                aggregation_count=len(notifications),
                template_context={
                    "count": len(notifications),
                    "notification_ids": [str(n.id) for n in notifications],
                },
            )

            # Link aggregated notifications
            aggregated.aggregated_with.add(*notifications)

            # Mark original notifications as aggregated
            for notification in notifications:
                notification.is_aggregated = True
                notification.save(update_fields=["is_aggregated"])

            logger.info(
                f"Aggregated {len(notifications)} notifications into {aggregated.id}"
            )

            return aggregated

        except Exception as e:
            logger.error(f"Error aggregating notifications: {e}")
            return None

    def create_aggregated_notification(
        self, notification: Notification
    ) -> Optional[Notification]:
        """
        Create an aggregated notification from a single notification
        by finding and aggregating with similar notifications.

        Args:
            notification: Notification instance

        Returns:
            Aggregated Notification instance or None
        """
        try:
            aggregatable = self.find_aggregatable_notifications(notification)

            if aggregatable:
                all_notifications = [notification] + aggregatable
                return self.aggregate_notifications(all_notifications)

            return None

        except Exception as e:
            logger.error(f"Error creating aggregated notification: {e}")
            return None


class DigestService:
    """
    Service for creating and sending notification digests.

    Provides methods for creating daily and weekly digests
    to batch multiple notifications into a single message.
    """

    def __init__(self):
        """Initialize the digest service."""
        self.cache_service = NotificationCacheService()

    def _group_by_type(
        self, notifications: List[Notification]
    ) -> Dict[str, List[Notification]]:
        """
        Group notifications by type.

        Args:
            notifications: List of Notification instances

        Returns:
            Dictionary mapping notification types to lists of notifications
        """
        grouped = {}
        for notification in notifications:
            ntype = notification.notification_type
            if ntype not in grouped:
                grouped[ntype] = []
            grouped[ntype].append(notification)

        return grouped

    def create_daily_digest(self, recipient: EmployeeProfile) -> Optional[Notification]:
        """
        Create a daily notification digest for a recipient.

        Args:
            recipient: EmployeeProfile instance

        Returns:
            Digest Notification instance or None if no notifications to digest
        """
        return self._create_digest(recipient, "daily")

    def create_weekly_digest(
        self, recipient: EmployeeProfile
    ) -> Optional[Notification]:
        """
        Create a weekly notification digest for a recipient.

        Args:
            recipient: EmployeeProfile instance

        Returns:
            Digest Notification instance or None if no notifications to digest
        """
        return self._create_digest(recipient, "weekly")

    def _create_digest(
        self, recipient: EmployeeProfile, frequency: str = "daily"
    ) -> Optional[Notification]:
        """
        Create a digest notification for a recipient.

        Args:
            recipient: EmployeeProfile instance
            frequency: str (daily, weekly)

        Returns:
            Digest Notification instance or None
        """
        try:
            # Get time range
            if frequency == "daily":
                start_time = timezone.now() - timedelta(days=1)
            elif frequency == "weekly":
                start_time = timezone.now() - timedelta(weeks=1)
            else:
                logger.error(f"Invalid digest frequency: {frequency}")
                return None

            # Get unread notifications in range
            notifications = list(
                Notification.objects.filter(
                    recipient=recipient,
                    is_read=False,
                    is_deleted=False,
                    is_aggregated=False,
                    created_at__gte=start_time,
                ).select_related("leave_request", "iou", "payroll", "appraisal")
            )

            if not notifications:
                logger.info(
                    f"No notifications for {frequency} digest for {recipient.id}"
                )
                return None

            # Group by type
            grouped = self._group_by_type(notifications)

            # Create digest notification
            digest_notification = Notification.objects.create(
                recipient=recipient,
                notification_type="INFO",
                priority="LOW",
                title=f"{frequency.capitalize()} Notification Digest",
                message=f"You have {len(notifications)} new notifications.",
                is_aggregated=True,
                aggregation_key=f"digest:{recipient.id}:{frequency}:{timezone.now().date()}",
                aggregation_count=len(notifications),
                template_context={
                    "frequency": frequency,
                    "total_count": len(notifications),
                    "grouped": {
                        ntype: [str(n.id) for n in notifs]
                        for ntype, notifs in grouped.items()
                    },
                },
            )

            # Link notifications to digest
            digest_notification.aggregated_with.add(*notifications)

            # Mark original notifications as aggregated
            for notification in notifications:
                notification.is_aggregated = True
                notification.save(update_fields=["is_aggregated"])

            logger.info(
                f"Created {frequency} digest for {recipient.id} with {len(notifications)} notifications"
            )

            return digest_notification

        except Exception as e:
            logger.error(f"Error creating {frequency} digest: {e}")
            return None

    def send_digest(self, recipient: EmployeeProfile, frequency: str = "daily") -> bool:
        """
        Create and queue a digest notification for delivery.

        Args:
            recipient: EmployeeProfile instance
            frequency: str (daily, weekly)

        Returns:
            bool - True if digest created and queued, False otherwise
        """
        try:
            if frequency == "daily":
                digest = self.create_daily_digest(recipient)
            elif frequency == "weekly":
                digest = self.create_weekly_digest(recipient)
            else:
                logger.error(f"Invalid digest frequency: {frequency}")
                return False

            if not digest:
                return False

            # Queue for delivery
            self._queue_digest_delivery(digest)

            return True

        except Exception as e:
            logger.error(f"Error sending digest: {e}")
            return False

    def _queue_digest_delivery(self, notification: Notification) -> bool:
        """
        Queue digest notification for async delivery.

        Args:
            notification: Notification instance

        Returns:
            bool - True if queued successfully, False otherwise
        """
        try:
            # Import here to avoid circular dependency
            from payroll.tasks import deliver_notification_task

            deliver_notification_task.apply_async(
                args=[str(notification.id)],
                queue="notifications_normal",
                countdown=0,
            )

            logger.info(f"Queued digest notification {notification.id} for delivery")
            return True

        except ImportError:
            # If tasks module doesn't exist yet, log warning
            logger.warning("Celery tasks module not available, skipping queue")
            return False

        except Exception as e:
            logger.error(f"Error queuing digest delivery: {e}")
            return False


class EventDispatcher:
    """
    Dispatches notification events to appropriate handlers.

    Maintains a registry of event handlers and dispatches
    events to the correct handler based on event type.
    """

    def __init__(self):
        """Initialize the event dispatcher and register default handlers."""
        self.handlers: Dict[str, Any] = {}
        self._register_handlers()

    def _register_handlers(self):
        """Register default event handlers."""
        # Import handler classes here to avoid circular imports
        # Handlers will be registered as they are implemented
        self.handlers = {
            "leave.approved": None,  # To be implemented
            "leave.rejected": None,
            "leave.pending": None,
            "iou.approved": None,
            "iou.rejected": None,
            "iou.pending": None,
            "payslip.available": None,
            "payroll.processed": None,
            "appraisal.assigned": None,
        }

        logger.info(f"Registered {len(self.handlers)} event handlers")

    def register(self, event_type: str, handler_class: Any):
        """
        Register an event handler for a specific event type.

        Args:
            event_type: String identifier for the event type
            handler_class: Handler class to register
        """
        self.handlers[event_type] = handler_class
        logger.info(f"Registered handler for event: {event_type}")

    def dispatch(self, event_type: str, event_data: Dict[str, Any]) -> bool:
        """
        Dispatch event to appropriate handler.

        Args:
            event_type: String identifier for the event type
            event_data: Dictionary containing event data

        Returns:
            bool - True if dispatched successfully, False otherwise
        """
        try:
            if event_type not in self.handlers:
                logger.warning(f"No handler registered for event: {event_type}")
                return False
            handler_class = self.handlers.get(event_type)

            # Event type exists but no concrete handler implementation yet.
            # Keep this silent at warning level to avoid noisy logs.
            if handler_class is None:
                logger.debug("No concrete handler implemented yet for event: %s", event_type)
                return False

            # Instantiate handler and handle event
            handler = handler_class()
            handler.handle(event_data)

            logger.info(f"Dispatched event: {event_type}")
            return True

        except Exception as e:
            logger.error(f"Error dispatching event {event_type}: {e}")
            return False

    def _get_handlers(self) -> Dict[str, Any]:
        """
        Get all registered handlers.

        Returns:
            Dictionary mapping event types to handler classes
        """
        return self.handlers.copy()


class NotificationService:
    """
    Main service for creating and managing notifications.

    Provides comprehensive methods for:
    - Creating single and bulk notifications
    - Managing notification delivery
    - Tracking read/unread status
    - Retrieving notifications with filtering
    - Deleting notifications
    - Aggregating similar notifications
    """

    def __init__(self):
        """Initialize the notification service with dependent services."""
        self.preference_service = PreferenceService()
        self.aggregation_service = AggregationService()
        self.digest_service = DigestService()
        self.cache_service = NotificationCacheService()

    def send_notification(
        self,
        recipient: EmployeeProfile,
        notification_type: str,
        title: str,
        message: str,
        priority: str = "MEDIUM",
        **kwargs,
    ) -> Optional[Notification]:
        """
        Create and send a notification.

        Args:
            recipient: EmployeeProfile instance
            notification_type: str from NOTIFICATION_TYPES
            title: str notification title
            message: str notification message
            priority: str priority level (CRITICAL, HIGH, MEDIUM, LOW)
            **kwargs: Additional fields (leave_request, iou, payroll, etc.)

        Returns:
            Notification instance or None if not created
        """
        try:
            # Validate recipient
            if not recipient:
                raise ValueError("Recipient is required")

            # Get user preferences
            preferences = self.preference_service.get_preferences(recipient)

            # Check if notifications are globally disabled
            if not preferences.notifications_enabled:
                logger.info(f"Notifications disabled for employee {recipient.id}")
                return None

            # Create notification
            notification = Notification.objects.create(
                recipient=recipient,
                notification_type=notification_type,
                priority=priority,
                title=title,
                message=message,
                **kwargs,
            )

            logger.info(
                f"Created notification {notification.id} for {recipient.id}: {title}"
            )

            # Check if should aggregate
            if self.aggregation_service.should_aggregate_notification(notification):
                aggregated = self.aggregation_service.create_aggregated_notification(
                    notification
                )
                if aggregated:
                    # Invalidate cache for aggregated notification
                    self.cache_service.invalidate_user_cache(str(recipient.id))
                    return aggregated

            # Queue for delivery
            self._queue_notification(notification)

            # Invalidate cache
            self.cache_service.invalidate_user_cache(str(recipient.id))

            return notification

        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return None

    def send_bulk_notification(
        self,
        recipients: List[EmployeeProfile],
        notification_type: str,
        title: str,
        message: str,
        priority: str = "MEDIUM",
        **kwargs,
    ) -> List[Notification]:
        """
        Create notifications for multiple recipients.

        Args:
            recipients: List of EmployeeProfile instances
            notification_type: str from NOTIFICATION_TYPES
            title: str notification title
            message: str notification message
            priority: str priority level
            **kwargs: Additional fields

        Returns:
            List of created Notification instances
        """
        notifications = []

        for recipient in recipients:
            try:
                notification = self.send_notification(
                    recipient=recipient,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    priority=priority,
                    **kwargs,
                )
                if notification:
                    notifications.append(notification)

            except Exception as e:
                logger.error(f"Failed to send notification to {recipient.id}: {e}")

        logger.info(
            f"Sent bulk notification to {len(notifications)} of {len(recipients)} recipients"
        )

        return notifications

    def _should_send(
        self,
        employee: EmployeeProfile,
        notification_type: str,
        channel: str,
        priority: str,
    ) -> bool:
        """
        Check if notification should be sent via a specific channel.

        Args:
            employee: EmployeeProfile instance
            notification_type: Type of notification
            channel: Channel name (in_app, email, push, sms)
            priority: Priority level

        Returns:
            bool - True if should send, False otherwise
        """
        return self.preference_service.should_send_notification(
            employee, notification_type, channel, priority
        )

    def _queue_notification(self, notification: Notification) -> bool:
        """
        Queue notification for async delivery.

        Args:
            notification: Notification instance

        Returns:
            bool - True if queued successfully, False otherwise
        """
        try:
            # Import here to avoid circular dependency
            from payroll.tasks import deliver_notification_task

            # Select queue based on priority
            queue_map = {
                "CRITICAL": "notifications_critical",
                "HIGH": "notifications_high",
                "MEDIUM": "notifications_normal",
                "LOW": "notifications_low",
            }

            queue = queue_map.get(notification.priority, "notifications_normal")

            # Determine which channels to use based on preferences
            # For now, queue for all enabled channels
            channels = ["in_app", "email", "push", "sms"]

            # Queue task for each channel separately
            for channel in channels:
                deliver_notification_task.apply_async(
                    args=[
                        str(notification.id),
                        channel,
                        str(notification.recipient.id),
                    ],
                    queue=queue,
                    countdown=0,
                )

            logger.info(
                f"Queued notification {notification.id} for delivery on {queue} queue"
            )

            return True

        except ImportError:
            # If tasks module doesn't exist yet, log warning
            logger.warning("Celery tasks module not available, skipping queue")
            return False

        except Exception as e:
            logger.error(f"Error queuing notification: {e}")
            return False

    def mark_as_read(self, notification_id: str, recipient: EmployeeProfile) -> bool:
        """
        Mark a notification as read.

        Args:
            notification_id: UUID of the notification
            recipient: EmployeeProfile instance

        Returns:
            bool - True if marked successfully, False otherwise
        """
        try:
            notification = Notification.objects.get(
                id=notification_id, recipient=recipient, is_deleted=False
            )

            if not notification.is_read:
                notification.mark_as_read()
                logger.info(f"Marked notification {notification_id} as read")

            return True

        except Notification.DoesNotExist:
            logger.warning(f"Notification {notification_id} not found")
            return False

        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return False

    def mark_all_as_read(self, recipient: EmployeeProfile) -> int:
        """
        Mark all notifications as read for a recipient.

        Args:
            recipient: EmployeeProfile instance

        Returns:
            int - Number of notifications marked as read
        """
        try:
            updated = Notification.objects.filter(
                recipient=recipient,
                is_read=False,
                is_deleted=False,
            ).update(is_read=True, read_at=timezone.now())

            # Invalidate cache
            self.cache_service.invalidate_user_cache(str(recipient.id))

            logger.info(f"Marked {updated} notifications as read for {recipient.id}")

            return updated

        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}")
            return 0

    def get_unread_count(self, recipient: EmployeeProfile) -> int:
        """
        Get unread notification count for a recipient with caching.

        Args:
            recipient: EmployeeProfile instance

        Returns:
            int - Unread notification count
        """
        try:
            # Try cache first
            cached = self.cache_service.get_unread_count(str(recipient.id))
            if cached is not None:
                return cached

            # Get from database
            count = Notification.objects.filter(
                recipient=recipient,
                is_read=False,
                is_deleted=False,
            ).count()

            # Cache the result
            self.cache_service.set_unread_count(str(recipient.id), count)

            return count

        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
            return 0

    def get_notifications(
        self,
        recipient: EmployeeProfile,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Notification]:
        """
        Get notifications for a recipient with filtering and caching.

        Args:
            recipient: EmployeeProfile instance
            unread_only: bool filter only unread
            notification_type: str filter by type
            priority: str filter by priority
            limit: int max results
            offset: int pagination offset

        Returns:
            List of Notification instances
        """
        try:
            # Try cache first
            cached = self.cache_service.get_notifications(
                str(recipient.id),
                unread_only,
                notification_type,
                priority,
                limit,
                offset,
            )

            if cached is not None:
                return cached

            # Build query
            queryset = Notification.objects.filter(
                recipient=recipient, is_deleted=False
            )

            if unread_only:
                queryset = queryset.filter(is_read=False)

            if notification_type:
                queryset = queryset.filter(notification_type=notification_type)

            if priority:
                queryset = queryset.filter(priority=priority)

            # Apply pagination
            queryset = queryset.select_related(
                "leave_request", "iou", "payroll", "appraisal"
            )[offset : offset + limit]

            # Convert to list
            notifications = list(queryset)

            # Cache result
            self.cache_service.set_notifications(
                str(recipient.id),
                notifications,
                unread_only,
                notification_type,
                priority,
                limit,
                offset,
            )

            return notifications

        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return []

    def delete_notification(
        self, notification_id: str, recipient: EmployeeProfile
    ) -> bool:
        """
        Soft delete a notification.

        Args:
            notification_id: UUID of the notification
            recipient: EmployeeProfile instance

        Returns:
            bool - True if deleted successfully, False otherwise
        """
        try:
            notification = Notification.objects.get(
                id=notification_id, recipient=recipient
            )

            notification.soft_delete()
            logger.info(f"Deleted notification {notification_id}")

            # Invalidate cache
            self.cache_service.invalidate_user_cache(str(recipient.id))

            return True

        except Notification.DoesNotExist:
            logger.warning(f"Notification {notification_id} not found")
            return False

        except Exception as e:
            logger.error(f"Error deleting notification: {e}")
            return False

    def delete_all_notifications(self, recipient: EmployeeProfile) -> int:
        """
        Soft delete all notifications for a recipient.

        Args:
            recipient: EmployeeProfile instance

        Returns:
            int - Number of notifications deleted
        """
        try:
            updated = Notification.objects.filter(
                recipient=recipient, is_deleted=False
            ).update(is_deleted=True, deleted_at=timezone.now())

            # Invalidate cache
            self.cache_service.invalidate_user_cache(str(recipient.id))

            logger.info(f"Deleted {updated} notifications for {recipient.id}")

            return updated

        except Exception as e:
            logger.error(f"Error deleting all notifications: {e}")
            return 0

    def aggregate_notifications(
        self, recipient: EmployeeProfile
    ) -> Optional[Notification]:
        """
        Aggregate similar notifications for a recipient.

        Args:
            recipient: EmployeeProfile instance

        Returns:
            Aggregated Notification instance or None
        """
        try:
            # Get recent unaggregated notifications
            recent_notifications = list(
                Notification.objects.filter(
                    recipient=recipient,
                    is_aggregated=False,
                    is_deleted=False,
                    created_at__gte=timezone.now() - timedelta(hours=2),
                ).order_by("-created_at")[:20]
            )

            if not recent_notifications:
                return None

            # Group by type
            grouped = {}
            for notification in recent_notifications:
                ntype = notification.notification_type
                if ntype not in grouped:
                    grouped[ntype] = []
                grouped[ntype].append(notification)

            # Try to aggregate each group
            for ntype, notifications in grouped.items():
                if len(
                    notifications
                ) >= 2 and self.aggregation_service.should_aggregate(ntype):
                    aggregated = self.aggregation_service.aggregate_notifications(
                        notifications
                    )
                    if aggregated:
                        # Invalidate cache
                        self.cache_service.invalidate_user_cache(str(recipient.id))
                        return aggregated

            return None

        except Exception as e:
            logger.error(f"Error aggregating notifications: {e}")
            return None
