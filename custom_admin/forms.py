from django import forms
from payroll.models.payroll import PayT

class PayTAdminForm(forms.ModelForm):
    class Meta:
        model = PayT
        fields = ['name', 'paydays', 'payroll_payday', 'is_active', 'closed']
        widgets = {
            'payroll_payday': forms.CheckboxSelectMultiple,
        }
