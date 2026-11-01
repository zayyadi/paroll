"""Projects, tasks, project time and project costing.

Time is booked against projects on the weekly ``payroll.Timesheet``: each
``TimeEntry`` is a slice of a timesheet's hours. Once a payroll run exists,
``ProjectCostAllocation`` spreads each employee's employer cost for the run
across projects in proportion to their approved project hours that month
(``projects.services.allocate_run_costs``). Hours not booked to a project stay
unallocated, as overhead.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    OPEN_STATUSES = (Status.PLANNED, Status.ACTIVE)

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="projects"
    )
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    client = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    manager = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_projects",
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total labour budget in the company currency.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="unique_project_code_per_company"
            )
        ]

    def __str__(self):
        return f"{self.code} · {self.name}"

    @property
    def is_open(self) -> bool:
        """Time can be booked only to planned or active projects."""
        return self.status in self.OPEN_STATUSES

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before the start date."})
        if self.budget is not None and self.budget < 0:
            raise ValidationError({"budget": "Budget cannot be negative."})
        if self.manager_id and self.manager.company_id != self.company_id:
            raise ValidationError({"manager": "The manager must work for this company."})


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    assignee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_tasks",
    )
    estimate_hours = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project", "status", "due_date", "pk"]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.estimate_hours is not None and self.estimate_hours < 0:
            raise ValidationError({"estimate_hours": "Estimate cannot be negative."})
        if self.assignee_id and self.project_id and (
            self.assignee.company_id != self.project.company_id
        ):
            raise ValidationError({"assignee": "The assignee must work for this company."})


class TimeEntry(models.Model):
    """Hours from one weekly timesheet booked to a project (and optionally a task)."""

    timesheet = models.ForeignKey(
        "payroll.Timesheet", on_delete=models.CASCADE, related_name="project_time"
    )
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="time_entries"
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="time_entries",
    )
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timesheet", "project__code", "pk"]
        verbose_name_plural = "time entries"

    def __str__(self):
        return f"{self.hours}h on {self.project.code}"

    def clean(self):
        super().clean()
        if self.hours is not None and self.hours <= 0:
            raise ValidationError({"hours": "Hours must be greater than zero."})
        if self.project_id and self.timesheet_id and (
            self.project.company_id != self.timesheet.company_id
        ):
            raise ValidationError({"project": "Select a project in your company."})
        if self.task_id and self.task.project_id != self.project_id:
            raise ValidationError({"task": "The task must belong to the selected project."})


class ProjectCostAllocation(models.Model):
    """One employee's share of a payroll run's cost booked to one project."""

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="project_cost_allocations"
    )
    payroll_run = models.ForeignKey(
        "payroll.PayrollRun", on_delete=models.CASCADE, related_name="project_costs"
    )
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="cost_allocations"
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.PROTECT,
        related_name="project_cost_allocations",
    )
    hours = models.DecimalField(
        max_digits=7, decimal_places=2, help_text="Approved hours booked to the project."
    )
    employee_hours = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        help_text="All approved timesheet hours for the employee in the period.",
    )
    employee_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Employer cost for the employee in this run (gross, employer levies, allowances).",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["project__code", "employee__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "project", "employee"],
                name="unique_project_cost_per_run_employee",
            )
        ]

    def __str__(self):
        return f"{self.project.code} · {self.employee} · {self.amount}"
