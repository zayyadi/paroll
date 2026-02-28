from calendar import monthrange
from decimal import Decimal

from django import forms
from django.utils import timezone
from django.apps import apps

from payroll import models
from monthyear.forms import MonthField
from company.utils import get_user_company

# from crispy_forms.layout import Field, Layout, Div, ButtonHolder, Submit
# from crispy_forms.helper import FormHelper


def _get_period_bounds(paydays):
    month_start = paydays.replace(day=1)
    month_end = month_start.replace(day=monthrange(paydays.year, paydays.month)[1])
    return month_start, month_end


def _employee_blocked_for_payday(employee, paydays):
    if not employee:
        return True, "missing employee"

    if employee.status == "terminated":
        return True, "terminated employee"

    user = employee.user
    if user and not user.is_active:
        return True, "disabled user account"

    DisciplinarySanction = apps.get_model("accounting", "DisciplinarySanction")
    period_start, period_end = _get_period_bounds(paydays)
    active_sanctions = DisciplinarySanction.objects.filter(
        case__respondent=user,
        status=DisciplinarySanction.Status.ACTIVE,
    )

    termination_exists = active_sanctions.filter(
        sanction_type=DisciplinarySanction.SanctionType.TERMINATION,
        effective_date__lte=period_end,
    ).exists()
    if termination_exists:
        return True, "terminated employee"

    for sanction in active_sanctions.filter(
        sanction_type=DisciplinarySanction.SanctionType.SUSPENSION,
        effective_date__lte=period_end,
    ):
        if sanction.overlaps_period(period_start, period_end):
            return True, "suspended in selected pay period"

    return False, ""


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


class PayrollForm(forms.Form):
    employee = forms.ModelChoiceField(queryset=models.EmployeeProfile.objects.all())
    basic_salary = forms.DecimalField(max_digits=12, decimal_places=2)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        company = get_user_company(user)
        if company:
            self.fields["employee"].queryset = models.EmployeeProfile.objects.filter(
                company=company
            )
        else:
            self.fields["employee"].queryset = models.EmployeeProfile.objects.none()


class AllowanceForm(forms.ModelForm):
    class Meta:
        model = models.Allowance
        fields = "__all__"


class DeductionForm(forms.ModelForm):
    class Meta:
        model = models.Deduction
        fields = "__all__"


# class CustomMMCF(forms.ModelMultipleChoiceField):
#     def label_from_instance(self, member):
#         return "%s" % member.name


class PayrollRunForm(forms.ModelForm):
    name = forms.CharField(
        label="Pay Period Name",
        required=True,
        widget=forms.TextInput(
            attrs={"class": "form-control border rounded p-2 w-full"}
        ),
    )
    # slug is auto-generated by AutoSlugField and typically not included in the form directly
    # paydays field will use the default widget from MonthField
    payroll_payday = forms.ModelMultipleChoiceField(
        queryset=models.PayrollEntry.objects.all().order_by("pays__first_name"),
        label="Employee to be included in Payroll for the Month",
        widget=forms.CheckboxSelectMultiple,
        required=False,  # M2M fields are often not required for the initial save
    )
    is_active = forms.BooleanField(label="Is Active?", required=False)
    closed = forms.BooleanField(
        label="Is Closed for Editing?",
        required=False,
        help_text="If checked, this pay period cannot be edited further.",
    )

    class Meta:
        model = models.PayrollRun
        fields = (
            "name",
            # "slug", # Removed as it's auto-generated
            "paydays",
            "payroll_payday",
            "is_active",
            "closed",
        )
        # The MonthField for 'paydays' should render its own widget.
        # You can add custom widgets here if needed for other fields.

        # paydays = forms.DateField( # Removed override
        #     label="Month of Payroll",
        #     widget=forms.TextInput(attrs={"class": "datepicker"}),
        # )

        # forms.ModelMultipleChoiceField(
        #     queryset=models.PayrollEntry.objects.all(),  # Assuming PayrollEntry is the related model
        #     # widget=forms.CheckboxSelectMultiple,  # Use checkboxes for multiple selection
        #     required=False,
        # )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        company = get_user_company(self.user)
        if company:
            self.fields["payroll_payday"].queryset = models.PayrollEntry.objects.filter(
                company=company
            ).order_by("pays__first_name")
        else:
            self.fields["payroll_payday"].queryset = models.PayrollEntry.objects.none()

        input_classes = (
            "form-input w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
        )
        checkbox_classes = (
            "h-4 w-4 text-primary-600 border-secondary-300 rounded focus:ring-primary-500"
        )
        self.fields["name"].widget.attrs["class"] = input_classes
        self.fields["paydays"].widget.attrs["class"] = input_classes
        self.fields["is_active"].widget.attrs["class"] = checkbox_classes
        self.fields["closed"].widget.attrs["class"] = checkbox_classes

    def save(self, commit=True):
        obj = super().save(commit=False)
        requested_closed = bool(self.cleaned_data.get("closed", False))
        is_new = obj.pk is None

        # For newly-created payroll runs, defer closure until after M2M entries
        # are persisted so close-trigger posting can see linked payroll entries.
        if is_new and requested_closed:
            obj.closed = False

        company = get_user_company(self.user)
        if company and not obj.company_id:
            obj.company = company
        if commit:
            obj.save()
            self.save_m2m()
            if is_new and requested_closed:
                obj.closed = True
                obj.save(update_fields=["closed"])
        return obj

    def clean_payroll_payday(self):
        payroll_entries = self.cleaned_data.get("payroll_payday")
        paydays = self.cleaned_data.get("paydays")
        if not payroll_entries or not paydays:
            return payroll_entries

        blocked = []
        for payroll_entry in payroll_entries:
            employee = payroll_entry.pays
            is_blocked, reason = _employee_blocked_for_payday(employee, paydays)
            if is_blocked:
                name = f"{employee.first_name} {employee.last_name}".strip()
                blocked.append(f"{name or employee.emp_id} ({reason})")

        if blocked:
            raise forms.ValidationError(
                "Some selected employees are not payroll-eligible for this period: "
                + ", ".join(blocked)
            )
        return payroll_entries


