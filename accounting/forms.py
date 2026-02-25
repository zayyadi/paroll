from django import forms
from django.forms import formset_factory
from django.forms.models import inlineformset_factory
from django.utils import timezone
from .models import (
    Account,
    Journal,
    JournalEntry,
    FiscalYear,
    AccountingPeriod,
    DisciplinaryCase,
    DisciplinaryEvidence,
    DisciplinarySanction,
    DisciplinaryAppeal,
)
from .utils import get_entry_type_for_balance_adjustment


class AccountForm(forms.ModelForm):
    """
    Form for creating and editing accounts
    """

    class Meta:
        model = Account
        fields = ["name", "account_number", "type", "description"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-input block w-full px-3 py-2 border border-secondary-300 rounded-md leading-5 bg-white text-secondary-900 focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500 sm:text-sm",
                    "placeholder": "e.g. Cash and Cash Equivalents",
                }
            ),
            "account_number": forms.TextInput(
                attrs={
                    "class": "form-input block w-full px-3 py-2 border border-secondary-300 rounded-md leading-5 bg-white text-secondary-900 focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500 sm:text-sm",
                    "placeholder": "e.g. 1010",
                }
            ),
            "type": forms.Select(
                attrs={
                    "class": "form-input block w-full px-3 py-2 border border-secondary-300 rounded-md leading-5 bg-white text-secondary-900 focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500 sm:text-sm",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-input block w-full px-3 py-2 border border-secondary-300 rounded-md leading-5 bg-white text-secondary-900 focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500 sm:text-sm",
                    "placeholder": "Optional notes about this account",
                }
            ),
        }


class JournalForm(forms.ModelForm):
    """
    Form for creating and editing journals
    """

    class Meta:
        model = Journal
        fields = ["description", "date", "period"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
        }


class JournalEntryForm(forms.ModelForm):
    """
    Form for creating and editing journal entries
    """

    class Meta:
        model = JournalEntry
        fields = ["account", "entry_type", "amount", "memo"]
        widgets = {
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "memo": forms.TextInput(attrs={"class": "form-control"}),
        }


# Create formset for journal entries
JournalEntryFormSet = inlineformset_factory(
    Journal,
    JournalEntry,
    form=JournalEntryForm,
    extra=2,
    can_delete=True,
    min_num=2,
    validate_min=True,
)


class JournalApprovalForm(forms.Form):
    """
    Form for approving or rejecting journals
    """

    ACTION_CHOICES = [
        ("approve", "Approve"),
        ("reject", "Reject"),
    ]

    action = forms.ChoiceField(
        choices=ACTION_CHOICES, widget=forms.RadioSelect, label="Action"
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Reason (optional)",
    )


class JournalReversalForm(forms.Form):
    """
    Form for reversing journals
    """

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Reason for reversal",
        help_text="Please provide a detailed reason for reversing this journal.",
    )


class FiscalYearForm(forms.ModelForm):
    """
    Form for creating and editing fiscal years
    """

    class Meta:
        model = FiscalYear
        fields = ["year", "name", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class AccountingPeriodForm(forms.ModelForm):
    """
    Form for creating and editing accounting periods
    """

    class Meta:
        model = AccountingPeriod
        fields = ["fiscal_year", "period_number", "name", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class AccountSearchForm(forms.Form):
    """
    Form for searching accounts
    """

    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search by name or number..."}),
    )


class JournalSearchForm(forms.Form):
    """
    Form for searching journals
    """

    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Search by description or number..."}
        ),
    )
    status = forms.ChoiceField(
        choices=[("", "All Status")] + list(Journal.JournalStatus.choices),
        required=False,
    )
    start_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    end_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )


class TrialBalanceForm(forms.Form):
    """
    Form for generating trial balance
    """

    period = forms.ModelChoiceField(
        queryset=AccountingPeriod.objects.all(),
        required=False,
        empty_label="Select a period",
    )
    as_of_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="As of date (if no period selected)",
    )


class AccountActivityForm(forms.Form):
    """
    Form for generating account activity report
    """

    account = forms.ModelChoiceField(
        queryset=Account.objects.all(),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    start_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    end_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )


