from rest_framework import serializers

from payroll.models import EmployeeProfile, PayT, Payday, Payroll, PayVar, Allowance


class EmployeeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeProfile
        fields= '__all__'

class EmployeeViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeProfile
        fields = ['id', 'emp_id','first_name', 'last_name', 'email', 'created', 'date_of_birth','date_of_employment','gender',]

class CreatePayrollSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payroll
        fields = ['basic_salary',]

class ViewPayrollSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payroll
        fields = "__all__"

class PayDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Payday
        fields = "__all__"