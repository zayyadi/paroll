from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.models import Account, AccountingPeriod, FiscalYear, Journal, JournalEntry
from company.models import Company
from company.utils import get_user_companies, get_user_company, set_active_company
from payroll.models import (
    Department,
    EmployeeProfile,
    IOU,
    LeavePolicy,
    LeaveRequest,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
)

from api.v1.permissions import CanMutateAccounting, IsAccountingRole, IsTenantMember
from api.v1.serializers import (
    AccountSerializer,
    AccountingPeriodSerializer,
    CompanyMembershipSerializer,
    DepartmentSerializer,
    EmployeeProfileSerializer,
    FiscalYearSerializer,
    IOUSerializer,
    JournalEntrySerializer,
    JournalSerializer,
    LeavePolicySerializer,
    LeaveRequestSerializer,
    PayrollEntrySerializer,
    PayrollRunEntrySerializer,
    PayrollRunSerializer,
    PayrollSerializer,
)


class TenantScopedModelViewSet(viewsets.ModelViewSet):
    """
    Generic company-scoped viewset.
    Set `company_filter_path` when company is accessible via relation.
    """

    permission_classes = [IsAuthenticated, IsTenantMember, DjangoModelPermissions]
    company_filter_path = "company"

    def get_company(self):
        return get_user_company(self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset()
        company = self.get_company()
        if company is None:
            return queryset.none()
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(**{self.company_filter_path: company})

    def perform_create(self, serializer):
        company = self.get_company()
        if company is None:
            serializer.save()
            return

        field_name = self.company_filter_path.split("__")[0]
        model_fields = {field.name for field in serializer.Meta.model._meta.get_fields()}
        if field_name in model_fields:
            serializer.save(**{field_name: company})
        else:
            serializer.save()


class SuperuserOnlyAccountingMixin:
    """
    Temporary safety gate for accounting APIs until models are fully tenant-scoped.
    """

    def _ensure_superuser(self):
        if not self.request.user.is_superuser:
            raise PermissionDenied(
                "Accounting API access is temporarily restricted to superusers."
            )


class DepartmentViewSet(TenantScopedModelViewSet):
    queryset = Department.objects.all().order_by("name")
    serializer_class = DepartmentSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]


class EmployeeViewSet(TenantScopedModelViewSet):
    queryset = (
        EmployeeProfile.objects.select_related("department", "user", "company")
        .all()
        .order_by("-created")
    )
    serializer_class = EmployeeProfileSerializer
    search_fields = ["first_name", "last_name", "email", "emp_id"]
    ordering_fields = ["created", "first_name", "last_name"]

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated, IsTenantMember])
    def me(self, request):
        employee = get_object_or_404(self.get_queryset(), user=request.user)
        serializer = self.get_serializer(employee)
        return Response(serializer.data)


class PayrollViewSet(TenantScopedModelViewSet):
    queryset = Payroll.objects.all().order_by("-timestamp")
    serializer_class = PayrollSerializer
    search_fields = ["status"]
    ordering_fields = ["timestamp", "updated", "basic_salary"]


class PayrollEntryViewSet(TenantScopedModelViewSet):
    queryset = PayrollEntry.objects.select_related("pays", "company").all().order_by("-id")
    serializer_class = PayrollEntrySerializer
    search_fields = ["pays__first_name", "pays__last_name", "status"]
    ordering_fields = ["id", "netpay"]


