from django.contrib.auth.hashers import make_password

# from django.contrib.auth.models import User # Replaced with CustomUser
from users.models import CustomUser

from rest_framework import serializers
from company.utils import get_user_company

from payroll.models import EmployeeProfile, PayrollRun, PayrollRunEntry, Payroll, PayrollEntry, Allowance


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    def create(self, validated_data):
        request = self.context.get("request")
        company = get_user_company(getattr(request, "user", None))
        user = CustomUser.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            company=company,
            active_company=company,
        )
        return user

    class Meta:  # Corrected typo
        model = CustomUser
        fields = ["email", "password", "first_name", "last_name"]


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


class PayrollRunEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRunEntry
        depth = 2
        fields = [
            "payroll_run",
            "payroll_entry",
        ]
