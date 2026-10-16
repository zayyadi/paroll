"""Own-request API access and authenticated maker binding for HR workflows."""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied, ValidationError
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError as APIValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from approvals.permissions import user_in_company, has_company_permission
from company.utils import get_user_company

class HRRequestPermission(BasePermission):
    def has_permission(self, request, view):
        company = get_user_company(request.user)
        if not user_in_company(request.user, company):
            return False
        if view.action in {"approve", "reject", "mark_paid"}:
            return view.can_manage_requests()
        return True

    def has_object_permission(self, request, view, obj):
        employee = getattr(obj, view.hr_employee_field)
        if employee.company_id != get_user_company(request.user).pk:
            return False
        if view.can_manage_requests():
            return True
        return employee.user_id == request.user.pk and (request.method in {"GET", "HEAD", "OPTIONS"} or obj.status == "PENDING")

class HRRequestAPIMixin:
    permission_classes = [IsAuthenticated, HRRequestPermission]

    def can_manage_requests(self):
        model_name = self.serializer_class.Meta.model._meta.model_name
        return has_company_permission(self.request.user, get_user_company(self.request.user), "payroll.change_" + model_name)

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.can_manage_requests():
            queryset = queryset.filter(**{self.hr_employee_field + "__user": self.request.user})
        return queryset

    def _validate_employee(self, serializer):
        employee = serializer.validated_data.get(self.hr_employee_field)
        if employee is None and serializer.instance:
            employee = getattr(serializer.instance, self.hr_employee_field)
        company = get_user_company(self.request.user)
        if employee is None or employee.company_id != company.pk:
            raise APIValidationError({self.hr_employee_field:"Employee must belong to the active company."})
        if not self.can_manage_requests() and employee.user_id != self.request.user.pk:
            raise PermissionDenied("You may submit or edit only your own requests.")
        return employee

    @transaction.atomic
    def perform_create(self, serializer):
        from payroll.services.hr_workflow import submit_hr_request
        self._validate_employee(serializer)
        try:
            source = serializer.save(requested_by=self.request.user)
            submit_hr_request(source, self.request.user)
        except ValidationError as exc:
            raise APIValidationError({"detail":exc.messages}) from exc

    @transaction.atomic
    def perform_update(self, serializer):
        from payroll.services.hr_workflow import submit_hr_request
        from approvals.services import cancel_approval
        from approvals.models import ApprovalRequest
        from django.contrib.contenttypes.models import ContentType
        self._validate_employee(serializer)
        source = serializer.instance
        if source.status != "PENDING":
            raise APIValidationError({"detail":"Only pending requests may be revised."})
        pending = ApprovalRequest.objects.filter(content_type=ContentType.objects.get_for_model(source), object_id=source.pk, status="PENDING").first()
        try:
            if pending:
                cancel_approval(approval=pending, actor=self.request.user, reason="Request revised")
            maker = getattr(source, "requested_by", None) or getattr(source, self.hr_employee_field).user
            if maker is None or maker.pk != self.request.user.pk:
                raise PermissionDenied("Only the original requester may revise the approval request.")
            source = serializer.save()
            submit_hr_request(source, self.request.user)
        except ValidationError as exc:
            raise APIValidationError({"detail":exc.messages}) from exc
