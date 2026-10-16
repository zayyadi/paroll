"""Normalize domain workflow validation for existing DRF action endpoints."""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

def workflow_exception_handler(exc,context):
    if isinstance(exc,DjangoValidationError):
        exc=ValidationError(exc.message_dict if hasattr(exc,'message_dict') else {'detail':exc.messages})
    return exception_handler(exc,context)