class MonthForm(forms.Form):
    month = MonthField()


class IOUForm(forms.ModelForm):
    class Meta:
        model = models.IOU
        fields = [
            "amount",
            "tenor",
            "approved_at",
        ]


class LeaveRequestForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
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

    class Meta:
        model = models.LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "reason"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class LeavePolicyForm(forms.ModelForm):
    class Meta:
        model = models.LeavePolicy
        fields = ["leave_type", "max_days"]


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


class AuditTrailForm(forms.ModelForm):
    class Meta:
        model = models.AuditTrail
        fields = [
            "user",
            "action",
            "content_type",
            "object_id",
        ]  # Excluded 'timestamp' as it is non-editable.


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


class PayrollRunCreateForm(forms.Form):
    """Enhanced form for creating PayrollRun (Pay Period) with efficient employee selection."""

    name = forms.CharField(
        label="Pay Period Name",
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-2.5 border border-secondary-300 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm",
                "placeholder": "e.g., December 2024 Payroll",
            }
        ),
    )
    paydays = MonthField(
        label="Month",
        required=True,
    )
    is_active = forms.BooleanField(
        label="Mark as Active",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 text-primary-600 border-secondary-300 rounded focus:ring-primary-500"
            }
        ),
    )
    closed = forms.BooleanField(
        label="Close for Editing",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 text-primary-600 border-secondary-300 rounded focus:ring-primary-500"
            }
        ),
    )

    # Hidden field to store selected employee IDs
    payroll_payday = forms.CharField(
        widget=forms.HiddenInput(attrs={"name": "payroll_payday"}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("is_active"):
            self.add_error(
                "is_active",
                "Pay period must be marked as active before creation.",
            )
        return cleaned_data

    def save(self):
        """Create PayrollRun instance and related PayrollEntry/PayrollRunEntry entries."""
        from payroll.models import PayrollRun, PayrollEntry, PayrollRunEntry, EmployeeProfile

        requested_closed = bool(self.cleaned_data.get("closed", False))
        company = get_user_company(self.user)

        # Create the PayrollRun instance
        payt = PayrollRun.objects.create(
            name=self.cleaned_data["name"],
            paydays=self.cleaned_data["paydays"],
            is_active=self.cleaned_data.get("is_active", False),
            closed=False,
            company=company,
        )

        # Get selected employee IDs
        employee_ids_str = self.cleaned_data.get("payroll_payday", "")
        skipped_employees = []
        if employee_ids_str:
            employee_ids = [
                int(eid.strip()) for eid in employee_ids_str.split(",") if eid.strip()
            ]

            # Create PayrollEntry and PayrollRunEntry entries for selected employees
            for emp_id in employee_ids:
                try:
                    employee = EmployeeProfile.objects.get(
                        id=emp_id,
                        company=company,
                    )
                    is_blocked, reason = _employee_blocked_for_payday(
                        employee, self.cleaned_data["paydays"]
                    )
                    if is_blocked:
                        full_name = f"{employee.first_name} {employee.last_name}".strip()
                        skipped_employees.append(f"{full_name or employee.emp_id} ({reason})")
                        continue

                    payvar = PayrollEntry.objects.create(
                        pays=employee,
                        company=company,
                        status="active",
                    )
                    PayrollRunEntry.objects.create(payroll_run=payt, payroll_entry=payvar)
                except EmployeeProfile.DoesNotExist:
                    continue

        if requested_closed:
            payt.closed = True
            payt.save(update_fields=["closed"])

        payt._skipped_employee_reasons = skipped_employees
        return payt


class PayrollEntryCreateForm(forms.Form):
    """Enhanced form for creating PayrollEntry (Payroll Variables) for multiple employees."""

    employee_ids = forms.CharField(
        widget=forms.HiddenInput(attrs={"name": "employee_ids"}),
        required=False,
    )
    is_housing = forms.BooleanField(
        label="NHF Deductable",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 text-primary-600 border-secondary-300 rounded focus:ring-primary-500"
            }
        ),
    )
    is_nhif = forms.BooleanField(
        label="NHIF Deductable",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 text-primary-600 border-secondary-300 rounded focus:ring-primary-500"
            }
        ),
    )
    status = forms.ChoiceField(
        label="Status",
        choices=models.PayrollEntry._meta.get_field("status").choices,
        initial="pending",
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2.5 border border-secondary-300 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm bg-white"
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def save(self):
        """Create PayrollEntry entries for selected employees."""
        from payroll.models import PayrollEntry, EmployeeProfile

        payvars = []

        # Get selected employee IDs
        employee_ids_str = self.cleaned_data.get("employee_ids", "")
        if employee_ids_str:
            employee_ids = [
                int(eid.strip()) for eid in employee_ids_str.split(",") if eid.strip()
            ]

            # Create PayrollEntry entries for selected employees
            for emp_id in employee_ids:
                try:
                    employee = EmployeeProfile.objects.get(
                        id=emp_id,
                        company=get_user_company(self.user),
                    )
                    payvar = PayrollEntry.objects.create(
                        pays=employee,
                        status=self.cleaned_data.get("status", "pending"),
                    )
                    payvars.append(payvar)
                except EmployeeProfile.DoesNotExist:
                    continue

        return payvars


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
