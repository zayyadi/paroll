from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from .models.payroll import IOU
from . import models # For EmployeeProfile
# from .forms import IOUCreateForm, IOUUpdateForm, IOUDeleteForm # Removed
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden


# Helper functions
def check_super(user):
    return user.is_superuser

def is_hr_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.groups.filter(name='HR').exists())
