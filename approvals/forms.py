from django import forms
from django.forms import formset_factory
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import ApprovalPolicy
from .registry import registered_actions, get_action
from .presentation import action_label


class PolicyForm(forms.ModelForm):
    class Meta:
        model = ApprovalPolicy
        fields = ["name", "action", "enabled", "minimum_amount", "currency"]
        labels = {
            "minimum_amount": "Apply from amount",
            "currency": "Currency (for example NGN)",
        }

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.company = company
        self.fields["action"] = forms.ChoiceField(
            choices=[(key, action_label(key)) for key in registered_actions()]
        )

    def _post_clean(self):
        # Ordered stages are attached after formset validation by the view.
        action = self.cleaned_data.get("action")
        self.instance.stages = (
            [{"permission": get_action(action).permission}] if action else []
        )
        super()._post_clean()


class StageForm(forms.Form):
    name = forms.CharField(max_length=100, required=False, label="Stage name")
    require_authority = forms.BooleanField(
        required=False,
        initial=True,
        label="Use action approval permission when no approvers are selected",
    )
    approvers = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.none(),
        required=False,
        label="Designated approvers (optional)",
        help_text="When selected, only these company members may decide this stage.",
    )

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["approvers"].queryset = (
            get_user_model()
            .objects.filter(is_active=True)
            .filter(Q(company=company) | Q(company_memberships__company=company))
            .distinct()
            .order_by("email")
        )

    def clean(self):
        data = super().clean()
        if (
            not data.get("DELETE")
            and not data.get("require_authority")
            and not data.get("approvers")
        ):
            raise forms.ValidationError(
                "Select action authority or designated approvers."
            )
        return data


StageFormSet = formset_factory(
    StageForm,
    extra=1,
    min_num=1,
    max_num=10,
    validate_min=True,
    validate_max=True,
    can_delete=True,
    can_order=True,
)
