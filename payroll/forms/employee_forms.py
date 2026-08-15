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

class EmployeeProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        company = get_user_company(user)
        if company:
            self.fields["department"].queryset = models.Department.objects.filter(
                company=company
            )
            self.fields["employee_pay"].queryset = models.Payroll.objects.filter(
                company=company
            )
        # Date of Employment: a single native date input instead of the
        # month/year split widget. The model stores the 1st of the month, so
        # day-level precision is normalized on save, matching the field's
        # month-granular semantics.
        doe = self.instance.date_of_employment if self.instance and self.instance.pk else None
        self.fields["date_of_employment"] = forms.DateField(
            required=False,
            label="Date of Employment",
            help_text="",
            widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        )
        # MonthField returns a `Month` object, which is not a datetime.date
        # subclass and would render as "YYYY-MM"; convert to a real date so
        # the native input gets "YYYY-MM-DD".
        if doe:
            self.initial["date_of_employment"] = doe.first_day()

        input_class = (
            "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm bg-white"
        )
        select_class = (
            "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm bg-white"
        )
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = select_class
            elif isinstance(field.widget, forms.FileInput):
                field.widget.attrs["class"] = (
                    "block w-full text-sm text-secondary-700 file:mr-4 file:py-2 "
                    "file:px-4 file:rounded-lg file:border-0 file:text-sm "
                    "file:font-semibold file:bg-primary-50 file:text-primary-700 "
                    "hover:file:bg-primary-100"
                )
            else:
                field.widget.attrs["class"] = input_class

    class Meta:
        model = models.EmployeeProfile
        fields = [
            "first_name",
            "last_name",
            "email",
            "date_of_birth",
            "gender",
            "phone",
            "address",
            "department",
            "job_title",
            "contract_type",
            "date_of_employment",
            "employee_pay",
            "hmo_provider",
            "pension_fund_manager",
            "pension_rsa",
            # "nin",
            "tin_no",
            "rent_paid",
            "emergency_contact_name",
            "emergency_contact_relationship",
            "emergency_contact_phone",
            "next_of_kin_name",
            "next_of_kin_relationship",
            "next_of_kin_phone",
            "bank",
            "bank_account_name",
            "bank_account_number",
            "photo",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "label": "block text-white text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "label": "block text-white text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
            "slug": forms.TextInput(
                attrs={
                    "label": "block text-white text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
            "address": forms.TextInput(
                attrs={
                    "label": "block text-white text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
            "employee_pay": forms.Select(),
            "hmo_provider": forms.Select(),
            "pension_fund_manager": forms.Select(),
            "photo": forms.FileInput(),
            "pension_rsa": forms.TextInput(
                attrs={
                    "label": "block text-white text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
            "tin_no": forms.TextInput(
                attrs={
                    "label": "block text-white text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
            "rent_paid": forms.TextInput(
                attrs={
                    "label": "block text-white text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
            "contract_type": forms.Select(),
            "phone": forms.TextInput(
                attrs={
                    "label": "block text-white text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
            "gender": forms.Select(),
            "job_title": forms.Select(),
            "bank": forms.Select(),
            "bank_account_name": forms.TextInput(
                attrs={
                    "label": "block text-yellow text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
            "bank_account_number": forms.TextInput(
                attrs={
                    "label": "block text-yellow text-sm font-bold mb-2",
                    "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
                }
            ),
        }
        extra_kwargs = {
            "date_of_birth": {"required": False},
            "date_of_employment": {"required": False},
        }
        # exclude = ["created",]



class EmployeeTransferForm(forms.Form):
    """Create an employee transfer request (department / position change)."""

    employee = forms.ModelChoiceField(
        queryset=models.EmployeeProfile.objects.none(),
        label="Employee",
        empty_label="Select employee",
    )
    to_department = forms.ModelChoiceField(
        queryset=models.Department.objects.none(),
        required=False,
        label="To Department",
        empty_label="No change",
    )
    to_position = forms.CharField(
        required=False,
        label="To Position",
        help_text="Leave blank if the position is unchanged.",
    )
    effective_date = forms.DateField(
        label="Effective Date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    reason = forms.CharField(
        required=False,
        label="Reason",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields["employee"].queryset = models.EmployeeProfile.objects.filter(
                company=company, status="active"
            )
            self.fields["to_department"].queryset = models.Department.objects.filter(
                company=company
            )
        _apply_standard_widget_classes(self.fields)


class EmployeePromotionForm(forms.Form):
    """Create an employee promotion request (title change)."""

    employee = forms.ModelChoiceField(
        queryset=models.EmployeeProfile.objects.none(),
        label="Employee",
        empty_label="Select employee",
    )
    new_title = forms.CharField(label="New Title")
    effective_date = forms.DateField(
        label="Effective Date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    reason = forms.CharField(
        required=False,
        label="Reason",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields["employee"].queryset = models.EmployeeProfile.objects.filter(
                company=company, status="active"
            )
        _apply_standard_widget_classes(self.fields)


class ContractGenerateForm(forms.Form):
    """Generate an employment contract from a template for one employee."""

    employee = forms.ModelChoiceField(
        queryset=models.EmployeeProfile.objects.none(),
        label="Employee",
        empty_label="Select employee",
    )
    template = forms.ModelChoiceField(
        queryset=models.ContractTemplate.objects.none(),
        required=False,
        label="Template",
        empty_label="Default template",
    )
    start_date = forms.DateField(
        label="Start Date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        label="End Date (optional)",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields["employee"].queryset = models.EmployeeProfile.objects.filter(
                company=company, status="active"
            )
            self.fields["template"].queryset = models.ContractTemplate.objects.filter(
                company=company, is_active=True
            )
        _apply_standard_widget_classes(self.fields)


class ContractTemplateForm(forms.ModelForm):
    """Create a reusable employment contract template."""

    class Meta:
        model = models.ContractTemplate
        fields = ["name", "template_html"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": (
                        "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
                        "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
                        "text-sm bg-white"
                    ),
                    "placeholder": "e.g., Full-Time Contract",
                }
            ),
            "template_html": forms.Textarea(
                attrs={
                    "rows": 15,
                    "class": (
                        "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
                        "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
                        "text-sm bg-white font-mono"
                    ),
                    "placeholder": (
                        "Django template syntax: {{ employee.first_name }}, "
                        "{{ salary.basic }}, {{ company.name }}..."
                    ),
                }
            ),
        }


class EmployeeProfileUpdateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        shared_class = (
            "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm bg-white"
        )
        for field in self.fields.values():
            if isinstance(field.widget, forms.FileInput):
                field.widget.attrs["class"] = (
                    "block w-full text-sm text-secondary-700 file:mr-4 file:py-2 "
                    "file:px-4 file:rounded-lg file:border-0 file:text-sm "
                    "file:font-semibold file:bg-primary-50 file:text-primary-700 "
                    "hover:file:bg-primary-100"
                )
            else:
                field.widget.attrs["class"] = shared_class

    class Meta:
        model = models.EmployeeProfile
        fields = [
            "first_name",
            "last_name",
            "email",
            "date_of_birth",
            "gender",
            "phone",
            "address",
            "tin_no",
            "photo",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                }
            ),
            "date_of_birth": forms.DateInput(
                attrs={
                    "class": "appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm",
                    "type": "date",
                }
            ),
            "gender": forms.Select(
                attrs={
                    "class": "appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                }
            ),
            "address": forms.TextInput(
                attrs={
                    "class": "appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                }
            ),
            "tin_no": forms.TextInput(
                attrs={
                    "class": "appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                }
            ),
            "photo": forms.FileInput(
                attrs={
                    "class": "block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-600 hover:file:bg-indigo-100"
                }
            ),
        }
        extra_kwargs = {
            "date_of_birth": {"required": False},
        }



