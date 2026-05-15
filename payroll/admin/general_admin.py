from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

try:
    from import_export import resources
    from import_export.admin import ImportExportModelAdmin
except ImportError:  # pragma: no cover - optional admin dependency
    class _FallbackModelResource:
        class Meta:
            abstract = True

    class _FallbackResources:
        ModelResource = _FallbackModelResource

    resources = _FallbackResources()
    ImportExportModelAdmin = admin.ModelAdmin
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
    PayslipEmailJob,
    LeaveAllowanceEmailJob,
    Appraisal,
    Metric,
    Review,
    Rating,
    AppraisalAssignment,
    CompanyPayrollSetting,
    CompanyHealthInsuranceTier,
    Position,
    Skill,
    EmployeeSkill,
    AttendanceRecord,
    EmployeeDocument,
    AssetCategory,
    EmployeeAsset,
    WorkflowTemplate,
    WorkflowExecution,
    Goal,
    OneOnOne,
    SurveyTemplate,
    SurveyQuestion,
    SurveyResponse,
    LearningCourse,
    CourseEnrollment,
    BenefitPlan,
    BenefitEnrollment,
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


class PayslipEmailJobResource(resources.ModelResource):
    class Meta:
        model = PayslipEmailJob


class LeaveAllowanceEmailJobResource(resources.ModelResource):
    class Meta:
        model = LeaveAllowanceEmailJob


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


class PositionResource(resources.ModelResource):
    class Meta:
        model = Position


class SkillResource(resources.ModelResource):
    class Meta:
        model = Skill


class AttendanceRecordResource(resources.ModelResource):
    class Meta:
        model = AttendanceRecord


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


@admin.register(PayslipEmailJob)
class PayslipEmailJobAdmin(ImportExportModelAdmin):
    resource_class = PayslipEmailJobResource
    list_display = (
        "id",
        "payroll_run",
        "status",
        "sent_count",
        "skipped_count",
        "queued_at",
        "started_at",
        "completed_at",
        "celery_task_id",
        "resend_link",
    )
    list_filter = ("status", "queued_at", "completed_at", "payroll_run__company")
    search_fields = (
        "payroll_run__name",
        "payroll_run__company__name",
        "celery_task_id",
        "error_message",
    )
    readonly_fields = (
        "payroll_run",
        "status",
        "celery_task_id",
        "sent_count",
        "skipped_count",
        "skipped_details",
        "error_message",
        "queued_at",
        "started_at",
        "completed_at",
        "updated_at",
        "resend_link",
    )
    date_hierarchy = "queued_at"
    actions = ("resend_selected_jobs",)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/resend/",
                self.admin_site.admin_view(self.resend_job_view),
                name="payroll_payslipemailjob_resend",
            ),
        ]
        return custom_urls + urls

    def resend_link(self, obj):
        url = reverse("admin:payroll_payslipemailjob_resend", args=[obj.pk])
        return format_html('<a class="button" href="{}">Resend</a>', url)

    resend_link.short_description = "Resend"

    @admin.action(description="Resend selected payslip email jobs")
    def resend_selected_jobs(self, request, queryset):
        queued = 0
        for job in queryset.select_related("payroll_run"):
            job.enqueue()
            queued += 1
        self.message_user(request, f"Queued {queued} payslip email job(s) for resend.")

    def resend_job_view(self, request, object_id):
        job = get_object_or_404(PayslipEmailJob, pk=object_id)
        if not self.has_change_permission(request, job):
            raise PermissionDenied

        job.enqueue()
        self.message_user(request, f"Queued payslip email job #{job.pk} for resend.")
        return redirect(
            request.META.get(
                "HTTP_REFERER",
                reverse("admin:payroll_payslipemailjob_change", args=[job.pk]),
            )
        )


@admin.register(LeaveAllowanceEmailJob)
class LeaveAllowanceEmailJobAdmin(ImportExportModelAdmin):
    resource_class = LeaveAllowanceEmailJobResource
    list_display = (
        "id",
        "leave_request",
        "employee_name",
        "amount",
        "status",
        "queued_at",
        "started_at",
        "completed_at",
        "celery_task_id",
        "resend_link",
    )
    list_filter = (
        "status",
        "queued_at",
        "completed_at",
        "leave_request__employee__company",
    )
    search_fields = (
        "leave_request__employee__first_name",
        "leave_request__employee__last_name",
        "leave_request__employee__emp_id",
        "celery_task_id",
        "error_message",
    )
    readonly_fields = (
        "leave_request",
        "allowance",
        "amount",
        "status",
        "celery_task_id",
        "error_message",
        "queued_at",
        "started_at",
        "completed_at",
        "updated_at",
        "resend_link",
    )
    date_hierarchy = "queued_at"
    actions = ("resend_selected_jobs",)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/resend/",
                self.admin_site.admin_view(self.resend_job_view),
                name="payroll_leaveallowanceemailjob_resend",
            ),
        ]
        return custom_urls + urls

    def employee_name(self, obj):
        employee = obj.leave_request.employee
        return f"{employee.first_name or ''} {employee.last_name or ''}".strip()

    employee_name.short_description = "Employee"

    def resend_link(self, obj):
        url = reverse("admin:payroll_leaveallowanceemailjob_resend", args=[obj.pk])
        return format_html('<a class="button" href="{}">Resend</a>', url)

    resend_link.short_description = "Resend"

    @admin.action(description="Resend selected leave allowance slips")
    def resend_selected_jobs(self, request, queryset):
        queued = 0
        for job in queryset.select_related("leave_request", "allowance"):
            job.enqueue()
            queued += 1
        self.message_user(request, f"Queued {queued} leave allowance slip job(s).")

    def resend_job_view(self, request, object_id):
        job = get_object_or_404(LeaveAllowanceEmailJob, pk=object_id)
        if not self.has_change_permission(request, job):
            raise PermissionDenied

        job.enqueue()
        self.message_user(request, f"Queued leave allowance slip job #{job.pk}.")
        return redirect(
            request.META.get(
                "HTTP_REFERER",
                reverse("admin:payroll_leaveallowanceemailjob_change", args=[job.pk]),
            )
        )


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


