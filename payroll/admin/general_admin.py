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
    PayrollEntry,
    Payroll,
    PayrollRun,
    Deduction,
    PayrollRunEntry,
    Appraisal,
    Metric,
    Review,
    Rating,
    AppraisalAssignment,
    CompanyPayrollSetting,
    CompanyHealthInsuranceTier,
)


class EmployeeProfileResources(resources.ModelResource):
    class Meta:
        model = EmployeeProfile


# Notification resources removed - now in notification_admin.py


class PayrollResource(resources.ModelResource):
    class Meta:
        model = Payroll


class PayrollRunResource(resources.ModelResource):
    class Meta:
        model = PayrollRun


class PayrollEntryResource(resources.ModelResource):
    class Meta:
        model = PayrollEntry


class IOUResource(resources.ModelResource):
    class Meta:
        model = IOU


class DepartmentResource(resources.ModelResource):
    class Meta:
        model = Department


class LeaveRequestResource(resources.ModelResource):
    class Meta:
        model = LeaveRequest


class PayrollRunEntryResource(resources.ModelResource):
    class Meta:
        model = PayrollRunEntry


class AppraisalResource(resources.ModelResource):
    class Meta:
        model = Appraisal


class MetricResource(resources.ModelResource):
    class Meta:
        model = Metric


class ReviewResource(resources.ModelResource):
    class Meta:
        model = Review


class RatingResource(resources.ModelResource):
    class Meta:
        model = Rating


class AppraisalAssignmentResource(resources.ModelResource):
    class Meta:
        model = AppraisalAssignment


class AllowanceResources(resources.ModelResource):
    class Meta:
        model = Allowance


class DeductionResources(resources.ModelResource):
    class Meta:
        model = Deduction


class PayrollInline(admin.StackedInline):
    model = PayrollRunEntry
    extra = 1
    raw_id_fields = ("payroll_entry",)


class CompanyHealthInsuranceTierInline(admin.TabularInline):
    model = CompanyHealthInsuranceTier
    extra = 1


@admin.register(PayrollRun)
class PayrollRunAdmin(ImportExportModelAdmin):
    resource_class = PayrollRunResource
    inlines = (PayrollInline,)
    list_display = ["name", "company", "paydays", "is_active", "closed"]
    list_filter = ["company", "is_active", "closed", "paydays"]
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
class LeaveRequestAdmin(ImportExportModelAdmin):
    resource_class = LeaveRequestResource
    list_display = ("employee", "leave_type", "start_date", "end_date", "status")
    list_filter = ("leave_type", "status")
    search_fields = ("employee__first_name", "employee__last_name")
    date_hierarchy = "start_date"


admin.site.register(Group, GroupAdmin)


class PermissionAdmin(admin.ModelAdmin):
    list_display = ("name", "codename", "content_type")
    list_filter = ("content_type",)
    search_fields = ("name", "codename")


admin.site.register(Permission, PermissionAdmin)


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(ImportExportModelAdmin):
    resource_class = EmployeeProfileResources
    list_display = (
        "first_name",
        "last_name",
        "company",
        "email",
        "department",
        "company",
        "job_title",
        "date_of_employment",
        "rent_paid",
        "status",  # Use custom method
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
                    "company",
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
                    "status",
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
                    "hmo_provider",
                    "pension_fund_manager",
                    "pension_rsa",
                    "bank",
                    "bank_account_name",
                    "bank_account_number",
                    "rent_paid",
                    # "rent_relief",
                )
            },
        ),
    )
    readonly_fields = ("emp_id",)


@admin.register(Payroll)
class PayrollAdmin(ImportExportModelAdmin):
    resource_class = PayrollResource
    list_display = ("company", "basic_salary", "payee", "timestamp", "updated")
    list_filter = ("company", "timestamp")
    search_fields = ("basic_salary",)
    readonly_fields = ("timestamp", "updated")
    date_hierarchy = "timestamp"


@admin.register(CompanyPayrollSetting)
class CompanyPayrollSettingAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "basic_percentage",
        "housing_percentage",
        "transport_percentage",
        "nhf_percentage",
        "leave_allowance_percentage",
        "pays_thirteenth_month",
        "thirteenth_month_percentage",
        "updated_at",
    )
    search_fields = ("company__name",)
    inlines = (CompanyHealthInsuranceTierInline,)


@admin.register(IOU)
class IOUAdmin(ImportExportModelAdmin):
    resource_class = IOUResource
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
    search_fields = (
        "employee__first_name",
        "employee__last_name",
        "deduction_type",
        "reason",
    )
    date_hierarchy = "created_at"


@admin.register(Department)
class DepartmentAdmin(ImportExportModelAdmin):
    resource_class = DepartmentResource
    list_display = ("name", "company")
    list_filter = ("company",)
    search_fields = ("name",)


@admin.register(PayrollRunEntry)
class PayrollRunEntryAdmin(ImportExportModelAdmin):
    resource_class = PayrollRunEntryResource
    list_display = ("payroll_run", "get_employee_name", "get_netpay")
    list_filter = ("payroll_run", "payroll_entry__pays__department")
    search_fields = (
        "payroll_run__name",
        "payroll_entry__pays__first_name",
        "payroll_entry__pays__last_name",
    )
    readonly_fields = ("get_netpay",)
    date_hierarchy = "payroll_run__paydays"

    def get_employee_name(self, obj):
        return f"{obj.payroll_entry.pays.first_name} {obj.payroll_entry.pays.last_name}"

    get_employee_name.short_description = "Employee"

    def get_netpay(self, obj):
        return obj.payroll_entry.netpay

    get_netpay.short_description = "Net Pay"


@admin.register(PayrollEntry)
class PayrollEntryAdmin(ImportExportModelAdmin):
    resource_class = PayrollEntryResource
    list_display = ("pays", "company", "status", "netpay")
    list_filter = ("company", "status")


class RatingInline(admin.TabularInline):
    model = Rating
    extra = 1


@admin.register(Appraisal)
class AppraisalAdmin(ImportExportModelAdmin):
    resource_class = AppraisalResource
    list_display = ("name", "start_date", "end_date")
    search_fields = ("name",)


@admin.register(Metric)
class MetricAdmin(ImportExportModelAdmin):
    resource_class = MetricResource
    list_display = ("name", "description")
    search_fields = ("name",)


@admin.register(Review)
class ReviewAdmin(ImportExportModelAdmin):
    resource_class = ReviewResource
    list_display = ("appraisal", "employee", "reviewer")
    search_fields = ("appraisal__name", "employee__first_name", "reviewer__first_name")
    inlines = [RatingInline]


@admin.register(Rating)
class RatingAdmin(ImportExportModelAdmin):
    resource_class = RatingResource
    list_display = ("review", "metric", "rating")
    search_fields = ("review__appraisal__name", "metric__name")


@admin.register(AppraisalAssignment)
class AppraisalAssignmentAdmin(ImportExportModelAdmin):
    resource_class = AppraisalAssignmentResource
    list_display = ("appraisal", "appraisee", "appraiser")
    search_fields = (
        "appraisal__name",
        "appraisee__first_name",
        "appraiser__first_name",
    )
