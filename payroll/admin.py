from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.contrib.auth.models import Group, Permission

# Register your models here.
from payroll.models import (
    IOU,
    Department,
    EmployeeProfile,
    Allowance,
    LeaveRequest,
    PayVar,
    Payroll,
    PayT,
    Deduction,
    PerformanceReview,
    Payday,
)


class EmployeeProfileResources(resources.ModelResource):
    class Meta:
        model = EmployeeProfile


class PayrollResource(resources.ModelResource):
    class Meta:
        model = Payroll


class PayTResource(resources.ModelResource):
    class Meta:
        model = PayT


class PayVarResource(resources.ModelResource):
    class Meta:
        model = PayVar


class AllowanceResources(resources.ModelResource):
    class Meta:
        model = Allowance


class DeductionResources(resources.ModelResource):
    class Meta:
        model = Deduction


class PayrollInline(admin.StackedInline):
    model = Payday
    extra = 1
    raw_id_fields = ("payroll_id",)


@admin.register(PayT)
class PayTAdmin(ImportExportModelAdmin):
    resource_class = PayTResource
    inlines = (PayrollInline,)
    list_display = ["name", "paydays", "is_active", "closed"]
    list_filter = ["is_active", "closed", "paydays"]
    search_fields = ["name"]
    date_hierarchy = "paydays"


admin.site.unregister(Group)


class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "get_permissions")
    filter_horizontal = ("permissions",)

    def get_permissions(self, obj):
        return ", ".join([p.name for p in obj.permissions.all()])

    get_permissions.short_description = "Permissions"


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "start_date", "end_date", "status")
    list_filter = ("leave_type", "status")
    search_fields = ("employee__first_name", "employee__last_name")
    date_hierarchy = "start_date"


admin.site.register(Group, GroupAdmin)


class PermissionAdmin(admin.ModelAdmin):
    list_display = ("name", "codename", "content_type")
    list_filter = ("content_type",)
    search_fields = ("name", "codename")


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ("employee", "review_date", "rating")
    list_filter = ("rating", "review_date")
    search_fields = ("employee__first_name", "employee__last_name", "comments")
    date_hierarchy = "review_date"


admin.site.register(Permission, PermissionAdmin)


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(ImportExportModelAdmin):
    resource_class = EmployeeProfileResources
    list_display = (
        "first_name",
        "last_name",
        "email",
        "department",
        "job_title",
        "date_of_employment",
        # "get_is_active",  # Use custom method
    )
    list_filter = (
        "department",
        "job_title",
        "contract_type",
        "gender",
        # Removed "is_active" from list_filter to avoid E116 error
    )
    search_fields = ("first_name", "last_name", "email", "emp_id")
    date_hierarchy = "date_of_employment"
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "user",
                    "emp_id",
                    "first_name",
                    "last_name",
                    "email",
                    "photo",
                )
            },
        ),
        (
            "Personal Information",
            {
                "fields": (
                    "date_of_birth",
                    "gender",
                    "phone",
                    "address",
                    "next_of_kin_name",
                    "next_of_kin_relationship",
                    "next_of_kin_phone",
                )
            },
        ),
        (
            "Employment Details",
            {
                "fields": (
                    "department",
                    "job_title",
                    "contract_type",
                    "date_of_employment",
                    # "is_active",
                )
            },
        ),
        (
            "Financial Information",
            {
                "fields": (
                    "employee_pay",
                    "pension_rsa",
                    "bank",
                    "bank_account_name",
                    "bank_account_number",
                )
            },
        ),
    )
    readonly_fields = ("emp_id",)

    # def get_is_active(self, obj):
    #     return obj.is_active

    # get_is_active.boolean = True
    # get_is_active.short_description = "Active"


@admin.register(Payroll)
class PayrollAdmin(ImportExportModelAdmin):
    resource_class = PayrollResource
    list_display = ("basic_salary", "payee", "timestamp", "updated")
    list_filter = ("timestamp",)
    search_fields = ("basic_salary",)
    readonly_fields = ("timestamp", "updated")
    date_hierarchy = "timestamp"


@admin.register(IOU)
class IOUAdmin(ImportExportModelAdmin):
    list_display = (
        "employee_id",
        "amount",
        "tenor",
        "status",
        "created_at",
        "approved_at",
    )
    list_filter = ("status", "tenor", "created_at", "approved_at")
    search_fields = ("employee_id__first_name", "employee_id__last_name", "reason")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)


@admin.register(Allowance)
class AllowanceAdmin(ImportExportModelAdmin):
    resource_class = AllowanceResources
    list_display = ("employee", "allowance_type", "amount", "created_at")
    list_filter = ("allowance_type", "created_at")
    search_fields = ("employee__first_name", "employee__last_name", "allowance_type")
    date_hierarchy = "created_at"


@admin.register(Deduction)
class DeductionAdmin(ImportExportModelAdmin):
    resource_class = DeductionResources
    list_display = ("employee", "deduction_type", "amount", "reason", "created_at")
    list_filter = ("deduction_type", "created_at")
    search_fields = ("employee__first_name", "employee__last_name", "deduction_type", "reason")
    date_hierarchy = "created_at"


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Payday)
class PaydayAdmin(admin.ModelAdmin):
    list_display = ("paydays_id", "get_employee_name", "get_netpay")
    list_filter = ("paydays_id", "payroll_id__pays__department")
    search_fields = (
        "paydays_id__name",
        "payroll_id__pays__first_name",
        "payroll_id__pays__last_name",
    )
    readonly_fields = ("get_netpay",)
    date_hierarchy = "paydays_id__paydays"

    def get_employee_name(self, obj):
        return f"{obj.payroll_id.pays.first_name} {obj.payroll_id.pays.last_name}"

    get_employee_name.short_description = "Employee"

    def get_netpay(self, obj):
        return obj.payroll_id.netpay

    get_netpay.short_description = "Net Pay"


admin.site.register(PayVar, ImportExportModelAdmin)
