from django.conf import settings
from django.contrib.auth.mixins import AccessMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
import sys
from company.utils import get_user_company
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


def _is_accounting_lockdown_enabled(user):
    return (
        settings.ACCOUNTING_SUPERUSER_ONLY_UNTIL_TENANT_SCOPED
        and "test" not in sys.argv
        and user.is_authenticated
        and not user.is_superuser
    )


class TenantScopedPermissionObjectMixin:
    permission_object_model = None

    def get_permission_queryset(self):
        if self.permission_object_model is None:
            raise AttributeError(
                f"{self.__class__.__name__} must define permission_object_model."
            )

        queryset = self.permission_object_model.objects.all()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return queryset

        company = get_user_company(user)
        if company is None:
            return queryset.none()

        if hasattr(self.permission_object_model, "company_id"):
            return queryset.filter(company=company)
        if hasattr(self.permission_object_model, "journal"):
            return queryset.filter(journal__company=company)
        if hasattr(self.permission_object_model, "fiscal_year"):
            return queryset.filter(fiscal_year__company=company)
        return queryset.none()

    def get_permission_object(self):
        if hasattr(self, "_permission_object"):
            return self._permission_object

        if hasattr(self, "get_object"):
            obj = self.get_object()
        elif self.permission_object_model and "pk" in self.kwargs:
            obj = get_object_or_404(self.get_permission_queryset(), pk=self.kwargs["pk"])
        else:
            raise AttributeError(
                f"{self.__class__.__name__} must define get_object() or permission_object_model."
            )

        self._permission_object = obj
        return obj


class AuditorRequiredMixin(AccessMixin):
    """
    Mixin to ensure user has auditor role
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if _is_accounting_lockdown_enabled(request.user):
            return HttpResponseForbidden(
                "Accounting access is temporarily restricted to superusers until tenant scoping is complete."
            )

        if not is_auditor(request.user):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden()
        return super().handle_no_permission()


class AccountantRequiredMixin(AccessMixin):
    """
    Mixin to ensure user has accountant role
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if _is_accounting_lockdown_enabled(request.user):
            return HttpResponseForbidden(
                "Accounting access is temporarily restricted to superusers until tenant scoping is complete."
            )

        if not is_accountant(request.user):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden()
        return super().handle_no_permission()


class PayrollProcessorRequiredMixin(AccessMixin):
    """
    Mixin to ensure user has payroll processor role
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if _is_accounting_lockdown_enabled(request.user):
            return HttpResponseForbidden(
                "Accounting access is temporarily restricted to superusers until tenant scoping is complete."
            )

        if not is_payroll_processor(request.user):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden()
        return super().handle_no_permission()


class AccountingRoleRequiredMixin(AccessMixin):
    """
    Mixin to ensure user has any accounting role
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if _is_accounting_lockdown_enabled(request.user):
            return HttpResponseForbidden(
                "Accounting access is temporarily restricted to superusers until tenant scoping is complete."
            )

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

        if _is_accounting_lockdown_enabled(request.user):
            return HttpResponseForbidden(
                "Accounting access is temporarily restricted to superusers until tenant scoping is complete."
            )

        if not (is_auditor(request.user) or is_accountant(request.user)):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)


class JournalApprovalMixin(TenantScopedPermissionObjectMixin, UserPassesTestMixin):
    """
    Mixin to check if user can approve a journal
    """

    def test_func(self):
        if _is_accounting_lockdown_enabled(self.request.user):
            return False
        if self.request.user.is_superuser:
            return True
        journal = self.get_permission_object()
        return can_approve_journal(self.request.user, journal)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden(
                "You don't have permission to approve this journal."
            )
        return redirect("login")


class JournalReversalMixin(TenantScopedPermissionObjectMixin, UserPassesTestMixin):
    """
    Mixin to check if user can reverse a journal
    """

    def test_func(self):
        if _is_accounting_lockdown_enabled(self.request.user):
            return False
        journal = self.get_permission_object()
        return can_reverse_journal(self.request.user, journal)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseForbidden(
                "You don't have permission to reverse this journal."
            )
        return redirect("login")


class PeriodClosingMixin(TenantScopedPermissionObjectMixin, UserPassesTestMixin):
    """
    Mixin to check if user can close an accounting period
    """

    def test_func(self):
        if _is_accounting_lockdown_enabled(self.request.user):
            return False
        period = self.get_permission_object()
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
        if _is_accounting_lockdown_enabled(self.request.user):
            return False
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
        if _is_accounting_lockdown_enabled(self.request.user):
            return False
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
        if _is_accounting_lockdown_enabled(self.request.user):
            return False
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

        if _is_accounting_lockdown_enabled(request.user):
            return HttpResponseForbidden(
                "Accounting access is temporarily restricted to superusers until tenant scoping is complete."
            )

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

        if _is_accounting_lockdown_enabled(request.user):
            return HttpResponseForbidden(
                "Accounting access is temporarily restricted to superusers until tenant scoping is complete."
            )

        if not can_manage_disciplinary_case(request.user):
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)
