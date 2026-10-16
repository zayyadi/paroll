from django import forms
from payroll.models import LeaveType


class TimesheetForm(forms.Form):
    week_start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    total_hours = forms.DecimalField(min_value=0, max_value=168, decimal_places=2, required=False,
                                    help_text="Leave blank to use clocked attendance hours.")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = ["code", "name", "default_days", "is_paid", "allows_half_day", "encashable",
                  "encashment_rate", "carryover_rate", "is_active"]

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.company = company
        if self.instance.pk:
            self.fields["code"].disabled = True

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if LeaveType.objects.filter(company=self.instance.company, code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This company already has that leave type code.")
        if not code.replace("_", "").isalnum():
            raise forms.ValidationError("Use letters, numbers and underscores.")
        return code


class DatasetQueryForm(forms.Form):
    start = forms.DateField(required=False)
    end = forms.DateField(required=False)
    metrics = forms.CharField(required=False)

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise forms.ValidationError("Start must be on or before end.")
        allowed = {"headcount", "attrition", "absence", "overtime", "payroll_cost"}
        selected = [v.strip() for v in data.get("metrics", "").split(",") if v.strip()]
        if set(selected) - allowed:
            raise forms.ValidationError("Select valid analytics metrics.")
        data["metrics"] = selected or None
        return data


