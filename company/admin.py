from django.contrib import admin
from company.models import Company, CompanyMembership
from payroll.admin import (
    DepartmentInline,
    EmployeeProfileInline,
    PayrollEntryInline,
    PayrollRunInline,
    PayrollStructureInline,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    inlines = (
        DepartmentInline,
        EmployeeProfileInline,
        PayrollStructureInline,
        PayrollRunInline,
        PayrollEntryInline,
    )


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "is_default", "created_at")
    list_filter = ("role", "is_default", "company")
    search_fields = ("user__email", "company__name")
