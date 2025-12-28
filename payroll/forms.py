from django import forms

from payroll import models
from monthyear.forms import MonthField

# from crispy_forms.layout import Field, Layout, Div, ButtonHolder, Submit
# from crispy_forms.helper import FormHelper


class EmployeeProfileForm(forms.ModelForm):
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
            "pension_rsa",
            # "nin",
            # "tin_no",
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
            "photo": forms.FileInput(),
            "pension_rsa": forms.TextInput(
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


class PaydayForm(forms.ModelForm):
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
        queryset=models.PayVar.objects.all().order_by("pays__first_name"),
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
        model = models.PayT
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
        #     queryset=models.PayVar.objects.all(),  # Assuming PayVar is the related model
        #     # widget=forms.CheckboxSelectMultiple,  # Use checkboxes for multiple selection
        #     required=False,
        # )


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
    class Meta:
        model = models.IOU
        fields = ["amount", "tenor", "reason", "payment_method"]


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
    class Meta:
        model = models.IOU
        fields = ["status", "approved_at"]


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


class ReviewForm(forms.ModelForm):
    class Meta:
        model = models.Review
        fields = ["self_assessment"]


class RatingForm(forms.ModelForm):
    class Meta:
        model = models.Rating
        fields = ["metric", "rating", "comments"]


BaseRatingFormSet = forms.inlineformset_factory(
    models.Review, models.Rating, form=RatingForm, extra=0, can_delete=False
)


class AppraisalAssignmentForm(forms.ModelForm):
    class Meta:
        model = models.AppraisalAssignment
        fields = ["appraisal", "appraisee", "appraiser"]


class PaydayCreateForm(forms.Form):
    """Enhanced form for creating PayT (Pay Period) with efficient employee selection."""

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

    def save(self):
        """Create PayT instance and related PayVar/Payday entries."""
        from payroll.models import PayT, PayVar, Payday, EmployeeProfile

        # Create the PayT instance
        payt = PayT.objects.create(
            name=self.cleaned_data["name"],
            paydays=self.cleaned_data["paydays"],
            is_active=self.cleaned_data.get("is_active", False),
            closed=self.cleaned_data.get("closed", False),
        )

        # Get selected employee IDs
        employee_ids_str = self.cleaned_data.get("payroll_payday", "")
        if employee_ids_str:
            employee_ids = [
                int(eid.strip()) for eid in employee_ids_str.split(",") if eid.strip()
            ]

            # Create PayVar and Payday entries for selected employees
            for emp_id in employee_ids:
                try:
                    employee = EmployeeProfile.objects.get(id=emp_id)
                    payvar = PayVar.objects.create(pays=employee)
                    Payday.objects.create(paydays_id=payt, payroll_id=payvar)
                except EmployeeProfile.DoesNotExist:
                    continue

        return payt


class PayVarCreateForm(forms.Form):
    """Enhanced form for creating PayVar (Payroll Variables) for multiple employees."""

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
        choices=models.PayVar._meta.get_field("status").choices,
        initial="pending",
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2.5 border border-secondary-300 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm bg-white"
            }
        ),
    )

    def save(self):
        """Create PayVar entries for selected employees."""
        from payroll.models import PayVar, EmployeeProfile

        payvars = []

        # Get selected employee IDs
        employee_ids_str = self.cleaned_data.get("employee_ids", "")
        if employee_ids_str:
            employee_ids = [
                int(eid.strip()) for eid in employee_ids_str.split(",") if eid.strip()
            ]

            # Create PayVar entries for selected employees
            for emp_id in employee_ids:
                try:
                    employee = EmployeeProfile.objects.get(id=emp_id)
                    payvar = PayVar.objects.create(
                        pays=employee,
                        is_housing=self.cleaned_data.get("is_housing", False),
                        is_nhif=self.cleaned_data.get("is_nhif", False),
                        status=self.cleaned_data.get("status", "pending"),
                    )
                    payvars.append(payvar)
                except EmployeeProfile.DoesNotExist:
                    continue

        return payvars
