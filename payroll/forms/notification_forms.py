"""
Forms for Notification System

This module provides forms for managing notification preferences,
filtering notifications, and configuring digests.

Architecture Reference: plans/NOTIFICATION_SYSTEM_ARCHITECTURE.md (Section 6)
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from payroll.models.notification import (
    NotificationPreference,
    Notification,
    NotificationTemplate,
)


class NotificationPreferenceForm(forms.ModelForm):
    """
    Form for managing global notification preferences.

    Features:
    - Channel enable/disable toggles
    - Priority threshold selection
    - Digest frequency configuration
    - Quiet hours setup
    """

    class Meta:
        model = NotificationPreference
        fields = [
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
        ]
        widgets = {
            "quiet_hours_start": forms.TimeInput(
                attrs={
                    "type": "time",
                    "class": "form-control",
                }
            ),
            "quiet_hours_end": forms.TimeInput(
                attrs={
                    "type": "time",
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        """Initialize form with custom help texts"""
        super().__init__(*args, **kwargs)

        # Add help texts
        self.fields[
            "notifications_enabled"
        ].help_text = "Enable or disable all notifications for this user."
        self.fields[
            "in_app_enabled"
        ].help_text = "Receive notifications in the application interface."
        self.fields["email_enabled"].help_text = "Receive notifications via email."
        self.fields[
            "push_enabled"
        ].help_text = "Receive push notifications on mobile devices."
        self.fields[
            "sms_enabled"
        ].help_text = "Receive SMS notifications (critical only recommended)."
        self.fields[
            "in_app_priority_threshold"
        ].help_text = "Minimum priority level for in-app notifications."
        self.fields[
            "email_priority_threshold"
        ].help_text = "Minimum priority level for email notifications."
        self.fields[
            "push_priority_threshold"
        ].help_text = "Minimum priority level for push notifications."
        self.fields[
            "sms_priority_threshold"
        ].help_text = "Minimum priority level for SMS notifications."
        self.fields[
            "email_digest_frequency"
        ].help_text = "How often to receive email digests."
        self.fields[
            "push_digest_frequency"
        ].help_text = "How often to receive push notification digests."
        self.fields[
            "quiet_hours_enabled"
        ].help_text = "Suppress non-critical notifications during quiet hours."
        self.fields[
            "quiet_hours_start"
        ].help_text = "Start time for quiet hours (e.g., 22:00)."
        self.fields[
            "quiet_hours_end"
        ].help_text = "End time for quiet hours (e.g., 08:00)."
        self.fields["quiet_hours_timezone"].help_text = "Timezone for quiet hours."

    def clean(self):
        """
        Validate form data.

        Ensures:
        - Quiet hours are properly configured if enabled
        - At least one channel is enabled
        """
        cleaned_data = super().clean()

        # Validate quiet hours
        quiet_hours_enabled = cleaned_data.get("quiet_hours_enabled")
        quiet_hours_start = cleaned_data.get("quiet_hours_start")
        quiet_hours_end = cleaned_data.get("quiet_hours_end")

        if quiet_hours_enabled:
            if not quiet_hours_start or not quiet_hours_end:
                raise ValidationError(
                    "Quiet hours start and end times are required when quiet hours are enabled."
                )

            if quiet_hours_start >= quiet_hours_end:
                raise ValidationError("Quiet hours end time must be after start time.")

        # Validate at least one channel is enabled
        if cleaned_data.get("notifications_enabled"):
            channels_enabled = [
                cleaned_data.get("in_app_enabled", False),
                cleaned_data.get("email_enabled", False),
                cleaned_data.get("push_enabled", False),
                cleaned_data.get("sms_enabled", False),
            ]

            if not any(channels_enabled):
                raise ValidationError(
                    "At least one notification channel must be enabled."
                )

        return cleaned_data


class NotificationTypePreferenceForm(forms.Form):
    """
    Form for managing per-notification-type preferences.

    Allows users to configure which channels to use for each
    notification type.
    """

    # Available notification types
    NOTIFICATION_TYPES = [
        ("LEAVE_APPROVED", "Leave Approved"),
        ("LEAVE_REJECTED", "Leave Rejected"),
        ("LEAVE_PENDING", "Leave Pending"),
        ("LEAVE_CANCELLED", "Leave Cancelled"),
        ("LEAVE_REMINDER", "Leave Reminder"),
        ("IOU_APPROVED", "IOU Approved"),
        ("IOU_REJECTED", "IOU Rejected"),
        ("IOU_PENDING", "IOU Pending"),
        ("IOU_DUE", "IOU Payment Due"),
        ("PAYSLIP_AVAILABLE", "Payslip Available"),
        ("PAYROLL_PROCESSED", "Payroll Processed"),
        ("PAYROLL_FAILED", "Payroll Processing Failed"),
        ("SALARY_DISBURSED", "Salary Disbursed"),
        ("APPRAISAL_ASSIGNED", "Appraisal Assigned"),
        ("APPRAISAL_COMPLETED", "Appraisal Completed"),
        ("APPRAISAL_REMINDER", "Appraisal Reminder"),
        ("PROFILE_UPDATED", "Profile Updated"),
        ("PASSWORD_CHANGED", "Password Changed"),
        ("INFO", "Information"),
        ("WARNING", "Warning"),
        ("ERROR", "Error"),
    ]

    # Available channels
    CHANNELS = [
        ("in_app", "In-App"),
        ("email", "Email"),
        ("push", "Push Notification"),
        ("sms", "SMS"),
    ]

    notification_type = forms.ChoiceField(
        label="Notification Type",
        choices=NOTIFICATION_TYPES,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    in_app_enabled = forms.BooleanField(
        label="In-App",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    email_enabled = forms.BooleanField(
        label="Email",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    push_enabled = forms.BooleanField(
        label="Push Notification",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    sms_enabled = forms.BooleanField(
        label="SMS",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        """Initialize form with initial data from existing preferences"""
        initial = kwargs.pop("initial", {})
        super().__init__(*args, **kwargs)

        # Set initial values if provided
        if initial:
            self.fields["in_app_enabled"].initial = initial.get("in_app", True)
            self.fields["email_enabled"].initial = initial.get("email", True)
            self.fields["push_enabled"].initial = initial.get("push", False)
            self.fields["sms_enabled"].initial = initial.get("sms", False)

    def get_type_preferences(self):
        """
        Get the type preferences as a dictionary.

        Returns:
            dict: Channel settings for the notification type
        """
        return {
            "in_app": self.cleaned_data.get("in_app_enabled", True),
            "email": self.cleaned_data.get("email_enabled", True),
            "push": self.cleaned_data.get("push_enabled", False),
            "sms": self.cleaned_data.get("sms_enabled", False),
        }


class NotificationFilterForm(forms.Form):
    """
    Form for filtering notifications in list views.

    Features:
    - Filter by read status
    - Filter by notification type
    - Filter by priority
    - Filter by date range
    - Search functionality
    """

    NOTIFICATION_TYPES = [
        ("", "All Types"),
        ("LEAVE_APPROVED", "Leave Approved"),
        ("LEAVE_REJECTED", "Leave Rejected"),
        ("LEAVE_PENDING", "Leave Pending"),
        ("LEAVE_CANCELLED", "Leave Cancelled"),
        ("LEAVE_REMINDER", "Leave Reminder"),
        ("IOU_APPROVED", "IOU Approved"),
        ("IOU_REJECTED", "IOU Rejected"),
        ("IOU_PENDING", "IOU Pending"),
        ("IOU_DUE", "IOU Payment Due"),
        ("PAYSLIP_AVAILABLE", "Payslip Available"),
        ("PAYROLL_PROCESSED", "Payroll Processed"),
        ("PAYROLL_FAILED", "Payroll Processing Failed"),
        ("SALARY_DISBURSED", "Salary Disbursed"),
        ("APPRAISAL_ASSIGNED", "Appraisal Assigned"),
        ("APPRAISAL_COMPLETED", "Appraisal Completed"),
        ("APPRAISAL_REMINDER", "Appraisal Reminder"),
        ("PROFILE_UPDATED", "Profile Updated"),
        ("PASSWORD_CHANGED", "Password Changed"),
        ("INFO", "Information"),
        ("WARNING", "Warning"),
        ("ERROR", "Error"),
    ]

    PRIORITY_CHOICES = [
        ("", "All Priorities"),
        ("CRITICAL", "Critical"),
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
    ]

    STATUS_CHOICES = [
        ("", "All Statuses"),
        ("unread", "Unread Only"),
        ("read", "Read Only"),
    ]

    search = forms.CharField(
        label="Search",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search notifications...",
            }
        ),
    )

    notification_type = forms.ChoiceField(
        label="Notification Type",
        required=False,
        choices=NOTIFICATION_TYPES,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    priority = forms.ChoiceField(
        label="Priority",
        required=False,
        choices=PRIORITY_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    status = forms.ChoiceField(
        label="Status",
        required=False,
        choices=STATUS_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    start_date = forms.DateField(
        label="From Date",
        required=False,
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    end_date = forms.DateField(
        label="To Date",
        required=False,
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    def clean(self):
        """
        Validate form data.

        Ensures:
        - End date is after start date
        """
        cleaned_data = super().clean()

        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date < start_date:
            raise ValidationError("End date must be after start date.")

        return cleaned_data

    def get_filters(self):
        """
        Get filter parameters as a dictionary.

        Returns:
            dict: Filter parameters for queryset
        """
        filters = {}

        if self.cleaned_data.get("search"):
            filters["search"] = self.cleaned_data["search"]

        if self.cleaned_data.get("notification_type"):
            filters["notification_type"] = self.cleaned_data["notification_type"]

        if self.cleaned_data.get("priority"):
            filters["priority"] = self.cleaned_data["priority"]

        if self.cleaned_data.get("status"):
            filters["status"] = self.cleaned_data["status"]

        if self.cleaned_data.get("start_date"):
            filters["start_date"] = self.cleaned_data["start_date"]

        if self.cleaned_data.get("end_date"):
            filters["end_date"] = self.cleaned_data["end_date"]

        return filters


class DigestSettingsForm(forms.Form):
    """
    Form for configuring notification digests.

    Features:
    - Enable/disable digests
    - Set digest frequency
    - Configure digest time
    - Select notification types for digest
    """

    DIGEST_FREQUENCY_CHOICES = [
        ("immediate", "Immediate (No Digest)"),
        ("hourly", "Hourly Digest"),
        ("daily", "Daily Digest"),
        ("weekly", "Weekly Digest"),
    ]

    DIGEST_TIME_CHOICES = [(hour, f"{hour:02d}:00") for hour in range(24)]

    email_digest_enabled = forms.BooleanField(
        label="Enable Email Digests",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Receive notifications in digest emails instead of individually.",
    )

    email_digest_frequency = forms.ChoiceField(
        label="Email Digest Frequency",
        required=False,
        choices=DIGEST_FREQUENCY_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="How often to receive digest emails.",
    )

    email_digest_time = forms.ChoiceField(
        label="Email Digest Time",
        required=False,
        choices=DIGEST_TIME_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Time of day to send digest emails.",
    )

    push_digest_enabled = forms.BooleanField(
        label="Enable Push Digests",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Receive notifications in digest push notifications instead of individually.",
    )

    push_digest_frequency = forms.ChoiceField(
        label="Push Digest Frequency",
        required=False,
        choices=DIGEST_FREQUENCY_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="How often to receive digest push notifications.",
    )

    include_notification_types = forms.MultipleChoiceField(
        label="Include Notification Types",
        required=False,
        choices=NotificationTypePreferenceForm.NOTIFICATION_TYPES,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        help_text="Select which notification types to include in digests.",
    )

    def clean(self):
        """
        Validate form data.

        Ensures:
        - Digest time is provided if digest is enabled
        - At least one notification type is selected
        """
        cleaned_data = super().clean()

        # Validate email digest settings
        email_digest_enabled = cleaned_data.get("email_digest_enabled")
        email_digest_time = cleaned_data.get("email_digest_time")

        if email_digest_enabled and not email_digest_time:
            raise ValidationError(
                "Digest time is required when email digests are enabled."
            )

        # Validate push digest settings
        push_digest_enabled = cleaned_data.get("push_digest_enabled")
        push_digest_frequency = cleaned_data.get("push_digest_frequency")

        if push_digest_enabled and not push_digest_frequency:
            raise ValidationError(
                "Digest frequency is required when push digests are enabled."
            )

        return cleaned_data


class NotificationTemplateForm(forms.ModelForm):
    """
    Form for creating and editing notification templates.

    Features:
    - Template code and name
    - Channel and language selection
    - Subject and body templates
    - Required variables specification
    """

    class Meta:
        model = NotificationTemplate
        fields = [
            "code",
            "name",
            "description",
            "channel",
            "language",
            "subject_template",
            "body_template",
            "required_variables",
            "is_active",
        ]
        widgets = {
            "code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., leave.approved",
                }
            ),
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Leave Approval Email",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
            "subject_template": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Your leave request has been approved",
                }
            ),
            "body_template": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 10,
                    "placeholder": "Use {{ variable }} for template variables",
                }
            ),
            "required_variables": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": '["employee_name", "leave_dates"]',
                }
            ),
        }

    def clean_code(self):
        """Validate template code format"""
        code = self.cleaned_data.get("code")
        if code:
            # Convert to lowercase and replace spaces with underscores
            code = code.lower().replace(" ", "_").replace("-", "_")
            return code
        return code

    def clean_body_template(self):
        """Validate body template syntax"""
        body_template = self.cleaned_data.get("body_template")
        if body_template:
            try:
                # Try to render template to check for syntax errors
                from django.template import Template, Context

                Template(body_template)
            except Exception as e:
                raise ValidationError(f"Invalid template syntax: {str(e)}")
        return body_template

    def clean_required_variables(self):
        """Validate required variables format"""
        required_variables = self.cleaned_data.get("required_variables")
        if required_variables:
            if not isinstance(required_variables, list):
                raise ValidationError("Required variables must be a list.")
        return required_variables


class BulkNotificationForm(forms.Form):
    """
    Form for sending bulk notifications.

    Features:
    - Select recipients
    - Set notification type and priority
    - Compose message
    - Add action URL
    """

    NOTIFICATION_TYPES = NotificationTypePreferenceForm.NOTIFICATION_TYPES
    PRIORITY_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
        ("CRITICAL", "Critical"),
    ]

    recipients = forms.ModelMultipleChoiceField(
        label="Recipients",
        queryset=Notification.objects.none(),  # Will be set in view
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control select2",
                "size": 10,
            }
        ),
        help_text="Select employees to notify.",
    )

    notification_type = forms.ChoiceField(
        label="Notification Type",
        choices=NOTIFICATION_TYPES,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    priority = forms.ChoiceField(
        label="Priority",
        choices=PRIORITY_CHOICES,
        initial="MEDIUM",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    title = forms.CharField(
        label="Title",
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Notification title",
            }
        ),
    )

    message = forms.CharField(
        label="Message",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Notification message",
            }
        ),
    )

    action_url = forms.CharField(
        label="Action URL",
        required=False,
        widget=forms.URLInput(
            attrs={
                "class": "form-control",
                "placeholder": "https://example.com/action",
            }
        ),
        help_text="Optional URL for user to take action.",
    )

    action_label = forms.CharField(
        label="Action Label",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g., View Details",
            }
        ),
        help_text="Label for the action button.",
    )

    def clean(self):
        """Validate form data"""
        cleaned_data = super().clean()

        # Ensure at least one recipient is selected
        recipients = cleaned_data.get("recipients")
        if not recipients or not recipients.exists():
            raise ValidationError("At least one recipient must be selected.")

        return cleaned_data
