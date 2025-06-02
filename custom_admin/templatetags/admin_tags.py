# custom_admin/templatetags/admin_tags.py
from django import template
from django.db import models
from django.urls import reverse, NoReverseMatch
from custom_admin.admin_config import registered_models # Import registered_models

register = template.Library()

@register.filter
def is_boolean_field(obj, field_name_str):
    try:
        # Ensure obj is a model instance and has _meta attribute
        if not hasattr(obj, '_meta'):
            return False
        field = obj._meta.get_field(field_name_str)
        return isinstance(field, (models.BooleanField, models.NullBooleanField))
    except Exception: # Handles cases where field_name_str might not be a valid field
        return False

@register.filter(name='get_field_value') # Explicitly naming the filter
def get_field_value(obj, field_name_str): # Renamed from getattr_filter
    try:
        # Check for properties or methods first
        # Ensure name is a string as field_name_str might be passed as something else from template
        name_str = str(field_name_str)
        if hasattr(obj, name_str) and callable(getattr(obj, name_str)):
            # Check if it's a property that is not a method
            # A common way to check for property is to see if it's an instance of `property`
            # However, direct callable check is more straightforward for simple cases.
            # For true model properties (defined with @property), direct getattr(obj, name_str) works.
            # If it's a method that needs to be called (e.g. get_absolute_url), then call it.
            # Let's assume if it's callable and not a field, it's a method to be called.
            # This might need refinement if properties are complex.
            
            # Simplified: if it's callable, call it. If not, access it.
            # If it's a field, direct getattr below will get its value.
            # If it's a property, direct getattr will get its value.
            # If it's a method to be called for display, then call it.
            
            # A robust way is to check if it is a field first.
            if hasattr(obj, '_meta') and name_str in [f.name for f in obj._meta.get_fields()]:
                 return getattr(obj, name_str) # It's a field, get its value

            # If not a field, and it's callable, call it
            if callable(getattr(obj, name_str)):
                 return getattr(obj, name_str)()

            # Otherwise, it's an attribute or property
            return getattr(obj, name_str)
            
    except AttributeError:
        return None 
    except Exception as e:
        # Optionally log other errors for debugging
        # print(f"Error in get_field_value: {e} while trying to get {field_name_str} from {obj}")
        return None

@register.filter
def is_foreign_key_or_one_to_one_field(obj, field_name_str):
    try:
        if not hasattr(obj, '_meta'):
            return False
        field = obj._meta.get_field(field_name_str)
        return isinstance(field, (models.ForeignKey, models.OneToOneField))
    except Exception:
        return False

@register.filter
def get_custom_admin_edit_url(related_obj_instance):
    if not hasattr(related_obj_instance, '_meta') or not hasattr(related_obj_instance, 'pk'):
        return None
    
    app_label = related_obj_instance._meta.app_label
    model_name = related_obj_instance._meta.model_name

    # Check if the related model is registered in our custom admin
    is_registered = False
    if app_label in registered_models:
        for model_info in registered_models[app_label]:
            if model_info['model_name'] == model_name:
                is_registered = True
                break
    if not is_registered:
        return None

    # Try specific URL pattern first (e.g., 'custom_admin:payroll_employeeprofile_update')
    try:
        # Convention: app_label and model_name in the URL are lowercased by Django by default
        # but URL names might be defined differently. Let's assume they are lowercase.
        url_name = f'custom_admin:{app_label.lower()}_{model_name.lower()}_update'
        return reverse(url_name, kwargs={'pk': related_obj_instance.pk})
    except NoReverseMatch:
        # Fallback to generic URL pattern
        try:
            url_name = 'custom_admin:generic_update'
            return reverse(url_name, kwargs={'app_label': app_label, 'model_name': model_name, 'pk': related_obj_instance.pk})
        except NoReverseMatch:
            return None # No suitable URL found

@register.filter
def is_date_field_filter(obj, field_name_str):
    try:
        if not hasattr(obj, '_meta'): return False
        field = obj._meta.get_field(field_name_str)
        # Check specifically for DateField and not DateTimeField
        return isinstance(field, models.DateField) and not isinstance(field, models.DateTimeField)
    except Exception:
        return False

@register.filter
def is_datetime_field_filter(obj, field_name_str):
    try:
        if not hasattr(obj, '_meta'): return False
        field = obj._meta.get_field(field_name_str)
        return isinstance(field, models.DateTimeField)
    except Exception:
        return False

@register.filter
def is_numeric_field_filter(obj, field_name_str):
    try:
        if not hasattr(obj, '_meta'): return False
        field = obj._meta.get_field(field_name_str)
        return isinstance(field, (
            models.IntegerField, models.FloatField, models.DecimalField,
            models.AutoField, models.BigAutoField, models.SmallIntegerField,
            models.PositiveIntegerField, models.PositiveSmallIntegerField,
            models.BigIntegerField
        ))
    except Exception:
        return False
