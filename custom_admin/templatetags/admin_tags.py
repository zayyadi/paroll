# custom_admin/templatetags/admin_tags.py
from django import template

register = template.Library()

@register.filter(name='getattr_filter') # Explicitly naming the filter
def getattr_filter(obj, name):
    try:
        return getattr(obj, str(name)) # Ensure name is a string
    except AttributeError:
        return None # Or '' or some default
    except Exception as e:
        # Optionally log other errors for debugging
        print(f"Error in getattr_filter: {e} while trying to get {name} from {obj}")
        return None
