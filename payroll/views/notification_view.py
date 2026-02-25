"""
Views for handling notifications using the new NotificationService layer.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db.models import Q

from payroll import models
from payroll.models import Notification, NotificationPreference
from payroll.models.employee_profile import EmployeeProfile
from payroll.services.notification_service import (
    NotificationService,
    PreferenceService,
    DigestService,
    AggregationService,
)


@login_required
def notification_list(request):
    """
    View to display all notifications for the logged-in user.

    Uses NotificationService.get_notifications() for data retrieval with caching.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize service
    service = NotificationService()

    # Get filter parameters
    filter_type = request.GET.get("type", "all")
    read_status = request.GET.get("read", "all")
    priority_filter = request.GET.get("priority", None)

    # Convert read status to unread_only flag
    unread_only = read_status == "unread"

    # Get notifications using service
    notifications = service.get_notifications(
        recipient=employee_profile,
        unread_only=unread_only,
        notification_type=filter_type if filter_type != "all" else None,
        priority=priority_filter,
        limit=50,
        offset=0,
    )

    # Get unread count using service
    unread_count = service.get_unread_count(employee_profile)

    context = {
        "notifications": notifications,
        "unread_count": unread_count,
        "filter_type": filter_type,
        "read_status": read_status,
        "priority_filter": priority_filter,
    }

    return render(request, "notifications/notification_list.html", context)


@login_required
def notification_dropdown(request):
    """
    View to render notification dropdown (for header).

    Uses NotificationService.get_notifications() for recent notifications.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize service
    service = NotificationService()

    # Get recent unread notifications (max 5)
    notifications = service.get_notifications(
        recipient=employee_profile,
        unread_only=False,  # Get all recent, not just unread
        limit=5,
        offset=0,
    )

    # Get unread count using service
    unread_count = service.get_unread_count(employee_profile)

    context = {
        "notifications": notifications,
        "unread_count": unread_count,
    }

    return render(request, "notifications/notification_dropdown.html", context)


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """
    Mark a specific notification as read.

    Uses NotificationService.mark_as_read() for updating read status.
    Returns JSON response for AJAX requests.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize service
    service = NotificationService()

    # Mark as read using service
    success = service.mark_as_read(str(notification_id), employee_profile)

    if success:
        # Get updated unread count
        unread_count = service.get_unread_count(employee_profile)
        return JsonResponse({"success": True, "unread_count": unread_count})
    else:
        return JsonResponse(
            {"error": "Notification not found or already read"}, status=404
        )


@login_required
@require_POST
def mark_notification_unread(request, notification_id):
    """
    Mark a specific notification as unread.

    Uses direct model access for marking as unread (not in service yet).
    Returns JSON response for AJAX requests.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    notification = get_object_or_404(
        Notification, id=notification_id, recipient=employee_profile
    )

    notification.mark_as_unread()

    # Get updated unread count
    service = NotificationService()
    unread_count = service.get_unread_count(employee_profile)

    return JsonResponse({"success": True, "unread_count": unread_count})


@login_required
@require_POST
def mark_all_read(request):
    """
    Mark all notifications as read for the current user.

    Uses NotificationService.mark_all_as_read() for bulk update.
    Returns JSON response for AJAX requests.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize service
    service = NotificationService()

    # Mark all as read using service
    updated_count = service.mark_all_as_read(employee_profile)

    return JsonResponse(
        {"success": True, "updated_count": updated_count, "unread_count": 0}
    )


@login_required
@require_POST
def delete_notification(request, notification_id):
    """
    Delete a specific notification (soft delete).

    Uses NotificationService.delete_notification() for soft deletion.
    Returns JSON response for AJAX requests.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize service
    service = NotificationService()

    # Delete notification using service
    success = service.delete_notification(str(notification_id), employee_profile)

    if success:
        # Get updated unread count
        unread_count = service.get_unread_count(employee_profile)
        return JsonResponse({"success": True, "unread_count": unread_count})
    else:
        return JsonResponse({"error": "Notification not found"}, status=404)


@login_required
def notification_count(request):
    """
    Get the count of unread notifications.

    Uses NotificationService.get_unread_count() with caching.
    Returns JSON response for AJAX requests.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"unread_count": 0})

    # Initialize service
    service = NotificationService()

    # Get unread count using service
    unread_count = service.get_unread_count(employee_profile)

    return JsonResponse({"unread_count": unread_count})


