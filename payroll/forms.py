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
                ),Div(
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
                ),Div(
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
        fields = ('basic_salary',)

    def __init__(self, *args, **kwargs):
        super(PayrollForm, self).__init__(*args, **kwargs)

        # self.fields['employee'].widget.attrs = {'placeholder': 'Choose Employee', 'class':'form-control'}
        self.fields['basic_salary'].widget.attrs = {'placeholder': 'Enter your Basic Salary', 'class':'form-control'}


class VariableForm(forms.ModelForm):

    class Meta:
        model = VariableCalc
        fields = ('is_leave','is_overtime','is_absent', 'is_late')

    def __init__(self, *args, **kwargs):
        super(VariableForm, self).__init__(*args, **kwargs)

        # self.fields['payr'].widget.attrs = {'placeholder':"choose Employee Pay"}
        self.fields['is_leave'].widget.attrs = {'placeholder':"choose is leave"}
        self.fields['is_overtime'].widget.attrs = {'placeholder':"choose is overtime"}
        self.fields['is_absent'].widget.attrs = {'placeholder':"choose is absent"}
        self.fields['is_late'].widget.attrs = {'placeholder':"choose is late"}

class CustomMMCF(forms.ModelMultipleChoiceField):    
    def label_from_instance(self, member):
        return "%s" % member.name

class PaydayForm(forms.ModelForm):

    paydays = MonthField()
    class Meta:
        model = PayT
        fields = ('name','slug','paydays','payroll_payday')

        payroll_payday = CustomMMCF(
        queryset=VariableCalc.objects.all(),
        widget=forms.CheckboxSelectMultiple
    )