from django import forms

from payroll.models import *

from crispy_forms.helper import FormHelper

from crispy_forms.layout import Field, Layout, Div, ButtonHolder, Submit


class EmployeeProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                Field("first_name"),
                css_class="col-md-4",
            ),
            Div(
                Field("last_name"),
                css_class="col-md-4",
            ),
            Div(
                Field("email"),
                css_class="col-md-4",
            ),
            Div(
                Field("photo"),
                css_class="col-md-4",
            ),
            Div(
                Field("date_of_birth"),
                css_class="col-md-4",
            ),
            Div(
                Field("gender"),
                css_class="col-md-4",
            ),
            Div(
                Div(
                    Field("date_of_employment"),
                    css_class="col-md-4",
                ),
                Div(
                    Field("employee_pay"),
                    css_class="col-md-4",
                ),
                Div(
                    Field("contract_type"),
                    css_class="col-md-4",
                ),
                Div(
                    Field("bank_account_name"),
                    css_class="col-md-4",
                ),
                Div(
                    Field("bank_account_number"),
                    css_class="col-md-4",
                ),
                css_class="row",
            ),
            Div(
                Div(
                    Field("email"),
                    css_class="col-md-4",
                ),
                Div(
                    Field("phone"),
                    css_class="col-md-4",
                ),
                Div(
                    Field("job_title"),
                    css_class="col-md-4",
                ),
                Div(
                    Field("address"),
                    css_class="col-md-4",
                ),
                css_class="row",
            ),
            ButtonHolder(Submit("submit", "Save", css_class="button white")),
        )
        super(EmployeeProfileForm, self).__init__(*args, **kwargs)

    class Meta:
        model = EmployeeProfile
        fields = "__all__"


class PayrollForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        widget=forms.TextInput(attrs={"class": "datepicker"})
    )
    date_of_employment = forms.DateField(
        widget=forms.TextInput(attrs={"class": "datepicker"})
    )

    class Meta:
        model = Payroll
        fields = ("basic_salary",)

    def __init__(self, *args, **kwargs):
        super(PayrollForm, self).__init__(*args, **kwargs)

        # self.fields['employee'].widget.attrs = {'placeholder': 'Choose Employee', 'class':'form-control'}
        self.fields["basic_salary"].widget.attrs = {
            "placeholder": "Enter your Basic Salary",
            "class": "form-control",
        }


class AllowanceForm(forms.ModelForm):
    class Meta:
        model = Allowance
        fields = ("payee", "name", "amount")

    def __init__(self, *args, **kwargs):
        super(AllowanceForm, self).__init__(*args, **kwargs)

        # self.fields['payr'].widget.attrs = {'placeholder':"choose Employee Pay"}
        self.fields["name"].widget.attrs = {"placeholder": "Name"}
        self.fields["amount"].widget.attrs = {"placeholder": "Amount"}


class CustomMMCF(forms.ModelMultipleChoiceField):
    def label_from_instance(self, member):
        return "%s" % member.name


class PaydayForm(forms.ModelForm):

    paydays = MonthField()

    class Meta:
        model = PayT
        fields = ("name", "slug", "paydays", "payroll_payday")

        payroll_payday = CustomMMCF(
            queryset=PayVar.objects.all(), widget=forms.CheckboxSelectMultiple
        )
