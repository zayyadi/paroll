from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.utils import timezone
import uuid

from payroll.models.employee_profile import EmployeeProfile

User = get_user_model()


# Enum definitions for type safety (module-level for easy import)
class NotificationChannel(models.TextChoices):
    """Notification delivery channels."""

    IN_APP = "in_app", "In-App"
    EMAIL = "email", "Email"
    PUSH = "push", "Push Notification"
    SMS = "sms", "SMS"


class DeliveryStatus(models.TextChoices):
    """Notification delivery status."""

    QUEUED = "QUEUED", "Queued"
    PROCESSING = "PROCESSING", "Processing"
    SENT = "SENT", "Sent"
    DELIVERED = "DELIVERED", "Delivered"
    FAILED = "FAILED", "Failed"
    RETRYING = "RETRYING", "Retrying"


class NotificationType(models.TextChoices):
    """Notification types."""

    # Leave Notifications
    LEAVE_APPROVED = "LEAVE_APPROVED", "Leave Approved"
    LEAVE_REJECTED = "LEAVE_REJECTED", "Leave Rejected"
    LEAVE_PENDING = "LEAVE_PENDING", "Leave Pending"
    LEAVE_CANCELLED = "LEAVE_CANCELLED", "Leave Cancelled"
    LEAVE_REMINDER = "LEAVE_REMINDER", "Leave Reminder"
    # IOU Notifications
    IOU_APPROVED = "IOU_APPROVED", "IOU Approved"
    IOU_REJECTED = "IOU_REJECTED", "IOU Rejected"
    IOU_PENDING = "IOU_PENDING", "IOU Pending"
    IOU_DUE = "IOU_DUE", "IOU Payment Due"
    # Payroll Notifications
    PAYSLIP_AVAILABLE = "PAYSLIP_AVAILABLE", "Payslip Available"
    PAYROLL_PROCESSED = "PAYROLL_PROCESSED", "Payroll Processed"
    PAYROLL_FAILED = "PAYROLL_FAILED", "Payroll Processing Failed"
    SALARY_DISBURSED = "SALARY_DISBURSED", "Salary Disbursed"
    # Appraisal Notifications
    APPRAISAL_ASSIGNED = "APPRAISAL_ASSIGNED", "Appraisal Assigned"
    APPRAISAL_COMPLETED = "APPRAISAL_COMPLETED", "Appraisal Completed"
    APPRAISAL_REMINDER = "APPRAISAL_REMINDER", "Appraisal Reminder"
    # Profile Notifications
    PROFILE_UPDATED = "PROFILE_UPDATED", "Profile Updated"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password Changed"
    # System Notifications
    INFO = "INFO", "Information"
    WARNING = "WARNING", "Warning"
    ERROR = "ERROR", "Error"


