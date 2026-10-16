"""API consumers for HR datasets, catalogues and approval workflows."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from payroll import models
from payroll.services.hr_surfaces import active_company, require_permission, timesheets_for, save_timesheet, RESOURCES


class PeopleAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from integrations.people_analytics import dataset_as_json
        from payroll.forms.hr_surfaces import DatasetQueryForm
        company = active_company(request.user)
        require_permission(request.user, company, "payroll.view_employeeprofile")
        require_permission(request.user, company, "payroll.view_payrollentry")
        form = DatasetQueryForm(request.query_params)
        if not form.is_valid():
            raise ValidationError(form.errors)
        return Response(dataset_as_json(company, **form.cleaned_data))


class TimesheetSerializer(serializers.ModelSerializer):
    is_payable = serializers.BooleanField(read_only=True)

    class Meta:
        model = models.Timesheet
        fields = ["id", "employee", "week_start", "total_hours", "notes", "status",
                  "submitted_at", "approved_at", "approval_request", "is_payable"]
        read_only_fields = ["employee", "status", "submitted_at", "approved_at", "approval_request"]


class TimesheetViewSet(viewsets.GenericViewSet):
    serializer_class = TimesheetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return timesheets_for(self.request.user)

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sheet = save_timesheet(actor=request.user, **serializer.validated_data)
        except models.EmployeeProfile.DoesNotExist:
            raise ValidationError("Your account needs an employee profile.")
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(self.get_serializer(sheet).data, status=201)

    def partial_update(self, request, pk=None):
        sheet = self.get_object()
        serializer = self.get_serializer(sheet, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "week_start" in serializer.validated_data and serializer.validated_data["week_start"] != sheet.week_start:
            raise ValidationError("A saved timesheet's week cannot be changed.")
        try:
            sheet = save_timesheet(actor=request.user, pk=sheet.pk,
                                   total_hours=serializer.validated_data.get("total_hours"),
                                   notes=serializer.validated_data.get("notes", sheet.notes))
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(self.get_serializer(sheet).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        from payroll.services.timesheet_service import submit_timesheet
        sheet = self.get_object()
        try:
            submit_timesheet(timesheet=sheet, actor=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        sheet.refresh_from_db()
        return Response(self.get_serializer(sheet).data)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        from payroll.services.timesheet_service import cancel_timesheet
        try:
            sheet = cancel_timesheet(timesheet=self.get_object(), actor=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(self.get_serializer(sheet).data)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        from approvals.services import decide_approval
        sheet = self.get_object()
        if not sheet.approval_request_id:
            raise ValidationError("Submit the timesheet before deciding it.")
        decision = serializers.ChoiceField(choices=["APPROVE", "REJECT"]).run_validation(request.data.get("decision"))
        comment = serializers.CharField(required=False, allow_blank=True).run_validation(request.data.get("comment", ""))
        try:
            decide_approval(approval=sheet.approval_request, actor=request.user, decision=decision, comment=comment)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        sheet.refresh_from_db()
        return Response(self.get_serializer(sheet).data)


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LeaveType
        fields = ["id", "code", "name", "default_days", "is_paid", "allows_half_day", "encashable",
                  "encashment_rate", "carryover_rate", "is_active"]

    def validate(self, attrs):
        from payroll.forms.hr_surfaces import LeaveTypeForm
        company = active_company(self.context["request"].user)
        if self.instance and "code" in attrs and attrs["code"] != self.instance.code:
            raise ValidationError({"code": "The leave type code cannot be changed."})
        source = self.instance or models.LeaveType()
        data = {name: getattr(source, name) for name in self.Meta.fields if name != "id"}
        data.update(attrs)
        # Form validation also checks company/code uniqueness and model bounds.
        form = LeaveTypeForm(data=data, instance=self.instance, company=company)
        if not form.is_valid():
            raise ValidationError(form.errors)
        return {name: value for name, value in form.cleaned_data.items() if name in self.Meta.fields}


class LeaveTypeViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveTypeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        company = active_company(request.user)
        permission = {"create": "add", "update": "change", "partial_update": "change"}.get(self.action, "view")
        require_permission(request.user, company, f"payroll.{permission}_leavetype")

    def get_queryset(self):
        from payroll.services.leave_type_service import ensure_default_leave_types
        company = active_company(self.request.user)
        permission = {"create": "add", "update": "change", "partial_update": "change"}.get(self.action, "view")
        require_permission(self.request.user, company, f"payroll.{permission}_leavetype")
        ensure_default_leave_types(company)
        return models.LeaveType.objects.filter(company=company)

    def perform_create(self, serializer):
        company = active_company(self.request.user)
        require_permission(self.request.user, company, "payroll.add_leavetype")
        serializer.save(company=company)


class LeaveBalancesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from payroll.services.leave_type_service import leave_balance_cards
        company = active_company(request.user)
        employee = get_object_or_404(models.EmployeeProfile, user=request.user, company=company)
        year = serializers.IntegerField(min_value=1900, max_value=9999).run_validation(request.query_params.get("year", timezone.localdate().year))
        return Response(leave_balance_cards(employee, year))


class StrictReadPermission:
    def check_permissions(self, request):
        super().check_permissions(request)
        company = active_company(request.user)
        require_permission(request.user, company, f"payroll.view_{self.queryset.model._meta.model_name}")


def record_viewset(model, scope):
    class RecordSerializer(serializers.ModelSerializer):
        class Meta:
            fields = "__all__"
        Meta.model = model

    RecordSerializer.__name__ = model.__name__ + "RecordSerializer"

    class RecordViewSet(StrictReadPermission, viewsets.ReadOnlyModelViewSet):
        permission_classes = [IsAuthenticated]
        queryset = model.objects.none()
        serializer_class = RecordSerializer

        def get_queryset(self):
            return model.objects.filter(**{scope: active_company(self.request.user)}).order_by("-pk")

    return RecordViewSet

RECORD_VIEWSETS = {name: record_viewset(model, scope) for name, (model, scope) in RESOURCES.items()}
