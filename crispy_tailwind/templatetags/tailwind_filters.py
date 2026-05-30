from django import template


register = template.Library()


@register.filter
def crispy(value):
    return value


@register.filter
def as_crispy_field(value):
    return value

__all__ = ["as_crispy_field", "crispy"]
