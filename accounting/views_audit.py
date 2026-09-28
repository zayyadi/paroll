"""Company-scoped accounting audit-trail views.

First slice of the accounting/views.py god-file split (3816 lines).
Import path stays backward compatible: accounting.views re-exports these.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView

from company.utils import get_user_company
from users.models import CustomUser as UserModel

from .mixins import AuditorOrFinanceReadMixin
from .models import AccountingAuditTrail


class AuditTrailListView(LoginRequiredMixin, AuditorOrFinanceReadMixin, ListView):
    """List audit trail entries scoped to the caller's company."""

    model = AccountingAuditTrail
    template_name = "accounting/audit_trail_list.html"
    context_object_name = "audit_logs"
    paginate_by = 20

    def get_queryset(self):
        company = get_user_company(self.request.user)
        if company is None:
            return AccountingAuditTrail.objects.none()
        queryset = AccountingAuditTrail.objects.filter(company=company).order_by(
            "-timestamp"
        )

        user_id = self.request.GET.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id, user__company=company)

        action = self.request.GET.get("action")
        if action:
            queryset = queryset.filter(action=action)

        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action_choices"] = AccountingAuditTrail.ActionType.choices
        company = get_user_company(self.request.user)
        if company is None:
            context["users"] = UserModel.objects.none()
        else:
            context["users"] = UserModel.objects.filter(company=company)
        return context


class AuditTrailDetailView(LoginRequiredMixin, AuditorOrFinanceReadMixin, DetailView):
    """View audit trail entry details scoped to the caller's company."""

    model = AccountingAuditTrail
    template_name = "accounting/audit_trail_detail.html"
    context_object_name = "audit_log"

    def get_queryset(self):
        company = get_user_company(self.request.user)
        if company is None:
            return AccountingAuditTrail.objects.none()
        return AccountingAuditTrail.objects.filter(company=company)
