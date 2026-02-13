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


@register.filter(name="naturaltime")
def naturaltime(value):
    """
    Returns a human-readable string representing the time difference between now and value.
    Similar to Django's timesince filter but with more natural language.
    """
    from django.utils import timezone
    from datetime import timedelta

    if not value:
        return "Never"

    now = timezone.now()
    # Ensure both datetimes have the same timezone awareness
    # If value is timezone-aware, make sure now is also timezone-aware
    # If value is timezone-naive, make now timezone-naive
    if timezone.is_aware(value):
        if not timezone.is_aware(now):
            now = timezone.make_aware(now, timezone.utc)
    else:
        if timezone.is_aware(now):
            now = timezone.make_naive(now)

    diff = now - value

    if diff < timedelta(minutes=1):
        return "Just now"
    elif diff < timedelta(hours=1):
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif diff < timedelta(hours=24):
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff < timedelta(days=7):
        days = int(diff.total_seconds() / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    elif diff < timedelta(days=30):
        weeks = int(diff.total_seconds() / (86400 * 7))
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    elif diff < timedelta(days=365):
        months = int(diff.total_seconds() / (86400 * 30))
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        years = int(diff.total_seconds() / (86400 * 365))
        return f"{years} year{'s' if years != 1 else ''} ago"


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
