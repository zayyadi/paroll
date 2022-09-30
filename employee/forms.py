from django import forms

from employee.models import Employee

from crispy_forms.helper import FormHelper

from crispy_forms.layout import Field, Layout, Div, ButtonHolder, Submit

class EmployeeForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        widget=forms.TextInput(attrs={"class": "datepicker"})
    )
    date_of_employment = forms.DateField(
        widget=forms.TextInput(attrs={"class": "datepicker"})
    )

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
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
                ),Div(
                    Field("gender"),
                    css_class="col-md-4",
                ),
                css_class="row",
            ),
            Div(
                Div(
                    Field("date_of_employment"),
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
        super(EmployeeForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Employee
        fields = "__all__"