"""
Notification Services Module

This module provides comprehensive services for managing notifications in the payroll system.
All services are designed to be testable, maintainable, and follow Django best practices.

Services:
- NotificationService: Main service for creating and managing notifications
- EventDispatcher: Dispatches notification events to appropriate handlers
- AggregationService: Aggregates similar notifications to reduce fatigue
- DigestService: Creates daily and weekly notification digests
- PreferenceService: Manages user notification preferences
- NotificationCacheService: Handles caching of notification data

Usage:
    from payroll.services import (
        NotificationService,
        EventDispatcher,
        AggregationService,
        DigestService,
        PreferenceService,
        NotificationCacheService,
    )

    # Create a notification
    service = NotificationService()
    notification = service.send_notification(
        recipient=employee,
        notification_type="INFO",
        title="Test Notification",
        message="This is a test notification",
        priority="MEDIUM"
    )

    # Get unread count
    unread_count = service.get_unread_count(employee)

    # Mark as read
    service.mark_as_read(notification.id, employee)

    # Manage preferences
    preference_service = PreferenceService()
    preferences = preference_service.get_preferences(employee)
    preference_service.update_preferences(employee, {"email_enabled": False})

    # Aggregate notifications
    aggregation_service = AggregationService()
    aggregated = aggregation_service.aggregate_notifications(notifications)

    # Create digest
    digest_service = DigestService()
    digest = digest_service.create_daily_digest(employee)

    # Dispatch events
    dispatcher = EventDispatcher()
    dispatcher.dispatch("leave.approved", {"leave_request": leave_request})

    # Cache management
    cache_service = NotificationCacheService()
    cache_service.invalidate_user_cache(str(employee.id))
"""

from payroll.services.notification_service import (
    NotificationService,
    EventDispatcher,
    AggregationService,
    DigestService,
    PreferenceService,
    NotificationCacheService,
)

__all__ = [
    "NotificationService",
    "EventDispatcher",
    "AggregationService",
    "DigestService",
    "PreferenceService",
    "NotificationCacheService",
]
