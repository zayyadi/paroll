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

class CompanyPayrollSettingForm(forms.ModelForm):
    class Meta:
        model = models.CompanyPayrollSetting
        fields = [
            "basic_percentage",
            "housing_percentage",
            "transport_percentage",
            "pension_employee_percentage",
            "pension_employer_percentage",
            "nhf_percentage",
            "leave_allowance_percentage",
            "pays_thirteenth_month",
            "thirteenth_month_percentage",
        ]
        widgets = {
            "basic_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "housing_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "transport_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "pension_employee_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "pension_employer_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "nhf_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "leave_allowance_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "thirteenth_month_percentage": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        input_classes = (
            "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = input_classes



class CompanyHealthInsuranceTierForm(forms.ModelForm):
    class Meta:
        model = models.CompanyHealthInsuranceTier
        fields = [
            "min_salary",
            "max_salary",
            "employee_percentage",
            "employer_percentage",
            "sort_order",
        ]
        widgets = {
            "min_salary": forms.NumberInput(attrs={"step": "0.01"}),
            "max_salary": forms.NumberInput(attrs={"step": "0.01"}),
            "employee_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "employer_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "sort_order": forms.NumberInput(attrs={"min": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        input_classes = (
            "w-full px-3 py-2 border border-secondary-300 rounded-lg "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
        )
        for field_name, field in self.fields.items():
            if field_name == "sort_order":
                field.widget.attrs["class"] = (
                    "w-24 px-3 py-2 border border-secondary-300 rounded-lg "
                    "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                )
            else:
                field.widget.attrs["class"] = input_classes


CompanyHealthInsuranceTierFormSet = forms.inlineformset_factory(
    models.CompanyPayrollSetting,
    models.CompanyHealthInsuranceTier,
    form=CompanyHealthInsuranceTierForm,
    extra=1,
    can_delete=True,
)

