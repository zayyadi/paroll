from __future__ import annotations

from rest_framework.permissions import BasePermission, SAFE_METHODS

from accounting.permissions import is_accountant, is_auditor, is_payroll_processor
from company.utils import get_user_company


class IsTenantMember(BasePermission):
    """
    Allows only authenticated users with an active company (or superusers).
    """

    message = "No active company is configured for this account."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return get_user_company(user) is not None


class IsAccountingRole(BasePermission):
    """
    Access for accounting role holders or superusers.
    """

    message = "You need an accounting role to access this endpoint."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return (
            user.is_superuser
            or is_accountant(user)
            or is_auditor(user)
            or is_payroll_processor(user)
        )


class CanMutateAccounting(BasePermission):
    """
    Read for accounting roles, write for accountant/payroll-processor/superuser.
    """

    message = "You do not have permission to modify accounting resources."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return (
                user.is_superuser
                or is_accountant(user)
                or is_auditor(user)
                or is_payroll_processor(user)
            )
        return user.is_superuser or is_accountant(user) or is_payroll_processor(user)