@login_required
def notification_detail(request, notification_id):
    """
    View notification details and mark as read.

    Uses NotificationService.mark_as_read() when viewing details.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    notification = get_object_or_404(
        Notification, id=notification_id, recipient=employee_profile
    )

    # Mark as read when viewing details using service
    service = NotificationService()
    service.mark_as_read(str(notification_id), employee_profile)

    context = {
        "notification": notification,
    }

    return render(request, "notifications/notification_detail.html", context)


# ==================== PREFERENCES MANAGEMENT VIEWS ====================


@login_required
def notification_preferences(request):
    """
    View for managing global notification preferences.

    GET: Display current preferences
    POST: Update preferences

    Uses PreferenceService for preference management.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize preference service
    preference_service = PreferenceService()

    if request.method == "POST":
        # Get form data
        updates = {
            "notifications_enabled": request.POST.get(
                "notifications_enabled", "true"
            ).lower()
            == "true",
            "in_app_enabled": request.POST.get("in_app_enabled", "true").lower()
            == "true",
            "email_enabled": request.POST.get("email_enabled", "true").lower()
            == "true",
            "push_enabled": request.POST.get("push_enabled", "false").lower() == "true",
            "sms_enabled": request.POST.get("sms_enabled", "false").lower() == "true",
            "in_app_priority_threshold": request.POST.get(
                "in_app_priority_threshold", "LOW"
            ),
            "email_priority_threshold": request.POST.get(
                "email_priority_threshold", "HIGH"
            ),
            "push_priority_threshold": request.POST.get(
                "push_priority_threshold", "HIGH"
            ),
            "sms_priority_threshold": request.POST.get(
                "sms_priority_threshold", "CRITICAL"
            ),
            "email_digest_frequency": request.POST.get(
                "email_digest_frequency", "immediate"
            ),
            "push_digest_frequency": request.POST.get(
                "push_digest_frequency", "immediate"
            ),
            "quiet_hours_enabled": request.POST.get(
                "quiet_hours_enabled", "false"
            ).lower()
            == "true",
        }

        # Handle quiet hours times
        quiet_hours_start = request.POST.get("quiet_hours_start")
        quiet_hours_end = request.POST.get("quiet_hours_end")

        if quiet_hours_start:
            from datetime import datetime

            try:
                updates["quiet_hours_start"] = datetime.strptime(
                    quiet_hours_start, "%H:%M"
                ).time()
            except ValueError:
                pass

        if quiet_hours_end:
            from datetime import datetime

            try:
                updates["quiet_hours_end"] = datetime.strptime(
                    quiet_hours_end, "%H:%M"
                ).time()
            except ValueError:
                pass

        # Update preferences
        try:
            preference_service.update_preferences(employee_profile, updates)
            return JsonResponse(
                {"success": True, "message": "Preferences updated successfully"}
            )
        except Exception as e:
            return JsonResponse(
                {"error": f"Failed to update preferences: {str(e)}"}, status=400
            )

    # GET request - display current preferences
    preferences = preference_service.get_preferences(employee_profile)

    context = {
        "preferences": preferences,
    }

    return render(request, "notifications/preferences.html", context)


