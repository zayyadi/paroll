from django import template

register = template.Library()


@register.filter
def index(sequence, position):
    try:
        return sequence[position]
    except IndexError:
        return ""


@register.filter(name="mask_account_number")
def mask_account_number(value):
    if len(value) > 4:
        return "*" * (len(value) - 4) + value[-4:]
    else:
        return value


@register.filter(name="format_field_name")
def format_field_name(value):
    """
    Replaces underscores with spaces and capitalizes the first letter of each word.
    """
    return value.replace("_", " ").title()


@register.filter
def multiply(value, arg):
    """Multiplies the value by the arg."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ""


@register.filter
def subtract(value, arg):
    """Subtracts the arg from the value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return ""


@register.filter
def add(value, arg):
    """Adds the value and the arg."""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return ""


@register.filter
def divide(value, arg):
    """Divides the value by the arg."""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return ""
