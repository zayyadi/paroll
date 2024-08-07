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