@login_required
def notification_type_preferences(request, notification_type):
    """
    View for managing type-specific notification preferences.

    GET: Display current type preferences
    POST: Update type preferences

    Uses PreferenceService for preference management.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize preference service
    preference_service = PreferenceService()

    if request.method == "POST":
        # Get type-specific preferences from form
        in_app_enabled = request.POST.get("in_app_enabled", "true").lower() == "true"
        email_enabled = request.POST.get("email_enabled", "true").lower() == "true"
        push_enabled = request.POST.get("push_enabled", "false").lower() == "true"
        sms_enabled = request.POST.get("sms_enabled", "false").lower() == "true"

        # Get current preferences
        preferences = preference_service.get_preferences(employee_profile)

        # Update type preferences
        type_preferences = preferences.type_preferences or {}
        type_preferences[notification_type] = {
            "in_app": in_app_enabled,
            "email": email_enabled,
            "push": push_enabled,
            "sms": sms_enabled,
        }

        # Save updated preferences
        try:
            preference_service.update_preferences(
                employee_profile, {"type_preferences": type_preferences}
            )
            return JsonResponse(
                {
                    "success": True,
                    "message": f"Preferences for {notification_type} updated successfully",
                }
            )
        except Exception as e:
            return JsonResponse(
                {"error": f"Failed to update preferences: {str(e)}"}, status=400
            )

    # GET request - display current type preferences
    type_prefs = preference_service.get_type_preferences(
        employee_profile, notification_type
    )

    context = {
        "notification_type": notification_type,
        "type_preferences": type_prefs,
    }

    return render(request, "notifications/type_preferences.html", context)


# ==================== AGGREGATION VIEWS ====================


@login_required
def aggregated_notifications(request):
    """
    View to display aggregated notifications.

    Shows notifications that have been grouped together
    to reduce notification fatigue.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize service
    service = NotificationService()

    # Get aggregated notifications
    notifications = (
        Notification.objects.filter(
            recipient=employee_profile, is_aggregated=True, is_deleted=False
        )
        .select_related("leave_request", "iou", "payroll", "appraisal")
        .order_by("-created_at")[:50]
    )

    # Get unread count
    unread_count = service.get_unread_count(employee_profile)

    context = {
        "notifications": notifications,
        "unread_count": unread_count,
    }

    return render(request, "notifications/aggregated_notifications.html", context)


@login_required
@require_POST
def expand_aggregated_notification(request, notification_id):
    """
    Expand an aggregated notification to show individual notifications.

    Returns JSON with list of individual notifications.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Get aggregated notification
    notification = get_object_or_404(
        Notification, id=notification_id, recipient=employee_profile, is_aggregated=True
    )

    # Get individual notifications
    individual_notifications = list(
        notification.aggregated_with.all().select_related(
            "leave_request", "iou", "payroll", "appraisal"
        )
    )

    # Mark aggregated notification as read
    service = NotificationService()
    service.mark_as_read(str(notification_id), employee_profile)

    # Serialize for JSON response
    notifications_data = []
    for notif in individual_notifications:
        notifications_data.append(
            {
                "id": str(notif.id),
                "type": notif.notification_type,
                "title": notif.title,
                "message": notif.message,
                "created_at": notif.created_at.isoformat(),
                "is_read": notif.is_read,
            }
        )

    return JsonResponse(
        {
            "success": True,
            "notifications": notifications_data,
            "count": len(notifications_data),
        }
    )


# ==================== DIGEST MANAGEMENT VIEWS ====================


@login_required
def notification_digests(request):
    """
    View to display notification digest history.

    Shows past daily and weekly digests.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize service
    service = NotificationService()

    # Get digest notifications (INFO type with aggregation)
    digests = (
        Notification.objects.filter(
            recipient=employee_profile,
            notification_type="INFO",
            is_aggregated=True,
            is_deleted=False,
        )
        .filter(aggregation_key__startswith="digest:")
        .select_related("leave_request", "iou", "payroll", "appraisal")
        .order_by("-created_at")[:20]
    )

    # Get unread count
    unread_count = service.get_unread_count(employee_profile)

    context = {
        "digests": digests,
        "unread_count": unread_count,
    }

    return render(request, "notifications/notification_digests.html", context)


@login_required
@require_POST
def notification_digest_settings(request):
    """
    Update digest settings from digest management page.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        messages.error(request, "Employee profile not found.")
        return redirect("payroll:notification_digests")

    daily_enabled = request.POST.get("daily_digest_enabled") == "on"
    weekly_enabled = request.POST.get("weekly_digest_enabled") == "on"

    preference_service = PreferenceService()
    try:
        if weekly_enabled and not daily_enabled:
            frequency = "weekly"
        elif daily_enabled:
            frequency = "daily"
        else:
            frequency = "immediate"

        preference_service.update_preferences(
            employee_profile, {"email_digest_frequency": frequency}
        )
        messages.success(request, "Digest settings updated successfully.")
    except Exception as exc:
        messages.error(request, f"Failed to update digest settings: {exc}")

    return redirect("payroll:notification_digests")


@login_required
@require_POST
def enable_daily_digest(request):
    """
    Enable daily digest for the current user.

    Updates preference to receive daily notification digest.
    Returns JSON response.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize preference service
    preference_service = PreferenceService()

    # Update email digest frequency to daily
    try:
        preference_service.update_preferences(
            employee_profile, {"email_digest_frequency": "daily"}
        )
        return JsonResponse(
            {"success": True, "message": "Daily digest enabled successfully"}
        )
    except Exception as e:
        return JsonResponse(
            {"error": f"Failed to enable daily digest: {str(e)}"}, status=400
        )


