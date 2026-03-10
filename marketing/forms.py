from django import forms

from marketing.models import LeadInquiry


class LeadInquiryForm(forms.ModelForm):
    class Meta:
        model = LeadInquiry
        fields = [
            "full_name",
            "work_email",
            "company_name",
            "company_size",
            "message",
        ]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5}),
        }
