from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


def _number(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


@register.filter
def div(value, arg):
    divisor = _number(arg)
    if divisor == 0:
        return Decimal("0")
    return _number(value) / divisor


@register.filter
def mul(value, arg):
    return _number(value) * _number(arg)


@register.filter
def sub(value, arg):
    return _number(value) - _number(arg)


@register.filter
def abs(value):
    return builtins_abs(_number(value))


builtins_abs = __builtins__["abs"] if isinstance(__builtins__, dict) else __builtins__.abs