@login_required
@require_POST
def enable_weekly_digest(request):
    """
    Enable weekly digest for the current user.

    Updates preference to receive weekly notification digest.
    Returns JSON response.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize preference service
    preference_service = PreferenceService()

    # Update email digest frequency to weekly
    try:
        preference_service.update_preferences(
            employee_profile, {"email_digest_frequency": "weekly"}
        )
        return JsonResponse(
            {"success": True, "message": "Weekly digest enabled successfully"}
        )
    except Exception as e:
        return JsonResponse(
            {"error": f"Failed to enable weekly digest: {str(e)}"}, status=400
        )


@login_required
@require_POST
def disable_digest(request):
    """
    Disable digest for the current user.

    Updates preference to receive immediate notifications.
    Returns JSON response.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize preference service
    preference_service = PreferenceService()

    # Update email digest frequency to immediate
    try:
        preference_service.update_preferences(
            employee_profile, {"email_digest_frequency": "immediate"}
        )
        return JsonResponse(
            {"success": True, "message": "Digest disabled successfully"}
        )
    except Exception as e:
        return JsonResponse(
            {"error": f"Failed to disable digest: {str(e)}"}, status=400
        )


@login_required
@require_POST
def trigger_manual_digest(request):
    """
    Trigger manual digest creation for the current user.

    Creates and sends a digest immediately.
    Returns JSON response.
    """
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        return JsonResponse({"error": "Employee profile not found"}, status=404)

    # Initialize digest service
    digest_service = DigestService()

    # Get frequency from request (default to daily)
    frequency = request.POST.get("frequency", "daily")

    # Create and send digest
    try:
        if frequency == "daily":
            digest = digest_service.create_daily_digest(employee_profile)
        elif frequency == "weekly":
            digest = digest_service.create_weekly_digest(employee_profile)
        else:
            return JsonResponse(
                {"error": "Invalid frequency. Use 'daily' or 'weekly'"}, status=400
            )

        if digest:
            return JsonResponse(
                {
                    "success": True,
                    "message": f"{frequency.capitalize()} digest created successfully",
                    "digest_id": str(digest.id),
                }
            )
        else:
            return JsonResponse(
                {
                    "success": True,
                    "message": f"No notifications to include in {frequency} digest",
                }
            )

    except Exception as e:
        return JsonResponse({"error": f"Failed to create digest: {str(e)}"}, status=500)


# ==================== CLASS-BASED VIEW FOR BACKWARD COMPATIBILITY ====================


class NotificationListView(LoginRequiredMixin, ListView):
    """
    Class-based view for notification list (maintained for backward compatibility).

    Uses NotificationService for data retrieval.
    """

    model = Notification
    template_name = "notifications/notification_list.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        """Get notifications using NotificationService"""
        try:
            employee_profile = self.request.user.employee_user
        except models.EmployeeProfile.DoesNotExist:
            return Notification.objects.none()

        # Initialize service
        service = NotificationService()

        # Get filter parameters
        notification_type = self.request.GET.get("type")
        read_status = self.request.GET.get("read")
        priority = self.request.GET.get("priority")

        # Convert read status
        unread_only = read_status == "unread"

        # Get notifications using service
        queryset = service.get_notifications(
            recipient=employee_profile,
            unread_only=unread_only,
            notification_type=notification_type,
            priority=priority,
            limit=100,  # Get more for pagination
            offset=0,
        )

        return queryset

    def get_context_data(self, **kwargs):
        """Add additional context data"""
        context = super().get_context_data(**kwargs)

        try:
            employee_profile = self.request.user.employee_user
            service = NotificationService()
            context["unread_count"] = service.get_unread_count(employee_profile)
        except models.EmployeeProfile.DoesNotExist:
            context["unread_count"] = 0

        context["filter_type"] = self.request.GET.get("type", "all")
        context["read_status"] = self.request.GET.get("read", "all")
        context["search_query"] = self.request.GET.get("q", "")
        context["priority_filter"] = self.request.GET.get("priority", None)

        return context
