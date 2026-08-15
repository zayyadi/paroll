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

class IOUForm(forms.ModelForm):
    class Meta:
        model = models.IOU
        fields = [
            "amount",
            "tenor",
            "approved_at",
        ]



class IOURequestForm(forms.ModelForm):
    @staticmethod
    def _add_months(base_date, months):
        if months <= 0:
            return base_date
        year = base_date.year + (base_date.month - 1 + months) // 12
        month = (base_date.month - 1 + months) % 12 + 1
        day = min(base_date.day, monthrange(year, month)[1])
        return base_date.replace(year=year, month=month, day=day)

    def __init__(self, *args, **kwargs):
        self.max_iou_amount = kwargs.pop("max_iou_amount", None)
        super().__init__(*args, **kwargs)
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
        self.fields["due_date"].required = False
        # due_date is always auto-calculated from the tenor, so present it as a
        # read-only native date input (matches the editorial form layer).
        self.fields["due_date"].widget.attrs.update({"type": "date", "readonly": True})
        # Enforce the caller's advance cap on the number input itself so the
        # rendered control carries a parseable max attribute.
        if self.max_iou_amount and self.max_iou_amount > 0:
            self.fields["amount"].widget.attrs["max"] = self.max_iou_amount

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None:
            return amount

        if self.max_iou_amount is not None and amount > self.max_iou_amount:
            raise forms.ValidationError(
                f"Amount cannot be more than {self.max_iou_amount}."
            )
        return amount

    def clean_tenor(self):
        tenor = self.cleaned_data.get("tenor")
        if tenor is None:
            return tenor
        if tenor < 1:
            raise forms.ValidationError("Tenor must be at least 1 month.")
        if tenor > 60:
            raise forms.ValidationError("Tenor cannot exceed 60 months.")
        return tenor

    def clean(self):
        cleaned_data = super().clean()
        tenor = cleaned_data.get("tenor")
        today = timezone.localdate()

        # Always derive due date from today's date and preferred tenor.
        if tenor:
            self.instance.tenor = tenor
        else:
            self.instance.tenor = 1

        computed_due_date = self._add_months(today, self.instance.tenor)
        cleaned_data["due_date"] = computed_due_date
        self.instance.due_date = computed_due_date

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if commit:
            instance.save()
        return instance

    class Meta:
        model = models.IOU
        fields = ["amount", "tenor", "reason", "due_date"]
        widgets = {
            "tenor": forms.NumberInput(attrs={"min": 1, "max": 60, "step": 1}),
        }



class IOUUpdateForm(forms.ModelForm):
    class Meta:
        model = models.IOU
        fields = [
            "amount",
            "reason",
            "tenor",
            "payment_method",
        ]  # Add/remove fields as needed for an update
        # For example, if 'employee_id' or 'requested_at' should not be editable here, exclude them.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Define CSS classes for different widget types
        default_input_classes = "w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
        select_classes = default_input_classes + " bg-gray-50"

        for field_name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                widget.attrs.update(
                    {"class": default_input_classes, "rows": 3}
                )  # Example: specific for textarea
            elif isinstance(widget, forms.Select):
                widget.attrs.update({"class": select_classes})
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.update(
                    {
                        "class": "h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    }
                )
            else:  # Default for TextInput, NumberInput, etc.
                widget.attrs.update({"class": default_input_classes})

            # If you were using a custom `field.widget_type` in your template,
            # you could set it on the field object here if needed, e.g.:
            # field.widget_type_for_template = widget.__class__.__name__.lower()
            # Then in template: {{ field.field.widget_type_for_template }}
            # However, by setting classes directly, this might not be necessary for styling.



class IOUApprovalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        input_class = (
            "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm bg-white"
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = input_class

    class Meta:
        model = models.IOU
        fields = ["status", "approved_at", "tenor", "repayment_deduction_percentage"]
        widgets = {
            "approved_at": forms.DateInput(attrs={"type": "date"}),
            "tenor": forms.NumberInput(attrs={"min": 1, "max": 60, "step": 1}),
            "repayment_deduction_percentage": forms.NumberInput(
                attrs={"min": 1, "max": 100, "step": "0.01"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        tenor = cleaned_data.get("tenor")
        deduction_pct = cleaned_data.get("repayment_deduction_percentage")

        if status == "APPROVED":
            if not tenor:
                self.add_error("tenor", "Set the approved tenor for repayment.")
            if not deduction_pct:
                self.add_error(
                    "repayment_deduction_percentage",
                    "Set the salary deduction percentage for repayment.",
                )

            employee_profile = getattr(self.instance, "employee_id", None)
            monthly_salary = Decimal("0.00")
            if employee_profile is not None:
                monthly_salary = Decimal(employee_profile.net_pay or Decimal("0.00"))
                if monthly_salary <= 0 and employee_profile.employee_pay:
                    monthly_salary = Decimal(
                        employee_profile.employee_pay.basic_salary or Decimal("0.00")
                    )

            if tenor and deduction_pct and monthly_salary > 0:
                monthly_deduction = (monthly_salary * Decimal(deduction_pct)) / Decimal(
                    "100"
                )
                max_repayable = monthly_deduction * Decimal(tenor)
                if max_repayable < Decimal(self.instance.total_amount):
                    self.add_error(
                        "repayment_deduction_percentage",
                        (
                            "Selected deduction percentage and tenor cannot repay this IOU "
                            "within the approved period."
                        ),
                    )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.status == "APPROVED" and not instance.approved_at:
            instance.approved_at = timezone.localdate()
        if commit:
            instance.save()
        return instance



