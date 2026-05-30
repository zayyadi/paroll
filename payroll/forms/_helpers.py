"""Form utility helpers extracted from monolithic forms.py."""

from calendar import monthrange
from decimal import Decimal
import json

from django import forms
from django.apps import apps
from django.utils import timezone


def _get_period_bounds(paydays):
    month_start = paydays.replace(day=1)
    month_end = month_start.replace(day=monthrange(paydays.year, paydays.month)[1])
    return month_start, month_end


def _employee_blocked_for_payday(employee, paydays):
    if not employee:
        return True, "missing employee"

    if employee.status == "terminated":
        return True, "terminated employee"

    user = employee.user
    if user and not user.is_active:
        return True, "disabled user account"

    DisciplinarySanction = apps.get_model("accounting", "DisciplinarySanction")
    period_start, period_end = _get_period_bounds(paydays)
    active_sanctions = DisciplinarySanction.objects.filter(
        case__respondent=user,
        status=DisciplinarySanction.Status.ACTIVE,
    )

    termination_exists = active_sanctions.filter(
        sanction_type=DisciplinarySanction.SanctionType.TERMINATION,
        effective_date__lte=period_end,
    ).exists()
    if termination_exists:
        return True, "terminated employee"

    for sanction in active_sanctions.filter(
        sanction_type=DisciplinarySanction.SanctionType.SUSPENSION,
        effective_date__lte=period_end,
    ):
        if sanction.overlaps_period(period_start, period_end):
            return True, "suspended in selected pay period"

    return False, ""


FORM_CONTROL_CLASS = (
    "w-full px-4 py-2.5 border border-secondary-300 rounded-xl "
    "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm bg-white"
)


def _apply_standard_widget_classes(fields):
    for field in fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = "h-4 w-4 rounded border-secondary-300 text-primary-600"
        else:
            field.widget.attrs["class"] = FORM_CONTROL_CLASS


def _parse_lines(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _parse_json_object(value, field_name):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise forms.ValidationError(f"{field_name} must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise forms.ValidationError(f"{field_name} must be a JSON object.")
    return parsed


def _normalize_month_widget_data(args, kwargs, field_name):
    data_source = args[0] if args else kwargs.get("data")
    if data_source is None:
        return args, kwargs

    data = data_source.copy()
    compact_value = data.get(field_name)
    month_key = f"{field_name}_0"
    year_key = f"{field_name}_1"
    if compact_value and not data.get(month_key) and not data.get(year_key):
        try:
            year, month = str(compact_value).split("-")[:2]
            data[month_key] = str(int(month))
            data[year_key] = str(int(year))
        except (TypeError, ValueError):
            pass
    if args:
        return (data, *args[1:]), kwargs
    kwargs["data"] = data
    return args, kwargs
