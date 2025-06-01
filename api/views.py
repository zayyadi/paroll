from django.shortcuts import get_object_or_404, render

from api.serializers import (
    CreatePayrollSerializer,
    EmployeeCreateSerializer,
    EmployeeViewSerializer,
    PayDaySerializer,
    ViewPayrollSerializer,
)

from rest_framework import generics, views, status, viewsets
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from payroll import models


class CreateEmployeeView(generics.CreateAPIView):
    queryset = models.EmployeeProfile.objects.all()
    serializer_class = EmployeeCreateSerializer
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAdminUser]


class ListAllEmployee(views.APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = models.EmployeeProfile.objects.all()
        serializer = EmployeeViewSerializer(queryset, many=True)
        return Response(serializer.data)


class ListEmployee(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = self.request.user.id # Renamed 'user' to 'user_id' for clarity
        # Assuming self.request.user.id is the ID of the CustomUser
        employee_profile = get_object_or_404(models.EmployeeProfile, user_id=user_id)
        serializer = EmployeeViewSerializer(employee_profile) # many=False is default and correct for single instance
        return Response(serializer.data)


class CreatePayrollView(generics.CreateAPIView):
    queryset = models.Payroll.objects.all()
    serializer_class = CreatePayrollSerializer
    permission_classes = [IsAdminUser]


class ListPayrollView(generics.ListAPIView):
    queryset = models.Payroll.objects.all()
    serializer_class = ViewPayrollSerializer
    permission_classes = [IsAdminUser]


class PaydayView(viewsets.ViewSet):
    permission_classes = [IsAdminUser]

    def list(self, request):
        pay = models.Payday.objects.all()
        serializer = PayDaySerializer(pay, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        # user = self.request.user.id
        # emp = get_object_or_404(models.EmployeeProfile, user_id=user)

    def retrieve(self, request, pk=None):

        queryset = (
            models.Payday.objects.all().filter(paydays_id=pk)
            # .values_list(
            #     "payroll_id__pays__emp_id",
            #     "payroll_id__pays__first_name",
            #     "payroll_id__pays__last_name",
            #     "payroll_id__pays__bank",
            #     "payroll_id__pays__bank_account_number",
            #     "payroll_id__netpay",
            # )
        )
        serializer = PayDaySerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