class PayrollRunViewSet(TenantScopedModelViewSet):
    queryset = PayrollRun.objects.all().order_by("-paydays")
    serializer_class = PayrollRunSerializer
    search_fields = ["name", "slug"]
    ordering_fields = ["paydays", "name"]

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        payroll_run = self.get_object()
        if payroll_run.closed:
            return Response(
                {"detail": "Payroll run is already closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payroll_run.closed = True
        payroll_run.save(update_fields=["closed"])
        return Response({"detail": "Payroll run closed successfully."})


class PayrollRunEntryViewSet(TenantScopedModelViewSet):
    queryset = (
        PayrollRunEntry.objects.select_related("payroll_run", "payroll_entry", "payroll_entry__company")
        .all()
        .order_by("-id")
    )
    serializer_class = PayrollRunEntrySerializer
    company_filter_path = "payroll_entry__company"
    ordering_fields = ["id", "payroll_run"]


class LeavePolicyViewSet(TenantScopedModelViewSet):
    queryset = LeavePolicy.objects.all().order_by("leave_type")
    serializer_class = LeavePolicySerializer
    ordering_fields = ["leave_type", "max_days"]


class LeaveRequestViewSet(TenantScopedModelViewSet):
    queryset = LeaveRequest.objects.select_related("employee", "approved_by").all().order_by("-created_at")
    serializer_class = LeaveRequestSerializer
    company_filter_path = "employee__company"
    search_fields = ["employee__first_name", "employee__last_name", "leave_type", "status"]
    ordering_fields = ["created_at", "start_date", "end_date", "status"]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        leave_request = self.get_object()
        leave_request.status = "APPROVED"
        leave_request.approved_by = request.user
        leave_request.save(user=request.user)
        return Response({"detail": "Leave request approved."})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        leave_request = self.get_object()
        leave_request.status = "REJECTED"
        leave_request.approved_by = request.user
        leave_request.save(user=request.user)
        return Response({"detail": "Leave request rejected."})


class IOUViewSet(TenantScopedModelViewSet):
    queryset = IOU.objects.select_related("employee_id").all().order_by("-created_at")
    serializer_class = IOUSerializer
    company_filter_path = "employee_id__company"
    search_fields = ["employee_id__first_name", "employee_id__last_name", "status"]
    ordering_fields = ["created_at", "amount", "status", "due_date"]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        iou = self.get_object()
        iou.status = "APPROVED"
        iou.approved_at = timezone.now().date()
        iou.save()
        return Response({"detail": "IOU approved."})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        iou = self.get_object()
        iou.status = "REJECTED"
        iou.save()
        return Response({"detail": "IOU rejected."})

    @action(detail=True, methods=["post"])
    def mark_paid(self, request, pk=None):
        iou = self.get_object()
        iou.status = "PAID"
        iou.save()
        return Response({"detail": "IOU marked as paid."})


class AccountViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = Account.objects.all().order_by("account_number", "name")
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["name", "account_number", "type"]
    ordering_fields = ["account_number", "name", "created_at"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset


class FiscalYearViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = FiscalYear.objects.all().order_by("-year")
    serializer_class = FiscalYearSerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["year", "name"]
    ordering_fields = ["year", "start_date", "end_date"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        self._ensure_superuser()
        fiscal_year = self.get_object()
        fiscal_year.close(request.user)
        return Response({"detail": "Fiscal year closed."})


class AccountingPeriodViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = AccountingPeriod.objects.select_related("fiscal_year").all().order_by("-fiscal_year__year", "-period_number")
    serializer_class = AccountingPeriodSerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["name", "fiscal_year__name"]
    ordering_fields = ["period_number", "start_date", "end_date"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        self._ensure_superuser()
        period = self.get_object()
        period.close(request.user)
        return Response({"detail": "Accounting period closed."})


class JournalViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = Journal.objects.select_related("period", "created_by", "approved_by", "posted_by").prefetch_related("entries").all().order_by("-created_at")
    serializer_class = JournalSerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["transaction_number", "description", "status"]
    ordering_fields = ["created_at", "date", "status"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset

    def perform_create(self, serializer):
        self._ensure_superuser()
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        self._ensure_superuser()
        journal = self.get_object()
        journal.submit_for_approval()
        return Response({"detail": "Journal submitted for approval."})

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        self._ensure_superuser()
        journal = self.get_object()
        journal.approve(request.user)
        return Response({"detail": "Journal approved."})

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        self._ensure_superuser()
        journal = self.get_object()
        journal.post(request.user)
        return Response({"detail": "Journal posted."})

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        self._ensure_superuser()
        journal = self.get_object()
        reason = request.data.get("reason", "").strip() or "API reversal"
        reversal = journal.reverse(request.user, reason)
        data = self.get_serializer(reversal).data
        return Response(data, status=status.HTTP_201_CREATED)


class JournalEntryViewSet(SuperuserOnlyAccountingMixin, TenantScopedModelViewSet):
    queryset = JournalEntry.objects.select_related("journal", "account", "created_by").all().order_by("-created_at")
    serializer_class = JournalEntrySerializer
    permission_classes = [IsAuthenticated, IsAccountingRole, CanMutateAccounting]
    company_filter_path = ""
    search_fields = ["journal__transaction_number", "account__name", "entry_type"]
    ordering_fields = ["created_at", "amount"]

    def get_queryset(self):
        self._ensure_superuser()
        return self.queryset

    def perform_create(self, serializer):
        self._ensure_superuser()
        serializer.save(created_by=self.request.user)


class AuthContextView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = get_user_company(request.user)
        memberships = request.user.company_memberships.select_related("company").all()
        serializer = CompanyMembershipSerializer(memberships, many=True)
        return Response(
            {
                "user": {
                    "id": request.user.id,
                    "email": request.user.email,
                    "first_name": request.user.first_name,
                    "last_name": request.user.last_name,
                },
                "active_company": (
                    {"id": company.id, "name": company.name, "slug": company.slug}
                    if company
                    else None
                ),
                "memberships": serializer.data,
            }
        )


class SwitchCompanyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = request.data.get("company_id")
        company = get_object_or_404(Company, pk=company_id, is_active=True)
        if not set_active_company(request.user, company):
            return Response(
                {"detail": "You do not have access to this company."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            {
                "detail": "Active company updated.",
                "active_company": {
                    "id": company.id,
                    "name": company.name,
                    "slug": company.slug,
                },
            }
        )


class MyCompaniesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        companies = get_user_companies(request.user)
        data = [{"id": c.id, "name": c.name, "slug": c.slug} for c in companies]
        return Response({"results": data})
