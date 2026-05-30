"""Domain-specific forms module."""

from decimal import Decimal
from calendar import monthrange
import json

from django import forms
from django.utils import timezone
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Q

from payroll import models
from monthyear.forms import MonthField
from company.utils import get_user_company
from payroll.forms._helpers import (
    _employee_blocked_for_payday,
    _apply_standard_widget_classes,
    _parse_lines,
    _parse_json_object,
    _normalize_month_widget_data,
    _get_period_bounds,
)

class HiringRequisitionForm(forms.ModelForm):
    must_have_criteria = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One must-have criterion per line.",
    )

    class Meta:
        model = models.JobRequisition
        fields = [
            "position",
            "title",
            "hiring_manager",
            "headcount",
            "status",
            "compensation_min",
            "compensation_max",
            "currency",
            "outcomes_90_days",
            "must_have_criteria",
        ]
        widgets = {
            "outcomes_90_days": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company is not None:
            user_model = get_user_model()
            self.fields["position"].queryset = models.Position.objects.filter(company=company)
            self.fields["hiring_manager"].queryset = user_model.objects.filter(
                Q(company=company) | Q(active_company=company)
            ).distinct()
        _apply_standard_widget_classes(self.fields)

    def clean_must_have_criteria(self):
        return _parse_lines(self.cleaned_data.get("must_have_criteria"))



class HiringCandidateForm(forms.ModelForm):
    class Meta:
        model = models.HiringCandidate
        fields = [
            "requisition",
            "first_name",
            "last_name",
            "email",
            "phone",
            "source",
            "consent_to_process",
        ]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company is not None:
            self.fields["requisition"].queryset = models.JobRequisition.objects.filter(
                company=company,
                status__in=[
                    models.JobRequisition.Status.OPEN,
                    models.JobRequisition.Status.ON_HOLD,
                ],
            )
        _apply_standard_widget_classes(self.fields)

    def clean_consent_to_process(self):
        consent = self.cleaned_data.get("consent_to_process")
        if not consent:
            raise forms.ValidationError("Candidate consent is required before storing hiring data.")
        return consent



class HiringScorecardForm(forms.Form):
    stage = forms.ModelChoiceField(queryset=models.HiringStage.objects.none())
    recommendation = forms.ChoiceField(choices=models.HiringStageScorecard.Recommendation.choices)
    competency_scores = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text='JSON object, for example {"role_fit": 5, "values": 4}.',
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["stage"].queryset = models.HiringStage.objects.filter(
                company=company,
                is_active=True,
            )
        _apply_standard_widget_classes(self.fields)

    def clean_competency_scores(self):
        scores = _parse_json_object(self.cleaned_data.get("competency_scores"), "Competency scores")
        for competency, score in scores.items():
            try:
                numeric_score = Decimal(str(score))
            except Exception as exc:
                raise forms.ValidationError(f"{competency} must be numeric.") from exc
            if numeric_score < 1 or numeric_score > 5:
                raise forms.ValidationError(f"{competency} must be scored from 1 to 5.")
        return scores



class JobOfferForm(forms.Form):
    title = forms.CharField(max_length=255)
    employment_type = forms.ChoiceField(choices=models.Position.EmploymentType.choices)
    salary_amount = forms.DecimalField(max_digits=14, decimal_places=2)
    currency = forms.CharField(max_length=3, initial="NGN")
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    expires_at = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    terms = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text='Optional JSON object, for example {"probation_months": 6}.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_standard_widget_classes(self.fields)

    def clean_terms(self):
        return _parse_json_object(self.cleaned_data.get("terms"), "Terms")



