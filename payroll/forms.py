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
            # "date_of_birth": forms.TextInput(
            #     attrs={
            #         "label": "block text-white text-sm font-bold mb-2",
            #         "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
            #     }
            # ),
            # "date_of_employment": forms.TextInput(
            #     attrs={
            #         "label": "block text-white text-sm font-bold mb-2",
            #         "class": "h-10 border mt-1 rounded px-4 w-full bg-gray-50",
            #     }
            # ),
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


class PayrollForm(forms.ModelForm):
    class Meta:
        model = models.Payroll
        fields = ("basic_salary",)


class AllowanceForm(forms.ModelForm):
    class Meta:
        model = models.Allowance
        fields = "__all__"


# class CustomMMCF(forms.ModelMultipleChoiceField):
#     def label_from_instance(self, member):
#         return "%s" % member.name


class PaydayForm(forms.ModelForm):
    name = forms.CharField(label="Name", required=True)
    slug = forms.CharField(label="Slug", required=True)
    # paydays = forms.DateField(
    #     label="Month of Payroll",
    #     widget=forms.TextInput(attrs={"class": "datepicker"}),
    # )

    payroll_payday = forms.ModelMultipleChoiceField(
        models.PayVar.objects.all().order_by("pays__first_name"),
        label="Employee to be included in Payroll for the Month",
        widget=forms.CheckboxSelectMultiple,
    )
    # is_active = forms.CheckboxInput()

    class Meta:
        model = models.PayT
        fields = (
            "name",
            "slug",
            "paydays",
            "payroll_payday",
            "is_active",
        )

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


class PerformanceReviewForm(forms.ModelForm):
    class Meta:
        model = models.PerformanceReview
        fields = ["employee", "review_date", "rating", "comments"]
        widgets = {
            "review_date": forms.DateInput(
                attrs={"type": "date", "class": "border rounded p-2"}
            ),
            "rating": forms.Select(attrs={"class": "border rounded p-2"}),
            "comments": forms.Textarea(
                attrs={"rows": 4, "class": "border rounded p-2"}
            ),
        }
