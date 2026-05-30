"""Domain-specific forms module."""

from decimal import Decimal
from calendar import monthrange
import json

from django import forms
from django.utils import timezone
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Q

from payroll import models
from monthyear.forms import MonthField
from company.utils import get_user_company
from payroll.forms._helpers import (
    _employee_blocked_for_payday,
    _apply_standard_widget_classes,
    _parse_lines,
    _parse_json_object,
    _normalize_month_widget_data,
    _get_period_bounds,
)

class AuditTrailForm(forms.ModelForm):
    class Meta:
        model = models.AuditTrail
        fields = [
            "user",
            "action",
            "content_type",
            "object_id",
        ]  # Excluded 'timestamp' as it is non-editable.