class OpeningBalanceImportForm(forms.Form):
    """
    Import opening balances from CSV and post a balancing journal.
    """

    opening_date = forms.DateField(
        initial=timezone.now().date,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Opening Balance Date",
    )
    offset_account = forms.ModelChoiceField(
        queryset=Account.objects.all().order_by("account_number", "name"),
        label="Offset Account (e.g. Opening Balance Equity)",
    )
    csv_file = forms.FileField(
        label="CSV File",
        help_text="Required columns: account_number,balance. Optional: memo,account_name",
    )
    description = forms.CharField(
        max_length=255,
        required=False,
        initial="Opening balances import",
        widget=forms.TextInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            "w-full px-3 py-2 border border-secondary-300 rounded-md "
            "focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = base_class


class BalanceAdjustmentForm(forms.Form):
    """
    Journal-backed account balance adjustment form.
    """

    ADJUSTMENT_CHOICES = [
        ("INCREASE", "Increase Balance"),
        ("DECREASE", "Decrease Balance"),
    ]

    account = forms.ModelChoiceField(
        queryset=Account.objects.all().order_by("account_number", "name"),
        label="Primary Account",
    )
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_CHOICES,
        label="Adjustment Type",
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={"step": "0.01"}),
        error_messages={
            "max_digits": "Amount can have at most 10 digits before the decimal point and 2 decimal places.",
            "max_decimal_places": "Amount can have at most 2 decimal places.",
        },
    )
    offset_account = forms.ModelChoiceField(
        queryset=Account.objects.all().order_by("account_number", "name"),
        label="Offset Account",
        help_text="Counter account for double-entry balancing.",
    )
    description = forms.CharField(
        max_length=255,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Reason for adjustment (required for audit).",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            "w-full px-3 py-2 border border-secondary-300 rounded-md "
            "focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = base_class

    def clean(self):
        cleaned_data = super().clean()
        account = cleaned_data.get("account")
        offset_account = cleaned_data.get("offset_account")
        if account and offset_account and account.pk == offset_account.pk:
            self.add_error("offset_account", "Offset account must be different.")
        return cleaned_data

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount is None:
            return amount

        if amount.adjusted() + 1 > 10:
            raise forms.ValidationError(
                "Amount can have at most 10 digits before the decimal point."
            )
        return amount

    def build_entries(self):
        account = self.cleaned_data["account"]
        offset_account = self.cleaned_data["offset_account"]
        amount = self.cleaned_data["amount"]
        adjustment_type = self.cleaned_data["adjustment_type"]

        primary_entry_type = get_entry_type_for_balance_adjustment(
            account, adjustment_type
        )
        offset_entry_type = "CREDIT" if primary_entry_type == "DEBIT" else "DEBIT"

        return [
            {
                "account": account,
                "entry_type": primary_entry_type,
                "amount": amount,
                "memo": f"Balance {adjustment_type.lower()} - primary account",
            },
            {
                "account": offset_account,
                "entry_type": offset_entry_type,
                "amount": amount,
                "memo": f"Balance {adjustment_type.lower()} - offset account",
            },
        ]


class JournalReversalInitiationForm(forms.Form):
    """
    Form for initiating a journal reversal
    """

    REVERSAL_TYPE_CHOICES = [
        ("full", "Full Reversal"),
        ("partial", "Partial Reversal"),
        ("correction", "Reversal with Correction"),
    ]

    reversal_type = forms.ChoiceField(
        choices=REVERSAL_TYPE_CHOICES,
        widget=forms.RadioSelect,
        label="Reversal Type",
        help_text="Select the type of reversal you want to perform",
    )

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Reason for reversal",
        help_text="Please provide a detailed reason for reversing this journal.",
    )


