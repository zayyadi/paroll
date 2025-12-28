"""
Django Admin Configuration for Notification System

This module provides admin interfaces for managing notifications,
preferences, delivery logs, and templates.

Architecture Reference: plans/NOTIFICATION_SYSTEM_ARCHITECTURE.md (Section 16)
"""

from django.contrib import admin
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from payroll.models.notification import (
    Notification,
    ArchivedNotification,
    NotificationPreference,
    NotificationDeliveryLog,
    NotificationTemplate,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    Admin interface for managing notifications.

    Features:
    - List view with filters and search
    - Custom actions for bulk operations
    - Read-only delivery status display
    - Detailed view of notification data
    """

    # List display fields
    list_display = [
        "id",
        "recipient_link",
        "notification_type",
        "priority_badge",
        "title",
        "is_read",
        "delivery_status_summary",
        "is_aggregated",
        "created_at",
    ]

    # List filters
    list_filter = [
        "notification_type",
        "priority",
        "is_read",
        "is_archived",
        "is_deleted",
        "is_aggregated",
        "created_at",
        "updated_at",
    ]

    # Search fields
    search_fields = [
        "id",
        "title",
        "message",
        "recipient__user__email",
        "recipient__user__first_name",
        "recipient__user__last_name",
        "action_url",
    ]

    # Read-only fields
    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
        "delivery_status",
        "aggregation_key",
    ]

    # Date hierarchy
    date_hierarchy = "created_at"

    # Default ordering
    ordering = ["-created_at"]

    # Actions
    actions = [
        "mark_as_read",
        "mark_as_unread",
        "soft_delete",
        "archive_selected",
    ]

    # List per page
    list_per_page = 50

    # Fieldsets for detail view
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "id",
                    "recipient",
                    "notification_type",
                    "priority",
                    "title",
                    "message",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_read",
                    "read_at",
                    "is_archived",
                    "archived_at",
                    "is_deleted",
                    "deleted_at",
                )
            },
        ),
        (
            "Delivery",
            {
                "fields": (
                    "delivery_status",
                    "is_aggregated",
                    "aggregation_key",
                )
            },
        ),
        (
            "Related Objects",
            {
                "fields": (
                    "leave_request",
                    "iou",
                    "payroll",
                    "appraisal",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Action Links",
            {
                "fields": (
                    "action_url",
                    "action_label",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Template Context",
            {
                "fields": ("template_context",),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                    "expires_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def recipient_link(self, obj):
        """Display recipient as clickable link"""
        if obj.recipient:
            url = reverse(
                "admin:payroll_employeeprofile_change", args=[obj.recipient.id]
            )
            return format_html('<a href="{}">{}</a>', url, obj.recipient)
        return "-"

    recipient_link.short_description = "Recipient"
    recipient_link.admin_order_field = "recipient"

    def priority_badge(self, obj):
        """Display priority as colored badge"""
        colors = {
            "CRITICAL": "#dc3545",  # Red
            "HIGH": "#fd7e14",  # Orange
            "MEDIUM": "#0d6efd",  # Blue
            "LOW": "#6c757d",  # Gray
        }
        color = colors.get(obj.priority, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.priority,
        )

    priority_badge.short_description = "Priority"
    priority_badge.admin_order_field = "priority"

    def delivery_status_summary(self, obj):
        """Display summary of delivery status across channels"""
        if not obj.delivery_status:
            return "Not Delivered"

        status_icons = {
            "DELIVERED": "✅",
            "SENT": "📤",
            "PENDING": "⏳",
            "FAILED": "❌",
            "RETRYING": "🔄",
        }

        channels = []
        for channel, status_info in obj.delivery_status.items():
            status = status_info.get("status", "UNKNOWN")
            icon = status_icons.get(status, "❓")
            channels.append(f"{channel}: {icon}")

        return mark_safe("<br>".join(channels))

    delivery_status_summary.short_description = "Delivery Status"

    def mark_as_read(self, request, queryset):
        """Mark selected notifications as read"""
        count = queryset.update(is_read=True, read_at=timezone.now())
        self.message_user(request, f"{count} notifications marked as read.")

    mark_as_read.short_description = "Mark selected as read"

    def mark_as_unread(self, request, queryset):
        """Mark selected notifications as unread"""
        count = queryset.update(is_read=False, read_at=None)
        self.message_user(request, f"{count} notifications marked as unread.")

    mark_as_unread.short_description = "Mark selected as unread"

    def soft_delete(self, request, queryset):
        """Soft delete selected notifications"""
        count = queryset.update(is_deleted=True, deleted_at=timezone.now())
        self.message_user(request, f"{count} notifications deleted.")

    soft_delete.short_description = "Soft delete selected"

    def archive_selected(self, request, queryset):
        """Archive selected notifications"""
        count = queryset.update(is_archived=True, archived_at=timezone.now())
        self.message_user(request, f"{count} notifications archived.")

    archive_selected.short_description = "Archive selected"

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return (
            super()
            .get_queryset(request)
            .select_related(
                "recipient__user", "leave_request", "iou", "payroll", "appraisal"
            )
        )


@admin.register(ArchivedNotification)
class ArchivedNotificationAdmin(admin.ModelAdmin):
    """
    Admin interface for managing archived notifications.

    Read-only interface for viewing archived notifications.
    """

    list_display = [
        "id",
        "original_notification_id",
        "recipient_link",
        "notification_type",
        "priority",
        "title",
        "is_read",
        "archived_at",
    ]

    list_filter = [
        "notification_type",
        "priority",
        "is_read",
        "archived_at",
    ]

    search_fields = [
        "original_notification_id",
        "title",
        "message",
        "recipient__user__email",
    ]

    readonly_fields = [
        "id",
        "original_notification_id",
        "recipient",
        "notification_type",
        "priority",
        "title",
        "message",
        "is_read",
        "read_at",
        "delivery_status",
        "is_aggregated",
        "aggregation_key",
        "action_url",
        "action_label",
        "template_context",
        "created_at",
        "updated_at",
        "archived_at",
    ]

    date_hierarchy = "archived_at"
    ordering = ["-archived_at"]
    list_per_page = 50

    def has_add_permission(self, request):
        """Disable adding archived notifications"""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing archived notifications"""
        return False

    def recipient_link(self, obj):
        """Display recipient as clickable link"""
        if obj.recipient:
            url = reverse(
                "admin:payroll_employeeprofile_change", args=[obj.recipient.id]
            )
            return format_html('<a href="{}">{}</a>', url, obj.recipient)
        return "-"

    recipient_link.short_description = "Recipient"


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """
    Admin interface for managing notification preferences.

    Features:
    - View and edit user preferences
    - Filter by enabled channels
    - Bulk update preferences
    """

    list_display = [
        "employee_link",
        "notifications_enabled",
        "in_app_enabled",
        "email_enabled",
        "push_enabled",
        "sms_enabled",
        "email_digest_frequency",
        "quiet_hours_enabled",
        "updated_at",
    ]

    list_filter = [
        "notifications_enabled",
        "in_app_enabled",
        "email_enabled",
        "push_enabled",
        "sms_enabled",
        "email_digest_frequency",
        "push_digest_frequency",
        "quiet_hours_enabled",
    ]

    search_fields = [
        "employee__user__email",
        "employee__user__first_name",
        "employee__user__last_name",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
    ]

    ordering = ["-updated_at"]
    list_per_page = 50

    fieldsets = (
        ("Employee", {"fields": ("employee",)}),
        ("Global Settings", {"fields": ("notifications_enabled",)}),
        (
            "Channel Settings",
            {
                "fields": (
                    "in_app_enabled",
                    "email_enabled",
                    "push_enabled",
                    "sms_enabled",
                )
            },
        ),
        (
            "Priority Thresholds",
            {
                "fields": (
                    "in_app_priority_threshold",
                    "email_priority_threshold",
                    "push_priority_threshold",
                    "sms_priority_threshold",
                )
            },
        ),
        (
            "Digest Settings",
            {
                "fields": (
                    "email_digest_frequency",
                    "push_digest_frequency",
                )
            },
        ),
        (
            "Quiet Hours",
            {
                "fields": (
                    "quiet_hours_enabled",
                    "quiet_hours_start",
                    "quiet_hours_end",
                    "quiet_hours_timezone",
                )
            },
        ),
        (
            "Type Preferences",
            {
                "fields": ("type_preferences",),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def employee_link(self, obj):
        """Display employee as clickable link"""
        if obj.employee:
            url = reverse(
                "admin:payroll_employeeprofile_change", args=[obj.employee.id]
            )
            return format_html('<a href="{}">{}</a>', url, obj.employee)
        return "-"

    employee_link.short_description = "Employee"
    employee_link.admin_order_field = "employee"


@admin.register(NotificationDeliveryLog)
class NotificationDeliveryLogAdmin(admin.ModelAdmin):
    """
    Admin interface for managing notification delivery logs.

    Features:
    - Track delivery attempts across channels
    - Monitor failed deliveries
    - View retry information
    """

    list_display = [
        "id",
        "notification_link",
        "channel",
        "status_badge",
        "recipient_link",
        "queued_at",
        "delivered_at",
        "retry_count",
    ]

    list_filter = [
        "channel",
        "status",
        "queued_at",
        "delivered_at",
        "failed_at",
    ]

    search_fields = [
        "id",
        "notification__title",
        "notification__id",
        "recipient__user__email",
        "email_address",
        "phone_number",
        "device_token",
        "error_message",
    ]

    readonly_fields = [
        "id",
        "notification",
        "channel",
        "status",
        "recipient",
        "queued_at",
        "processing_started_at",
        "delivered_at",
        "failed_at",
        "retry_count",
        "max_retries",
        "next_retry_at",
    ]

    date_hierarchy = "queued_at"
    ordering = ["-queued_at"]
    list_per_page = 50

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "id",
                    "notification",
                    "channel",
                    "status",
                    "recipient",
                )
            },
        ),
        (
            "Delivery Details",
            {
                "fields": (
                    "queued_at",
                    "processing_started_at",
                    "delivered_at",
                    "failed_at",
                )
            },
        ),
        (
            "Retry Information",
            {
                "fields": (
                    "retry_count",
                    "max_retries",
                    "next_retry_at",
                )
            },
        ),
        (
            "Channel-Specific",
            {
                "fields": (
                    "email_address",
                    "email_message_id",
                    "device_token",
                    "platform",
                    "phone_number",
                    "sms_provider",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Error Information",
            {
                "fields": (
                    "error_message",
                    "error_code",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def notification_link(self, obj):
        """Display notification as clickable link"""
        if obj.notification:
            url = reverse(
                "admin:payroll_notification_change", args=[obj.notification.id]
            )
            return format_html('<a href="{}">{}</a>', url, obj.notification.title)
        return "-"

    notification_link.short_description = "Notification"
    notification_link.admin_order_field = "notification"

    def recipient_link(self, obj):
        """Display recipient as clickable link"""
        if obj.recipient:
            url = reverse(
                "admin:payroll_employeeprofile_change", args=[obj.recipient.id]
            )
            return format_html('<a href="{}">{}</a>', url, obj.recipient)
        return "-"

    recipient_link.short_description = "Recipient"

    def status_badge(self, obj):
        """Display status as colored badge"""
        colors = {
            "QUEUED": "#6c757d",  # Gray
            "PROCESSING": "#0dcaf0",  # Cyan
            "SENT": "#0d6efd",  # Blue
            "DELIVERED": "#198754",  # Green
            "FAILED": "#dc3545",  # Red
            "RETRYING": "#ffc107",  # Yellow
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.status,
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return (
            super()
            .get_queryset(request)
            .select_related("notification", "recipient__user")
        )


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    """
    Admin interface for managing notification templates.

    Features:
    - Create and edit notification templates
    - Version control for templates
    - Preview templates
    """

    list_display = [
        "code",
        "name",
        "channel",
        "language",
        "version",
        "is_active",
        "created_at",
    ]

    list_filter = [
        "code",
        "channel",
        "language",
        "is_active",
        "version",
        "created_at",
    ]

    search_fields = [
        "code",
        "name",
        "description",
        "subject_template",
        "body_template",
    ]

    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
    ]

    ordering = ["code", "language", "-version"]
    list_per_page = 50

    fieldsets = (
        (
            "Template Identification",
            {
                "fields": (
                    "code",
                    "name",
                    "description",
                )
            },
        ),
        (
            "Template Configuration",
            {
                "fields": (
                    "channel",
                    "language",
                    "version",
                    "is_active",
                )
            },
        ),
        (
            "Template Content",
            {
                "fields": (
                    "subject_template",
                    "body_template",
                )
            },
        ),
        (
            "Template Variables",
            {
                "fields": ("required_variables",),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["activate_templates", "deactivate_templates"]

    def activate_templates(self, request, queryset):
        """Activate selected templates"""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} templates activated.")

    activate_templates.short_description = "Activate selected templates"

    def deactivate_templates(self, request, queryset):
        """Deactivate selected templates"""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} templates deactivated.")

    deactivate_templates.short_description = "Deactivate selected templates"

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).order_by("code", "language", "-version")
