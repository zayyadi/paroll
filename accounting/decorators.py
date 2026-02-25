# from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib import messages
from .permissions import (
    is_auditor,
    is_accountant,
    is_payroll_processor,
    can_access_disciplinary,
    can_manage_disciplinary_case,
    can_reverse_journal,
    can_partial_reverse_journal,
    can_reverse_with_correction,
    can_batch_reverse_journals,
)


def auditor_required(view_func):
    """
    Decorator to ensure user has auditor role
    """

    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")

        if not is_auditor(request.user):
            return HttpResponseForbidden("Access denied. Auditor role required.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def accountant_required(view_func):
    """
    Decorator to ensure user has accountant role
    """

    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")

        if not is_accountant(request.user):
            return HttpResponseForbidden("Access denied. Accountant role required.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def payroll_processor_required(view_func):
    """
    Decorator to ensure user has payroll processor role
    """

    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")

        if not is_payroll_processor(request.user):
            return HttpResponseForbidden(
                "Access denied. Payroll Processor role required."
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def reversal_required(view_func=None):
    """
    Decorator to ensure user has permission to reverse journals
    """

    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            journal_id = kwargs.get("pk")
            if journal_id:
                from .models import Journal

                try:
                    journal = Journal.objects.get(pk=journal_id)
                    if not can_reverse_journal(request.user, journal):
                        messages.error(
                            request,
                            "You don't have permission to reverse this journal.",
                        )
                        return redirect("accounting:journal_detail", pk=journal_id)
                except Journal.DoesNotExist:
                    messages.error(request, "Journal not found.")
                    return redirect("accounting:journal_list")
            else:
                if not can_batch_reverse_journals(request.user):
                    messages.error(
                        request, "You don't have permission to perform batch reversals."
                    )
                    return redirect("accounting:journal_list")

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    if view_func:
        return decorator(view_func)
    return decorator


def partial_reversal_required(view_func=None):
    """
    Decorator to ensure user has permission to partially reverse journals
    """

    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            journal_id = kwargs.get("pk")
            if journal_id:
                from .models import Journal

                try:
                    journal = Journal.objects.get(pk=journal_id)
                    if not can_partial_reverse_journal(request.user, journal):
                        messages.error(
                            request,
                            "You don't have permission to partially reverse this journal.",
                        )
                        return redirect("accounting:journal_detail", pk=journal_id)
                except Journal.DoesNotExist:
                    messages.error(request, "Journal not found.")
                    return redirect("accounting:journal_list")

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    if view_func:
        return decorator(view_func)
    return decorator


def reversal_with_correction_required(view_func=None):
    """
    Decorator to ensure user has permission to reverse with correction
    """

    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            journal_id = kwargs.get("pk")
            if journal_id:
                from .models import Journal

                try:
                    journal = Journal.objects.get(pk=journal_id)
                    if not can_reverse_with_correction(request.user, journal):
                        messages.error(
                            request,
                            "You don't have permission to reverse with correction this journal.",
                        )
                        return redirect("accounting:journal_detail", pk=journal_id)
                except Journal.DoesNotExist:
                    messages.error(request, "Journal not found.")
                    return redirect("accounting:journal_list")

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    if view_func:
        return decorator(view_func)
    return decorator


def accounting_role_required(view_func):
    """
    Decorator to ensure user has any accounting role (auditor, accountant, or payroll processor)
    """

    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")

        if not (
            is_auditor(request.user)
            or is_accountant(request.user)
            or is_payroll_processor(request.user)
        ):
            return HttpResponseForbidden("Access denied. Accounting role required.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def auditor_or_accountant_required(view_func):
    """
    Decorator to ensure user has auditor or accountant role
    """

    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")

        if not (is_auditor(request.user) or is_accountant(request.user)):
            return HttpResponseForbidden(
                "Access denied. Auditor or Accountant role required."
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def discipline_access_required(view_func):
    """
    Decorator to ensure user can access disciplinary pages.
    """

    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")

        if not can_access_disciplinary(request.user):
            return HttpResponseForbidden(
                "Access denied. Disciplinary access role required."
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def discipline_manager_required(view_func):
    """
    Decorator to ensure user can manage disciplinary decisions/sanctions/appeals.
    """

    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")

        if not can_manage_disciplinary_case(request.user):
            return HttpResponseForbidden(
                "Access denied. Disciplinary manager role required."
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view