class JournalPartialReversalForm(forms.Form):
    """
    Form for partial journal reversal
    """

    def __init__(self, journal_entries, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.journal_entries = journal_entries

        # Add fields for each entry
        for entry in journal_entries:
            field_name = f"entry_{entry.id}"
            self.fields[field_name] = forms.BooleanField(
                required=False,
                label=f"{entry.account.name} - {entry.get_entry_type_display()} - {entry.amount}",
                help_text=f"Check to reverse this entry (Original: {entry.memo or 'No memo'})",
            )

            # Add amount field for partial amount reversal
            amount_field_name = f"amount_{entry.id}"
            self.fields[amount_field_name] = forms.DecimalField(
                required=False,
                min_value=0.01,
                max_digits=12,
                decimal_places=2,
                widget=forms.NumberInput(attrs={"step": "0.01"}),
                label=f"Amount to reverse (Max: {entry.amount})",
                help_text="Leave blank to reverse full amount",
            )

    def clean(self):
        cleaned_data = super().clean()
        has_selected_entries = False

        for entry in self.journal_entries:
            field_name = f"entry_{entry.id}"
            if cleaned_data.get(field_name):
                has_selected_entries = True
                amount_field_name = f"amount_{entry.id}"
                amount = cleaned_data.get(amount_field_name)
                if amount and amount > entry.amount:
                    self.add_error(
                        amount_field_name,
                        f"Amount cannot exceed original entry amount ({entry.amount})",
                    )

        if not has_selected_entries:
            raise forms.ValidationError("Please select at least one entry to reverse")

        return cleaned_data


class JournalCorrectionForm(forms.Form):
    """
    Form for reversal with correction entries
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We'll use JavaScript to dynamically add correction entry fields

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Reason for reversal and correction",
        help_text="Please provide a detailed reason for reversing and correcting this journal.",
    )


class CorrectionEntryForm(forms.Form):
    """
    Form for a single correction entry
    """

    account = forms.ModelChoiceField(
        queryset=Account.objects.all(),
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Account",
    )

    entry_type = forms.ChoiceField(
        choices=JournalEntry.EntryType.choices,
        widget=forms.RadioSelect,
        label="Entry Type",
    )

    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "class": "form-control"}),
        label="Amount",
    )

    memo = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Memo",
    )


# Create formset for correction entries
CorrectionEntryFormSet = formset_factory(
    CorrectionEntryForm,
    extra=2,
    can_delete=True,
    min_num=2,
    validate_min=True,
)


class BatchJournalReversalForm(forms.Form):
    """
    Form for batch journal reversal
    """

    journals = forms.ModelMultipleChoiceField(
        queryset=Journal.objects.filter(status=Journal.JournalStatus.POSTED),
        widget=forms.CheckboxSelectMultiple,
        label="Journals to Reverse",
        help_text="Select all journals you want to reverse",
    )

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Reason for batch reversal",
        help_text="Please provide a detailed reason for reversing these journals.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter out journals that are already reversed
        self.fields["journals"].queryset = Journal.objects.filter(
            status=Journal.JournalStatus.POSTED, reversed_journal__isnull=True
        ).select_related("period", "created_by")


class JournalReversalConfirmationForm(forms.Form):
    """
    Form for confirming journal reversal
    """

    confirm = forms.BooleanField(
        label="I confirm that I want to reverse this journal",
        help_text="This action cannot be undone. Please confirm you want to proceed.",
    )

    final_reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Final confirmation reason",
        help_text="Please restate the reason for this reversal for audit purposes.",
    )


class DisciplinaryCaseForm(forms.ModelForm):
    class Meta:
        model = DisciplinaryCase
        fields = [
            "allegation_summary",
            "allegation_details",
            "incident_date",
            "respondent",
            "violation_level",
            "emergency_case",
            "repeat_offense_suspected",
            "power_imbalance_flag",
            "conflict_of_interest_flag",
            "mental_health_context",
            "cultural_context",
            "interim_measures",
        ]
        widgets = {
            "incident_date": forms.DateInput(attrs={"type": "date"}),
            "allegation_details": forms.Textarea(attrs={"rows": 4}),
            "interim_measures": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            "w-full px-3 py-2 border border-secondary-300 rounded-md "
            "focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
        )
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "rounded border-secondary-300 text-primary-600"
            else:
                field.widget.attrs["class"] = base_class


class DisciplinaryEvidenceForm(forms.ModelForm):
    class Meta:
        model = DisciplinaryEvidence
        fields = [
            "title",
            "evidence_type",
            "description",
            "file",
            "is_confidential",
            "chain_of_custody_notes",
            "reliability_score",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "chain_of_custody_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            "w-full px-3 py-2 border border-secondary-300 rounded-md "
            "focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
        )
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "rounded border-secondary-300 text-primary-600"
            else:
                field.widget.attrs["class"] = base_class


class DisciplinaryDecisionForm(forms.ModelForm):
    class Meta:
        model = DisciplinaryCase
        fields = ["finding", "findings_summary", "decision_rationale"]
        widgets = {
            "findings_summary": forms.Textarea(attrs={"rows": 4}),
            "decision_rationale": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            "w-full px-3 py-2 border border-secondary-300 rounded-md "
            "focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = base_class


class DisciplinarySanctionForm(forms.ModelForm):
    class Meta:
        model = DisciplinarySanction
        fields = [
            "sanction_type",
            "rationale",
            "effective_date",
            "duration_days",
            "compliance_due_date",
            "is_rehabilitative",
        ]
        widgets = {
            "effective_date": forms.DateInput(attrs={"type": "date"}),
            "compliance_due_date": forms.DateInput(attrs={"type": "date"}),
            "rationale": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            "w-full px-3 py-2 border border-secondary-300 rounded-md "
            "focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
        )
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "rounded border-secondary-300 text-primary-600"
            else:
                field.widget.attrs["class"] = base_class


class DisciplinaryAppealForm(forms.ModelForm):
    class Meta:
        model = DisciplinaryAppeal
        fields = ["grounds", "details"]
        widgets = {
            "details": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            "w-full px-3 py-2 border border-secondary-300 rounded-md "
            "focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = base_class


class DisciplinaryAppealReviewForm(forms.ModelForm):
    class Meta:
        model = DisciplinaryAppeal
        fields = ["status", "outcome_notes"]
        widgets = {
            "outcome_notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            "w-full px-3 py-2 border border-secondary-300 rounded-md "
            "focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = base_class
