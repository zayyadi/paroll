from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from accounting.models import (
    Account,
    AccountingPeriod,
    FiscalYear,
    Journal,
    JournalEntry,
)
from company.models import CompanyMembership
from company.utils import get_user_company
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
from standup.models import (
    StandupAnswer,
    StandupCheckin,
    StandupFollow,
    StandupQuestion,
    StandupTeam,
    StandupTeamMember,
)


User = get_user_model()


class UserLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_active"]
        read_only_fields = fields


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "password", "first_name", "last_name"]

    def create(self, validated_data):
        request = self.context.get("request")
        company = get_user_company(request.user if request else None)
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            company=company,
            active_company=company,
        )


class CompanyMembershipSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = CompanyMembership
        fields = [
            "id",
            "company",
            "company_name",
            "role",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "company_name", "created_at"]


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "company", "name", "description"]
        read_only_fields = ["id", "company"]


class EmployeeProfileSerializer(serializers.ModelSerializer):
    user = UserLiteSerializer(read_only=True)
    user_payload = UserCreateSerializer(write_only=True, required=False)
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = EmployeeProfile
        fields = [
            "id",
            "company",
            "emp_id",
            "slug",
            "user",
            "user_payload",
            "first_name",
            "last_name",
            "email",
            "department",
            "department_name",
            "job_title",
            "contract_type",
            "date_of_birth",
            "date_of_employment",
            "phone",
            "address",
            "gender",
            "status",
            "created",
        ]
        read_only_fields = ["id", "company", "emp_id", "slug", "email", "created"]

    def validate_department(self, value):
        request = self.context.get("request")
        company = get_user_company(request.user if request else None)
        if value and company and value.company_id != company.id:
            raise serializers.ValidationError("Department must belong to your company.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        company = get_user_company(request.user if request else None)
        user_payload = validated_data.pop("user_payload", None)

        if user_payload:
            user = UserCreateSerializer(
                data=user_payload,
                context=self.context,
            )
            user.is_valid(raise_exception=True)
            created_user = user.save()
            employee = created_user.employee_user
            for key, value in validated_data.items():
                setattr(employee, key, value)
            if company:
                employee.company = company
            employee.save()
            return employee

        validated_data["company"] = company
        return super().create(validated_data)


class PayrollSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payroll
        fields = [
            "id",
            "company",
            "basic_salary",
            "basic",
            "housing",
            "transport",
            "pension_employee",
            "pension_employer",
            "pension",
            "gross_income",
            "taxable_income",
            "payee",
            "nsitf",
            "status",
            "timestamp",
            "updated",
        ]
        read_only_fields = [
            "id",
            "company",
            "basic",
            "housing",
            "transport",
            "pension_employee",
            "pension_employer",
            "pension",
            "gross_income",
            "taxable_income",
            "payee",
            "nsitf",
            "timestamp",
            "updated",
        ]


class PayrollEntrySerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="pays.__str__", read_only=True)

    class Meta:
        model = PayrollEntry
        fields = [
            "id",
            "company",
            "pays",
            "employee_name",
            "status",
            "netpay",
        ]
        read_only_fields = ["id", "company", "netpay", "employee_name"]

    def validate_pays(self, value):
        request = self.context.get("request")
        company = get_user_company(request.user if request else None)
        if company and value.company_id != company.id:
            raise serializers.ValidationError("Employee must belong to your company.")
        return value


class PayrollRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRun
        fields = [
            "id",
            "company",
            "name",
            "slug",
            "paydays",
            "is_active",
            "closed",
        ]
        read_only_fields = ["id", "company", "slug"]


class PayrollRunEntrySerializer(serializers.ModelSerializer):
    payroll_run_slug = serializers.CharField(source="payroll_run.slug", read_only=True)

    class Meta:
        model = PayrollRunEntry
        fields = ["id", "payroll_run", "payroll_run_slug", "payroll_entry"]
        read_only_fields = ["id", "payroll_run_slug"]

    def validate(self, attrs):
        request = self.context.get("request")
        company = get_user_company(request.user if request else None)
        payroll_entry = attrs.get("payroll_entry")
        payroll_run = attrs.get("payroll_run")
        if company and payroll_entry and payroll_entry.company_id != company.id:
            raise serializers.ValidationError(
                {"payroll_entry": "Payroll entry must belong to your company."}
            )
        if company and payroll_run and payroll_run.company_id != company.id:
            raise serializers.ValidationError(
                {"payroll_run": "Payroll run must belong to your company."}
            )
        return attrs


class LeavePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeavePolicy
        fields = ["id", "company", "leave_type", "max_days"]
        read_only_fields = ["id", "company"]


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.__str__", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "employee",
            "employee_name",
            "leave_type",
            "start_date",
            "end_date",
            "is_half_day",
            "reason",
            "status",
            "approved_by",
            "hr_override",
            "override_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "employee_name",
            "approved_by",
            "status",
            "created_at",
            "updated_at",
        ]

    def validate_employee(self, value):
        request = self.context.get("request")
        company = get_user_company(request.user if request else None)
        if company and value.company_id != company.id:
            raise serializers.ValidationError("Employee must belong to your company.")
        return value


class IOUSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee_id.__str__", read_only=True)
    total_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = IOU
        fields = [
            "id",
            "employee_id",
            "employee_name",
            "amount",
            "tenor",
            "reason",
            "interest_rate",
            "payment_method",
            "status",
            "created_at",
            "approved_at",
            "due_date",
            "total_amount",
        ]
        read_only_fields = [
            "id",
            "employee_name",
            "status",
            "created_at",
            "approved_at",
            "total_amount",
        ]

    def validate_employee_id(self, value):
        request = self.context.get("request")
        company = get_user_company(request.user if request else None)
        if company and value.company_id != company.id:
            raise serializers.ValidationError("Employee must belong to your company.")
        return value


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = Account
        fields = [
            "id",
            "name",
            "account_number",
            "type",
            "description",
            "created_at",
            "updated_at",
            "balance",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "balance"]


class FiscalYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalYear
        fields = [
            "id",
            "year",
            "name",
            "start_date",
            "end_date",
            "is_active",
            "is_closed",
            "closed_at",
            "closed_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "closed_at", "closed_by", "created_at", "updated_at"]


class AccountingPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountingPeriod
        fields = [
            "id",
            "fiscal_year",
            "period_number",
            "name",
            "start_date",
            "end_date",
            "is_active",
            "is_closed",
            "closed_at",
            "closed_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "closed_at", "closed_by", "created_at", "updated_at"]


class JournalEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "journal",
            "account",
            "entry_type",
            "amount",
            "memo",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class JournalSerializer(serializers.ModelSerializer):
    entries = JournalEntrySerializer(many=True, read_only=True)

    class Meta:
        model = Journal
        fields = [
            "id",
            "transaction_number",
            "description",
            "date",
            "period",
            "status",
            "created_by",
            "approved_by",
            "approved_at",
            "posted_by",
            "posted_at",
            "reversed_journal",
            "reversal_reason",
            "content_type",
            "object_id",
            "created_at",
            "updated_at",
            "entries",
        ]
        read_only_fields = [
            "id",
            "transaction_number",
            "created_by",
            "approved_by",
            "approved_at",
            "posted_by",
            "posted_at",
            "created_at",
            "updated_at",
            "entries",
        ]


class StandupTeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = StandupTeam
        fields = [
            "id",
            "company",
            "name",
            "slug",
            "description",
            "cadence",
            "timezone_name",
            "reminder_time",
            "deadline_time",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "company", "created_at", "updated_at"]


class StandupTeamMemberSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.__str__", read_only=True)

    class Meta:
        model = StandupTeamMember
        fields = [
            "id",
            "team",
            "employee",
            "employee_name",
            "role",
            "is_active",
            "joined_at",
        ]
        read_only_fields = ["id", "employee_name", "joined_at"]

    def validate(self, attrs):
        team = attrs.get("team")
        employee = attrs.get("employee")
        if team and employee and team.company_id != employee.company_id:
            raise serializers.ValidationError("Team and employee must belong to the same company.")
        return attrs


class StandupQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StandupQuestion
        fields = [
            "id",
            "team",
            "prompt",
            "help_text",
            "answer_type",
            "order",
            "is_required",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class StandupAnswerSerializer(serializers.ModelSerializer):
    question_prompt = serializers.CharField(source="question.prompt", read_only=True)

    class Meta:
        model = StandupAnswer
        fields = [
            "id",
            "question",
            "question_prompt",
            "body",
            "is_blocker",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "question_prompt", "created_at", "updated_at"]


class StandupCheckinSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source="member.__str__", read_only=True)
    answers = StandupAnswerSerializer(many=True, read_only=True)

    class Meta:
        model = StandupCheckin
        fields = [
            "id",
            "company",
            "team",
            "member",
            "member_name",
            "work_date",
            "status",
            "submitted_at",
            "blocker_count",
            "created_at",
            "updated_at",
            "answers",
        ]
        read_only_fields = [
            "id",
            "company",
            "member",
            "member_name",
            "status",
            "submitted_at",
            "blocker_count",
            "created_at",
            "updated_at",
            "answers",
        ]

    def validate_team(self, value):
        request = self.context.get("request")
        company = get_user_company(request.user if request else None)
        if company and value.company_id != company.id:
            raise serializers.ValidationError("Team must belong to your company.")
        return value


class StandupFollowSerializer(serializers.ModelSerializer):
    follower_email = serializers.CharField(source="follower.email", read_only=True)

    class Meta:
        model = StandupFollow
        fields = ["id", "team", "follower", "follower_email", "created_at"]
        read_only_fields = ["id", "follower", "follower_email", "created_at"]
