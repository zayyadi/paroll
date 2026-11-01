from django.contrib import admin

from projects.models import Project, ProjectCostAllocation, Task, TimeEntry


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ("title", "status", "assignee", "estimate_hours", "due_date")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company", "status", "manager", "budget")
    list_filter = ("status", "company")
    search_fields = ("code", "name", "client")
    inlines = [TaskInline]


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("timesheet", "project", "task", "hours")
    list_filter = ("project",)


@admin.register(ProjectCostAllocation)
class ProjectCostAllocationAdmin(admin.ModelAdmin):
    list_display = ("payroll_run", "project", "employee", "hours", "amount")
    list_filter = ("project", "payroll_run")

    def has_add_permission(self, request):
        return False  # built by projects.services.allocate_run_costs