class Notification(models.Model):
    """
    Enhanced notification model with priority, multi-channel support,
    delivery tracking, aggregation, and soft delete capabilities.
    """

    # Priority Levels
    PRIORITY_CHOICES = [
        ("CRITICAL", "Critical"),
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
    ]

    # Notification Types (expanded from 12 to 20)
    NOTIFICATION_TYPES = [
        # Leave Notifications
        ("LEAVE_APPROVED", "Leave Approved"),
        ("LEAVE_REJECTED", "Leave Rejected"),
        ("LEAVE_PENDING", "Leave Pending"),
        ("LEAVE_CANCELLED", "Leave Cancelled"),
        ("LEAVE_REMINDER", "Leave Reminder"),
        # IOU Notifications
        ("IOU_APPROVED", "IOU Approved"),
        ("IOU_REJECTED", "IOU Rejected"),
        ("IOU_PENDING", "IOU Pending"),
        ("IOU_DUE", "IOU Payment Due"),
        # Payroll Notifications
        ("PAYSLIP_AVAILABLE", "Payslip Available"),
        ("PAYROLL_PROCESSED", "Payroll Processed"),
        ("PAYROLL_FAILED", "Payroll Processing Failed"),
        ("SALARY_DISBURSED", "Salary Disbursed"),
        # Appraisal Notifications
        ("APPRAISAL_ASSIGNED", "Appraisal Assigned"),
        ("APPRAISAL_COMPLETED", "Appraisal Completed"),
        ("APPRAISAL_REMINDER", "Appraisal Reminder"),
        # Profile Notifications
        ("PROFILE_UPDATED", "Profile Updated"),
        ("PASSWORD_CHANGED", "Password Changed"),
        # System Notifications
        ("INFO", "Information"),
        ("WARNING", "Warning"),
        ("ERROR", "Error"),
    ]

    # Core Fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )

    notification_type = models.CharField(
        max_length=50, choices=NOTIFICATION_TYPES, db_index=True
    )

    priority = models.CharField(
        max_length=20, choices=PRIORITY_CHOICES, default="MEDIUM", db_index=True
    )

    title = models.CharField(max_length=255)
    message = models.TextField()

    # Read Status
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # Delivery Tracking (per channel)
    delivery_status = models.JSONField(default=dict, blank=True)
    # Example: {
    #   "in_app": {"status": "DELIVERED", "at": "2025-12-27T10:00:00Z"},
    #   "email": {"status": "SENT", "at": "2025-12-27T10:00:01Z", "message_id": "abc123"},
    #   "push": {"status": "FAILED", "error": "Device token expired", "retries": 3},
    #   "sms": {"status": "PENDING"}
    # }

    # Aggregation
    is_aggregated = models.BooleanField(default=False)
    aggregated_with = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="aggregated_notifications"
    )
    aggregation_key = models.CharField(max_length=255, blank=True, db_index=True)
    aggregation_count = models.IntegerField(default=0)

    # Generic Foreign Key for related objects (replaces multiple FKs)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    object_id = models.UUIDField(null=True, blank=True)
    related_object = GenericForeignKey("content_type", "object_id")

    # Maintain backward compatibility with existing FKs
    leave_request = models.ForeignKey(
        "LeaveRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    iou = models.ForeignKey(
        "IOU",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    payroll = models.ForeignKey(
        "PayT",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    appraisal = models.ForeignKey(
        "Appraisal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    # Action Links
    action_url = models.CharField(max_length=500, blank=True, null=True)
    action_label = models.CharField(max_length=100, blank=True, null=True)

    # Template Context (for dynamic rendering)
    template_context = models.JSONField(default=dict, blank=True)
    # Example: {
    #   "employee_name": "John Doe",
    #   "leave_dates": "Jan 1-5, 2025",
    #   "amount": 50000
    # }

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Soft Delete
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Archiving
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    # Additional metadata field for flexibility
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["notification_type"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["recipient", "priority"]),
            models.Index(fields=["recipient", "is_archived"]),
            models.Index(fields=["aggregation_key"]),
            models.Index(fields=["is_deleted"]),
            models.Index(fields=["expires_at"]),
            # Composite indexes for common queries
            models.Index(fields=["recipient", "-created_at", "is_read"]),
            models.Index(fields=["recipient", "priority", "-created_at"]),
            models.Index(fields=["recipient", "is_deleted", "-created_at"]),
        ]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return f"{self.recipient} - {self.title}"

    def mark_as_read(self):
        """
        Mark notification as read and update cache.
        """
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])
            self._invalidate_cache()

    def mark_as_unread(self):
        """
        Mark notification as unread and update cache.
        """
        self.is_read = False
        self.read_at = None
        self.save(update_fields=["is_read", "read_at"])
        self._invalidate_cache()

    def mark_as_delivered(self, channel="in_app"):
        """
        Mark notification as delivered via specific channel.

        Args:
            channel: str - Channel name (in_app, email, push, sms)
        """
        self.update_delivery_status(channel, "DELIVERED")

    def soft_delete(self):
        """
        Soft delete notification without removing from database.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])
        self._invalidate_cache()

    def update_delivery_status(self, channel, status, **metadata):
        """
        Update delivery status for a specific channel.

        Args:
            channel: str - Channel name (in_app, email, push, sms)
            status: str - Status (PENDING, SENT, DELIVERED, FAILED, RETRYING)
            **metadata: Additional metadata (message_id, error, retries, etc.)
        """
        if self.delivery_status is None:
            self.delivery_status = {}

        self.delivery_status[channel] = {
            "status": status,
            "at": timezone.now().isoformat(),
            **metadata,
        }
        self.save(update_fields=["delivery_status"])

    def is_expired(self):
        """
        Check if notification has expired.

        Returns:
            bool - True if expired, False otherwise
        """
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    def _invalidate_cache(self):
        """
        Invalidate related cache entries.
        """
        cache_key_patterns = [
            f"notifications:{self.recipient.id}:unread_count",
            f"notifications:{self.recipient.id}:recent",
        ]
        for pattern in cache_key_patterns:
            cache.delete(pattern)

    @property
    def icon_class(self):
        """
        Return Lucide icon class based on notification type.
        """
        icon_map = {
            "LEAVE_APPROVED": "check-circle",
            "LEAVE_REJECTED": "x-circle",
            "LEAVE_PENDING": "clock",
            "LEAVE_CANCELLED": "ban",
            "LEAVE_REMINDER": "alert-circle",
            "IOU_APPROVED": "dollar-sign",
            "IOU_REJECTED": "x-circle",
            "IOU_PENDING": "clock",
            "IOU_DUE": "alert-triangle",
            "PAYSLIP_AVAILABLE": "file-text",
            "PAYROLL_PROCESSED": "banknote",
            "PAYROLL_FAILED": "alert-octagon",
            "SALARY_DISBURSED": "credit-card",
            "APPRAISAL_ASSIGNED": "star",
            "APPRAISAL_COMPLETED": "award",
            "APPRAISAL_REMINDER": "bell",
            "PROFILE_UPDATED": "user",
            "PASSWORD_CHANGED": "lock",
            "INFO": "bell",
            "WARNING": "alert-triangle",
            "ERROR": "alert-octagon",
        }
        return icon_map.get(self.notification_type, "bell")

    @property
    def color_class(self):
        """
        Return color class based on priority.
        """
        color_map = {
            "CRITICAL": "red",
            "HIGH": "orange",
            "MEDIUM": "blue",
            "LOW": "gray",
        }
        return color_map.get(self.priority, "blue")


class NotificationPreference(models.Model):
    """
    Global and per-type notification preferences for each user.
    Supports granular control over notification delivery across channels.
    """

    CHANNEL_CHOICES = [
        ("in_app", "In-App"),
        ("email", "Email"),
        ("push", "Push Notification"),
        ("sms", "SMS"),
    ]

    PRIORITY_THRESHOLD_CHOICES = [
        ("CRITICAL", "Critical Only"),
        ("HIGH", "High and Above"),
        ("MEDIUM", "Medium and Above"),
        ("LOW", "All Notifications"),
    ]

    DIGEST_FREQUENCY_CHOICES = [
        ("immediate", "Immediate"),
        ("hourly", "Hourly Digest"),
        ("daily", "Daily Digest"),
        ("weekly", "Weekly Digest"),
    ]

    # Core Fields
    employee = models.OneToOneField(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )

    # Global Settings
    notifications_enabled = models.BooleanField(default=True)

    # Per-Channel Settings
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)
    sms_enabled = models.BooleanField(default=False)

    # Priority Thresholds per Channel
    in_app_priority_threshold = models.CharField(
        max_length=20, choices=PRIORITY_THRESHOLD_CHOICES, default="LOW"
    )
    email_priority_threshold = models.CharField(
        max_length=20, choices=PRIORITY_THRESHOLD_CHOICES, default="HIGH"
    )
    push_priority_threshold = models.CharField(
        max_length=20, choices=PRIORITY_THRESHOLD_CHOICES, default="HIGH"
    )
    sms_priority_threshold = models.CharField(
        max_length=20, choices=PRIORITY_THRESHOLD_CHOICES, default="CRITICAL"
    )

    # Digest Settings
    email_digest_frequency = models.CharField(
        max_length=20, choices=DIGEST_FREQUENCY_CHOICES, default="immediate"
    )
    push_digest_frequency = models.CharField(
        max_length=20, choices=DIGEST_FREQUENCY_CHOICES, default="immediate"
    )

    # Quiet Hours (no notifications during this period)
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    quiet_hours_timezone = models.CharField(max_length=50, default="UTC")

    # Frequency Limits
    max_notifications_per_hour = models.IntegerField(
        default=100, help_text="Maximum notifications per hour per channel"
    )

    # Per-Type Preferences (JSON for flexibility)
    type_preferences = models.JSONField(default=dict, blank=True)
    # Example: {
    #   "LEAVE_APPROVED": {"in_app": True, "email": True, "push": False, "sms": False},
    #   "PAYSLIP_AVAILABLE": {"in_app": True, "email": True, "push": True, "sms": False},
    #   "INFO": {"in_app": True, "email": False, "push": False, "sms": False}
    # }

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        return f"Preferences for {self.employee}"

    def should_send(self, notification_type, channel, priority):
        """
        Determine if a notification should be sent via a specific channel.

        Args:
            notification_type: str - Type of notification
            channel: str - Channel name (in_app, email, push, sms)
            priority: str - Priority level (CRITICAL, HIGH, MEDIUM, LOW)

        Returns:
            bool - True if should send, False otherwise
        """
        # Check if notifications are globally disabled
        if not self.notifications_enabled:
            return False

        # Check if channel is enabled
        channel_enabled = getattr(self, f"{channel}_enabled", False)
        if not channel_enabled:
            return False

        # Check priority threshold
        threshold = getattr(self, f"{channel}_priority_threshold", "LOW")
        priority_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        if priority_order.index(priority) < priority_order.index(threshold):
            return False

        # Check type-specific preference
        if notification_type in self.type_preferences:
            type_pref = self.type_preferences[notification_type]
            if not type_pref.get(channel, True):
                return False

        # Check quiet hours
        if self.quiet_hours_enabled and self.quiet_hours_start and self.quiet_hours_end:
            from pytz import timezone as tz

            user_tz = tz(self.quiet_hours_timezone)
            current_time = timezone.now().astimezone(user_tz).time()

            if self.quiet_hours_start <= current_time <= self.quiet_hours_end:
                # Only allow critical notifications during quiet hours
                if priority != "CRITICAL":
                    return False

        return True

    def get_digest_frequency(self, channel):
        """
        Get digest frequency for a specific channel.

        Args:
            channel: str - Channel name

        Returns:
            str - Digest frequency (immediate, hourly, daily, weekly)
        """
        return getattr(self, f"{channel}_digest_frequency", "immediate")


class NotificationTypePreference(models.Model):
    """
    Per-notification-type preferences for granular control.
    Allows users to customize settings for specific notification types.
    """

    CHANNEL_CHOICES = [
        ("in_app", "In-App"),
        ("email", "Email"),
        ("push", "Push Notification"),
        ("sms", "SMS"),
    ]

    PRIORITY_CHOICES = [
        ("CRITICAL", "Critical"),
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
    ]

    # Core Fields
    employee = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="type_preferences"
    )

    notification_type = models.CharField(
        max_length=50, choices=Notification.NOTIFICATION_TYPES
    )

    # Per-Channel Settings
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)
    sms_enabled = models.BooleanField(default=False)

    # Priority Threshold (minimum priority to receive this type)
    min_priority = models.CharField(
        max_length=20, choices=PRIORITY_CHOICES, default="LOW"
    )

    # Custom settings
    custom_title = models.CharField(max_length=255, blank=True, null=True)
    custom_message = models.TextField(blank=True, null=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["employee", "notification_type"]]
        verbose_name = "Notification Type Preference"
        verbose_name_plural = "Notification Type Preferences"
        ordering = ["employee", "notification_type"]

    def __str__(self):
        return f"{self.employee} - {self.get_notification_type_display()}"

    def should_send(self, channel, priority):
        """
        Determine if this notification type should be sent via a specific channel.

        Args:
            channel: str - Channel name
            priority: str - Priority level

        Returns:
            bool - True if should send, False otherwise
        """
        # Check if channel is enabled
        channel_enabled = getattr(self, f"{channel}_enabled", False)
        if not channel_enabled:
            return False

        # Check priority threshold
        priority_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        if priority_order.index(priority) < priority_order.index(self.min_priority):
            return False

        return True


class NotificationDeliveryLog(models.Model):
    """
    Log of all notification delivery attempts for monitoring and debugging.
    Tracks delivery status per channel with retry information and error details.
    """

    STATUS_CHOICES = [
        ("QUEUED", "Queued"),
        ("PROCESSING", "Processing"),
        ("SENT", "Sent"),
        ("DELIVERED", "Delivered"),
        ("FAILED", "Failed"),
        ("RETRYING", "Retrying"),
    ]

    CHANNEL_CHOICES = [
        ("in_app", "In-App"),
        ("email", "Email"),
        ("push", "Push Notification"),
        ("sms", "SMS"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="delivery_logs"
    )

    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, db_index=True)

    # Delivery Details
    recipient = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="delivery_logs"
    )

    # Email-specific
    email_address = models.EmailField(blank=True, null=True)
    email_message_id = models.CharField(max_length=255, blank=True, null=True)

    # Push-specific
    device_token = models.CharField(max_length=255, blank=True, null=True)
    platform = models.CharField(max_length=20, blank=True, null=True)

    # SMS-specific
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    sms_provider = models.CharField(max_length=50, blank=True, null=True)
    sms_message_id = models.CharField(max_length=255, blank=True, null=True)

    # Retry Information
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    next_retry_at = models.DateTimeField(null=True, blank=True)

    # Error Information
    error_message = models.TextField(blank=True, null=True)
    error_code = models.CharField(max_length=50, blank=True, null=True)

    # Timing
    queued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    # Additional metadata
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-queued_at"]
        indexes = [
            models.Index(fields=["notification", "channel"]),
            models.Index(fields=["status", "queued_at"]),
            models.Index(fields=["recipient", "queued_at"]),
            models.Index(fields=["channel", "status"]),
            models.Index(fields=["retry_count"]),
        ]
        verbose_name = "Notification Delivery Log"
        verbose_name_plural = "Notification Delivery Logs"

    def __str__(self):
        return f"{self.notification.title} - {self.channel} - {self.status}"

    def mark_delivered(self):
        """Mark delivery as successful."""
        self.status = "DELIVERED"
        self.delivered_at = timezone.now()
        self.save(update_fields=["status", "delivered_at"])

    def mark_failed(self, error_message=None, error_code=None):
        """Mark delivery as failed."""
        self.status = "FAILED"
        self.failed_at = timezone.now()
        if error_message:
            self.error_message = error_message
        if error_code:
            self.error_code = error_code
        self.save(update_fields=["status", "failed_at", "error_message", "error_code"])

    def increment_retry(self):
        """Increment retry count and schedule next retry."""
        from datetime import timedelta

        self.retry_count += 1
        if self.retry_count < self.max_retries:
            self.status = "RETRYING"
            # Exponential backoff: 2^retry_count minutes
            delay_minutes = 2**self.retry_count
            self.next_retry_at = timezone.now() + timedelta(minutes=delay_minutes)
        else:
            self.status = "FAILED"
            self.failed_at = timezone.now()

        self.save(update_fields=["retry_count", "status", "next_retry_at", "failed_at"])


class ArchivedNotification(models.Model):
    """
    Archived notifications for long-term storage and compliance.
    Mirrors the Notification model but in a separate table for performance.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_notification_id = models.UUIDField()

    recipient = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="archived_notifications"
    )

    notification_type = models.CharField(max_length=50)
    priority = models.CharField(max_length=20)

    title = models.CharField(max_length=255)
    message = models.TextField()

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    delivery_status = models.JSONField(default=dict, blank=True)
    is_aggregated = models.BooleanField(default=False)
    aggregation_key = models.CharField(max_length=255, blank=True)
    aggregation_count = models.IntegerField(default=0)

    action_url = models.CharField(max_length=500, blank=True, null=True)
    action_label = models.CharField(max_length=100, blank=True, null=True)

    template_context = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField()
    archived_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Store related object IDs for reference
    leave_request_id = models.UUIDField(null=True, blank=True)
    iou_id = models.UUIDField(null=True, blank=True)
    payroll_id = models.UUIDField(null=True, blank=True)
    appraisal_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-archived_at"]
        indexes = [
            models.Index(fields=["recipient", "archived_at"]),
            models.Index(fields=["archived_at"]),
            models.Index(fields=["notification_type"]),
            models.Index(fields=["original_notification_id"]),
        ]
        verbose_name = "Archived Notification"
        verbose_name_plural = "Archived Notifications"

    def __str__(self):
        return f"Archived: {self.recipient} - {self.title}"


