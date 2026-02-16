from django.contrib import admin
from company.models import Company, CompanyMembership


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "is_default", "created_at")
    list_filter = ("role", "is_default", "company")
    search_fields = ("user__email", "company__name")
