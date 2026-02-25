from django.shortcuts import get_object_or_404, render

from api.serializers import (
    CreatePayrollSerializer,
    EmployeeCreateSerializer,
    EmployeeViewSerializer,
    PayrollRunEntrySerializer,
    ViewPayrollSerializer,
)

from rest_framework import generics, views, status, viewsets
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import (
    IsAuthenticated,
    DjangoModelPermissions,
)  # Changed IsAdminUser to DjangoModelPermissions

from payroll import models
from company.utils import get_user_company
from company.tenancy import scoped_queryset


class CreateEmployeeView(generics.CreateAPIView):
    queryset = (
        models.EmployeeProfile.objects.all()
    )  # Used by DjangoModelPermissions to infer model
    serializer_class = EmployeeCreateSerializer
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [DjangoModelPermissions]  # Changed from IsAdminUser

    def perform_create(self, serializer):
        employee = serializer.save()
        company = get_user_company(self.request.user)
        if company:
            employee.company = company
            employee.save(update_fields=["company"])


class ListAllEmployee(views.APIView):
    queryset = models.EmployeeProfile.objects.none()  # Added for DjangoModelPermissions
    permission_classes = [DjangoModelPermissions]  # Changed from IsAdminUser

    def get(self, request):
        queryset = scoped_queryset(models.EmployeeProfile.objects, request.user)
        serializer = EmployeeViewSerializer(queryset, many=True)
        return Response(serializer.data)


class ListEmployee(views.APIView):
    permission_classes = [IsAuthenticated]  # Remains IsAuthenticated

    def get(self, request):
        user_id = self.request.user.id
        employee_profile = get_object_or_404(
            scoped_queryset(models.EmployeeProfile.objects, request.user),
            user_id=user_id,
        )
        serializer = EmployeeViewSerializer(employee_profile)
        return Response(serializer.data)


class CreatePayrollView(generics.CreateAPIView):
    queryset = models.Payroll.objects.all()  # Used by DjangoModelPermissions
    serializer_class = CreatePayrollSerializer
    permission_classes = [DjangoModelPermissions]  # Changed from IsAdminUser

    def perform_create(self, serializer):
        serializer.save(company=get_user_company(self.request.user))


class ListPayrollView(generics.ListAPIView):
    queryset = models.Payroll.objects.all()  # Used by DjangoModelPermissions
    serializer_class = ViewPayrollSerializer
    permission_classes = [DjangoModelPermissions]  # Changed from IsAdminUser

    def get_queryset(self):
        return scoped_queryset(models.Payroll.objects, self.request.user)


class PayrollRunEntryView(viewsets.ViewSet):
    queryset = models.PayrollRunEntry.objects.none()  # Added for DjangoModelPermissions
    permission_classes = [DjangoModelPermissions]  # Changed from IsAdminUser

    def list(self, request):
        pay = scoped_queryset(
            models.PayrollRunEntry.objects,
            request.user,
            company_field="payroll_entry__company",
        )
        serializer = PayrollRunEntrySerializer(pay, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        # For retrieve, DjangoModelPermissions will check 'view_payday' perm on the specific object if object perms are setup
        # or just model-level if not. The queryset here is for the ViewSet's general model.
        # The actual object fetching for retrieve is usually handled by get_object() or manually.
        # The current manual filtering is kept:
        queryset_data = scoped_queryset(
            models.PayrollRunEntry.objects.filter(
                payroll_run=pk,
            ),
            request.user,
            company_field="payroll_entry__company",
        )
        serializer = PayrollRunEntrySerializer(
            queryset_data, many=True
        )  # many=True seems odd for a retrieve on pk. Usually one object.
        # If payroll_run can map to multiple PayrollRunEntry entries, then it's a list.
        return Response(serializer.data, status=status.HTTP_200_OK)