class NotificationTemplate(models.Model):
    """
    Templates for notification messages with support for multiple languages and channels.
    Enables dynamic message generation with variable substitution.
    """

    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("push", "Push Notification"),
        ("sms", "SMS"),
        ("in_app", "In-App"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Template Identification
    code = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Template Content
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    language = models.CharField(max_length=10, default="en")

    subject_template = models.CharField(max_length=255, blank=True, null=True)
    body_template = models.TextField()

    # Required Variables (for validation)
    required_variables = models.JSONField(default=list, blank=True)
    # Example: ["employee_name", "leave_dates", "amount"]

    # Metadata
    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["code", "channel", "language", "version"]]
        ordering = ["code", "language", "-version"]
        indexes = [
            models.Index(fields=["code", "language"]),
            models.Index(fields=["channel", "is_active"]),
        ]
        verbose_name = "Notification Template"
        verbose_name_plural = "Notification Templates"

    def __str__(self):
        return f"{self.code} - {self.channel} - {self.language} v{self.version}"

    def render(self, context):
        """
        Render template with provided context.

        Args:
            context: dict - Context variables for template rendering

        Returns:
            str - Rendered template
        """
        from django.template import Template, Context as DjangoContext

        template = Template(self.body_template)
        return template.render(DjangoContext(context))

    def render_subject(self, context):
        """
        Render subject template with provided context.

        Args:
            context: dict - Context variables for template rendering

        Returns:
            str - Rendered subject or None if no subject template
        """
        if not self.subject_template:
            return None

        from django.template import Template, Context as DjangoContext

        template = Template(self.subject_template)
        return template.render(DjangoContext(context))

    def validate_variables(self, context):
        """
        Validate that all required variables are present in context.

        Args:
            context: dict - Context variables to validate

        Returns:
            tuple - (is_valid, missing_variables)
        """
        missing = []
        for var in self.required_variables:
            if var not in context:
                missing.append(var)

        return (len(missing) == 0, missing)
