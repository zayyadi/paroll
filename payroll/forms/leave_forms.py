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

class LeaveRequestForm(forms.ModelForm):
    leave_type = forms.ChoiceField()

    def __init__(self, *args, company=None, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        from payroll.services.leave_type_service import ensure_default_leave_types
        if employee is None and self.instance.employee_id:
            employee = self.instance.employee
        company = company or (employee.company if employee else None)
        self.fields["leave_type"].choices = (
            [(row.code, row.name) for row in ensure_default_leave_types(company)]
            if company else []
        )
        if employee:
            self.instance.employee = employee
        input_class = (
            "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm bg-white"
        )
        textarea_class = (
            "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm bg-white"
        )
        for field in self.fields.values():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["class"] = textarea_class
                field.widget.attrs.setdefault("rows", 4)
            else:
                field.widget.attrs["class"] = input_class

    class Meta:
        model = models.LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "is_half_day", "reason"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }



class LeavePolicyForm(forms.ModelForm):
    class Meta:
        model = models.LeavePolicy
        fields = ["leave_type", "max_days"]



