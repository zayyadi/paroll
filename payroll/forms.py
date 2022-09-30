from django import forms

from payroll.models import *

class PayrollForm(forms.ModelForm):

    class Meta:
        model = Payroll
        fields = ('employee', 'basic_salary')

    def __init__(self, *args, **kwargs):
        super(PayrollForm, self).__init__(*args, **kwargs)

        self.fields['employee'].widget.attrs = {'placeholder': 'Choose Employee', 'class':'form-control'}
        self.fields['basic_salary'].widget.attrs = {'placeholder': 'Enter your Basic Salary', 'class':'form-control'}


class VariableForm(forms.ModelForm):

    class Meta:
        model = VariableCalc
        fields = ('payr', 'is_leave','is_overtime','is_absent', 'is_late')

    def __init__(self, *args, **kwargs):
        super(VariableForm, self).__init__(*args, **kwargs)

        self.fields['payr'].widget.attrs = {'placeholder':"choose Employee Pay"}
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