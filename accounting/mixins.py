from django.contrib.auth.mixins import AccessMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from .permissions import (
    is_auditor,
    is_accountant,
    is_payroll_processor,
    can_access_disciplinary,
    can_manage_disciplinary_case,
    can_approve_journal,
    can_reverse_journal,
    can_close_period,
    can_view_payroll_data,
    can_modify_payroll_data,
)


class AuditorRequiredMixin(AccessMixin):
    """
    Mixin to ensure user has auditor role
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not is_auditor(request.user):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)


class AccountantRequiredMixin(AccessMixin):
    """
    Mixin to ensure user has accountant role
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not is_accountant(request.user):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)


class PayrollProcessorRequiredMixin(AccessMixin):
    """
    Mixin to ensure user has payroll processor role
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not is_payroll_processor(request.user):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)


class AccountingRoleRequiredMixin(AccessMixin):
    """
    Mixin to ensure user has any accounting role
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not (
            is_auditor(request.user)
            or is_accountant(request.user)
            or is_payroll_processor(request.user)
        ):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)


class AuditorOrAccountantRequiredMixin(AccessMixin):
    """
    Mixin to ensure user has auditor or accountant role
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not (is_auditor(request.user) or is_accountant(request.user)):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)


class JournalApprovalMixin(UserPassesTestMixin):
    """
    Mixin to check if user can approve a journal
    """

    def test_func(self):
        journal = self.get_object()
        return can_approve_journal(self.request.user, journal)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden(
                "You don't have permission to approve this journal."
            )
        return redirect("login")


class JournalReversalMixin(UserPassesTestMixin):
    """
    Mixin to check if user can reverse a journal
    """

    def test_func(self):
        journal = self.get_object()
        return can_reverse_journal(self.request.user, journal)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden(
                "You don't have permission to reverse this journal."
            )
        return redirect("login")


class PeriodClosingMixin(UserPassesTestMixin):
    """
    Mixin to check if user can close an accounting period
    """

    def test_func(self):
        period = self.get_object()
        return can_close_period(self.request.user, period)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden(
                "You don't have permission to close this period."
            )
        return redirect("login")


class PayrollViewMixin(UserPassesTestMixin):
    """
    Mixin to check if user can view payroll data
    """

    def test_func(self):
        return can_view_payroll_data(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden(
                "You don't have permission to view payroll data."
            )
        return redirect("login")


class PayrollModifyMixin(UserPassesTestMixin):
    """
    Mixin to check if user can modify payroll data
    """

    def test_func(self):
        return can_modify_payroll_data(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden(
                "You don't have permission to modify payroll data."
            )
        return redirect("login")


class SelfModificationMixin(UserPassesTestMixin):
    """
    Mixin to prevent users from modifying their own journals
    """

    def test_func(self):
        if is_auditor(self.request.user):
            return True  # Auditors can modify any journal

        journal = self.get_object()
        return journal.created_by != self.request.user

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden("You cannot modify your own journal.")
        return redirect("login")


class DisciplineAccessRequiredMixin(AccessMixin):
    """
    Mixin to ensure user can access disciplinary pages.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not can_access_disciplinary(request.user):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)


class DisciplineManagerRequiredMixin(AccessMixin):
    """
    Mixin to ensure user can manage disciplinary decisions/sanctions/appeals.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not can_manage_disciplinary_case(request.user):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)
