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

class AppraisalForm(forms.ModelForm):
    class Meta:
        model = models.Appraisal
        fields = ["name", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date cannot be before start date.")
        return cleaned_data



class ReviewForm(forms.ModelForm):
    class Meta:
        model = models.Review
        fields = ["self_assessment"]



class RatingForm(forms.ModelForm):
    class Meta:
        model = models.Rating
        fields = ["metric", "rating", "comments"]



class AppraisalAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        company = get_user_company(user) if user else None
        if company:
            employee_qs = models.EmployeeProfile.objects.filter(company=company)
            self.fields["appraisee"].queryset = employee_qs
            self.fields["appraiser"].queryset = employee_qs
            self.fields["appraisal"].queryset = models.Appraisal.objects.filter(
                company=company
            )

    class Meta:
        model = models.AppraisalAssignment
        fields = ["appraisal", "appraisee", "appraiser"]

    def clean(self):
        cleaned_data = super().clean()
        appraisee = cleaned_data.get("appraisee")
        appraiser = cleaned_data.get("appraiser")
        appraisal = cleaned_data.get("appraisal")
        if appraisee and appraiser and appraisee.pk == appraiser.pk:
            self.add_error(
                "appraiser", "Appraiser and appraisee must be different employees."
            )
        if appraisal and appraisal.start_date and appraisal.end_date:
            if appraisal.end_date < appraisal.start_date:
                self.add_error("appraisal", "Selected appraisal has invalid date range.")
        return cleaned_data



