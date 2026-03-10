from django.contrib import admin

from marketing.models import LeadInquiry, MarketingEvent


@admin.register(LeadInquiry)
class LeadInquiryAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "work_email",
        "company_name",
        "company_size",
        "status",
        "assignee",
        "created_at",
    )
    search_fields = ("full_name", "work_email", "company_name")
    list_filter = ("company_size", "status", "created_at")
    ordering = ("-created_at",)
    actions = ("mark_as_contacted", "mark_as_qualified", "assign_to_me")

    @admin.action(description="Mark selected leads as contacted")
    def mark_as_contacted(self, request, queryset):
        queryset.update(status=LeadInquiry.STATUS_CONTACTED)

    @admin.action(description="Mark selected leads as qualified")
    def mark_as_qualified(self, request, queryset):
        queryset.update(status=LeadInquiry.STATUS_QUALIFIED)

    @admin.action(description="Assign selected leads to me")
    def assign_to_me(self, request, queryset):
        queryset.update(assignee=request.user)


@admin.register(MarketingEvent)
class MarketingEventAdmin(admin.ModelAdmin):
    list_display = ("event_name", "path", "user", "created_at")
    search_fields = ("event_name", "path")
    list_filter = ("event_name", "created_at")
    ordering = ("-created_at",)
