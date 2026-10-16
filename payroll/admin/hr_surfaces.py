"""Tenant-scoped admin catalogue editing and workflow inspection."""
from django.contrib import admin
from django.core.exceptions import ValidationError
from payroll import models
from payroll.services.hr_surfaces import active_company


class CompanyAdmin(admin.ModelAdmin):
    company_path = "company"
    exclude = ("company",)

    def _allowed(self, request, action):
        from approvals.permissions import has_company_permission
        return has_company_permission(request.user, active_company(request.user),
                                      f"payroll.{action}_{self.model._meta.model_name}")

    def has_view_permission(self, request, obj=None):
        return self._allowed(request, "view")

    def has_add_permission(self, request):
        return self._allowed(request, "add")

    def has_change_permission(self, request, obj=None):
        return self._allowed(request, "change")

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).filter(**{self.company_path: active_company(request.user)})

    def get_form(self, request, obj=None, **kwargs):
        base_form = super().get_form(request, obj, **kwargs)
        company = active_company(request.user)

        class CompanyForm(base_form):
            def _post_clean(self):
                self.instance.company = company
                super()._post_clean()
                if not self.errors:
                    try:
                        # Company is excluded from editable fields, but must
                        # participate in composite uniqueness validation.
                        self.instance.full_clean()
                    except ValidationError as exc:
                        self._update_errors(exc)

        return CompanyForm

    def save_model(self, request, obj, form, change):
        company = active_company(request.user)
        obj.company = company
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(models.LeaveType)
class LeaveTypeAdmin(CompanyAdmin):
    list_display = ("code", "name", "default_days", "is_paid", "is_active")
    list_filter = ("is_active", "is_paid")
    search_fields = ("code", "name")

    def get_readonly_fields(self, request, obj=None):
        return ("code",) if obj else ()


@admin.register(models.SalaryBand)
class SalaryBandAdmin(CompanyAdmin):
    list_display = ("position_title", "min_salary", "mid_salary", "max_salary", "currency", "is_active")
    search_fields = ("position_title",)


class WorkflowReadAdmin(CompanyAdmin):
    actions = None
    exclude = ()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields)


@admin.register(models.Timesheet)
class TimesheetAdmin(WorkflowReadAdmin):
    list_display = ("employee", "week_start", "total_hours", "status")
    list_filter = ("status",)


@admin.register(models.ExitSettlement)
class ExitSettlementAdmin(WorkflowReadAdmin):
    list_display = ("employee", "last_working_day", "status")


@admin.register(models.LeaveLedgerEntry)
class LeaveLedgerEntryAdmin(WorkflowReadAdmin):
    company_path = "employee__company"
    list_display = ("employee", "leave_type", "event_type", "days", "year")


@admin.register(models.RetroPayDelta)
class RetroPayDeltaAdmin(WorkflowReadAdmin):
    company_path = "employee__company"
    list_display = ("employee", "effective_date", "total_delta", "status")


@admin.register(models.CompReview)
class CompReviewAdmin(WorkflowReadAdmin):
    company_path = "cycle__company"
    list_display = ("employee", "cycle", "proposed_basic", "status")