@admin.register(Position)
class PositionAdmin(ImportExportModelAdmin):
    resource_class = PositionResource
    list_display = ("title", "company", "department", "employment_type", "status")
    list_filter = ("company", "employment_type", "status")
    search_fields = ("title", "code")


@admin.register(Skill)
class SkillAdmin(ImportExportModelAdmin):
    resource_class = SkillResource
    list_display = ("name", "company", "category")
    list_filter = ("company", "category")
    search_fields = ("name", "category")


@admin.register(EmployeeSkill)
class EmployeeSkillAdmin(admin.ModelAdmin):
    list_display = ("employee", "skill", "proficiency", "is_primary")
    list_filter = ("company", "proficiency", "is_primary")
    search_fields = ("employee__first_name", "employee__last_name", "skill__name")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(ImportExportModelAdmin):
    resource_class = AttendanceRecordResource
    list_display = ("employee", "work_date", "status", "hours_worked")
    list_filter = ("company", "status", "work_date")
    search_fields = ("employee__first_name", "employee__last_name")


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "employee", "document_type", "acknowledgement_required", "is_acknowledged")
    list_filter = ("company", "document_type", "acknowledgement_required", "is_acknowledged")
    search_fields = ("title", "employee__first_name", "employee__last_name")


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "company")
    search_fields = ("name",)


@admin.register(EmployeeAsset)
class EmployeeAssetAdmin(admin.ModelAdmin):
    list_display = ("asset_tag", "name", "employee", "category", "status")
    list_filter = ("company", "status", "category")
    search_fields = ("asset_tag", "name", "employee__first_name", "employee__last_name")


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "workflow_type", "trigger_event", "is_active")
    list_filter = ("company", "workflow_type", "is_active")
    search_fields = ("name", "trigger_event")


@admin.register(WorkflowExecution)
class WorkflowExecutionAdmin(admin.ModelAdmin):
    list_display = ("template", "employee", "status", "started_at", "completed_at")
    list_filter = ("company", "status", "started_at")
    search_fields = ("template__name", "employee__first_name", "employee__last_name")


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("title", "employee", "status", "cycle", "progress_percent")
    list_filter = ("company", "status", "cycle")
    search_fields = ("title", "employee__first_name", "employee__last_name")


@admin.register(OneOnOne)
class OneOnOneAdmin(admin.ModelAdmin):
    list_display = ("employee", "manager", "scheduled_for", "status")
    list_filter = ("company", "status", "scheduled_for")
    search_fields = ("employee__first_name", "employee__last_name", "manager__first_name", "manager__last_name")


class SurveyQuestionInline(admin.TabularInline):
    model = SurveyQuestion
    extra = 1


@admin.register(SurveyTemplate)
class SurveyTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "survey_type", "is_anonymous", "is_active")
    list_filter = ("company", "survey_type", "is_anonymous", "is_active")
    search_fields = ("name",)
    inlines = [SurveyQuestionInline]


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ("survey", "question", "employee", "submitted_at")
    list_filter = ("company", "survey", "submitted_at")
    search_fields = ("survey__name", "employee__first_name", "employee__last_name")


@admin.register(LearningCourse)
class LearningCourseAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "course_type", "delivery_mode", "is_mandatory")
    list_filter = ("company", "course_type", "delivery_mode", "is_mandatory")
    search_fields = ("title",)


@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("course", "employee", "status", "due_date", "completed_at")
    list_filter = ("company", "status", "due_date")
    search_fields = ("course__title", "employee__first_name", "employee__last_name")


@admin.register(BenefitPlan)
class BenefitPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "plan_type", "is_active")
    list_filter = ("company", "plan_type", "is_active")
    search_fields = ("name",)


@admin.register(BenefitEnrollment)
class BenefitEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("plan", "employee", "status", "effective_date", "end_date")
    list_filter = ("company", "status", "effective_date")
    search_fields = ("plan__name", "employee__first_name", "employee__last_name")
