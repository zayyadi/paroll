from django.shortcuts import get_object_or_404, render

from api.serializers import CreatePayrollSerializer, EmployeeCreateSerializer, EmployeeViewSerializer, PayDaySerializer, ViewPayrollSerializer

from rest_framework import generics

from payroll import models


class CreateEmployeeView(generics.CreateAPIView):
    queryset = models.EmployeeProfile.objects.all()
    serializer_class = EmployeeCreateSerializer


class ListAllEmployee(generics.ListAPIView):
    queryset = models.EmployeeProfile.objects.all()
    serializer_class= EmployeeViewSerializer

class CreatePayrollView(generics.CreateAPIView):
    queryset = models.Payroll.objects.all()
    serializer_class = CreatePayrollSerializer

class ListPayrollView(generics.ListAPIView):
    queryset = models.Payroll.objects.all()
    serializer_class = ViewPayrollSerializer

class PaydayView(generics.ListAPIView):
    serializer_class = PayDaySerializer

    def get_queryset(self):
        user = self.request.user.id
        # emp = get_object_or_404(models.EmployeeProfile, user_id=user)

        return models.Payday.objects.all().filter(payroll_id__pays__id=user)

