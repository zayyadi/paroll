from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.contrib.auth.models import Group, Permission

# Register your models here.
from payroll.models import (
    Department,
    EmployeeProfile,
    Allowance,
    LeaveRequest,
    PayVar,
    Payroll,
    PayT,
    Deduction,
    PerformanceReview,
)


class EmployeeProfileResources(resources.ModelResource):
    class Meta:
        model = EmployeeProfile


class PayrollResource(resources.ModelResource):
    class Meta:
        model = Payroll


class VarResource(resources.ModelResource):
    class Meta:
        model = Payroll


class PayResource(resources.ModelResource):
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
    model = PayT.payroll_payday.through
    extra = 4
    raw_id_fields = ("payroll_id",)
    # readonly_fields = ['net_pay']


class PayrollAdmin(admin.ModelAdmin):
    model = PayT
    inlines = (PayrollInline,)
    list_display = ["paydays"]
    # readonly_fields = ['timestamp', 'updated']
    # raw_id_fields = ['payday']


admin.site.unregister(Group)


# Custom Group Admin
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "get_permissions")
    filter_horizontal = ("permissions",)  # Makes it easier to assign permissions

    def get_permissions(self, obj):
        return ", ".join([p.name for p in obj.permissions.all()])

    get_permissions.short_description = "Permissions"


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "start_date", "end_date", "status")


# Register the Group model with the custom admin
admin.site.register(Group, GroupAdmin)


# Optionally, register the Permission model if you want to manage it directly
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("name", "codename", "content_type")
    list_filter = ("content_type",)
    search_fields = ("name", "codename")


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ("employee", "review_date", "rating")


admin.site.register(Permission, PermissionAdmin)


admin.site.register(PayT, PayrollAdmin)
admin.site.register(Department)
admin.site.register(EmployeeProfile, ImportExportModelAdmin)
admin.site.register(Payroll, ImportExportModelAdmin)
admin.site.register(PayVar, ImportExportModelAdmin)
# admin.site.register(PayT, ImportExportModelAdmin)
admin.site.register(Allowance, ImportExportModelAdmin)
admin.site.register(Deduction, ImportExportModelAdmin)
