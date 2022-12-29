from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User

from rest_framework import serializers

from payroll.models import EmployeeProfile, PayT, Payday, Payroll, PayVar, Allowance


class UserSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        validated_data["password"] = make_password(validated_data["password"])
        return super(UserSerializer, self).create(validated_data)

    class meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
        ]


class ViewPayrollSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payroll
        fields = "__all__"


class EmployeeCreateSerializer(serializers.ModelSerializer):
    photo = serializers.ImageField(required=False)
    user = UserSerializer()
    employee_pay = ViewPayrollSerializer()

    class Meta:
        model = EmployeeProfile
        fields = "__all__"


class EmployeeViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeProfile
        depth = 2
        fields = [
            "id",
            "emp_id",
            "first_name",
            "last_name",
            "email",
            "photo",
            "created",
            "user",
            "date_of_birth",
            "date_of_employment",
            "gender",
            "employee_pay",
        ]


class CreatePayrollSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payroll
        fields = [
            "basic_salary",
        ]


class PayDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Payday
        depth = 2
        fields = [
            "paydays_id",
            "payroll_id",
        ]
