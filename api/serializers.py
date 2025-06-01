from django.contrib.auth.hashers import make_password
# from django.contrib.auth.models import User # Replaced with CustomUser
from users.models import CustomUser

from rest_framework import serializers

from payroll.models import EmployeeProfile, PayT, Payday, Payroll, PayVar, Allowance


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    def create(self, validated_data):
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        return user

    class Meta: # Corrected typo
        model = CustomUser
        fields = [
            "email",
            "password",
            "first_name",
            "last_name"
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
