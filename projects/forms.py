from django import forms

from projects.models import Project, Task


class _CompanyEmployeeMixin:
    """Limit employee choices to the active company."""

    employee_fields: tuple = ()

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        from payroll.models import EmployeeProfile

        employees = EmployeeProfile.objects.filter(company=company).order_by(
            "first_name", "last_name"
        )
        for name in self.employee_fields:
            self.fields[name].queryset = employees
            self.fields[name].required = False


class ProjectForm(_CompanyEmployeeMixin, forms.ModelForm):
    employee_fields = ("manager",)

    class Meta:
        model = Project
        fields = [
            "code",
            "name",
            "client",
            "status",
            "manager",
            "start_date",
            "end_date",
            "budget",
            "description",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class TaskForm(_CompanyEmployeeMixin, forms.ModelForm):
    employee_fields = ("assignee",)

    class Meta:
        model = Task
        fields = ["title", "status", "assignee", "estimate_hours", "due_date", "description"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }


class TimeEntryForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.none())
    task = forms.ModelChoiceField(queryset=Task.objects.none(), required=False)
    hours = forms.DecimalField(max_digits=5, decimal_places=2, min_value=0.25)
    note = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        projects = Project.objects.filter(company=company, status__in=Project.OPEN_STATUSES)
        self.fields["project"].queryset = projects
        self.fields["task"].queryset = Task.objects.filter(project__in=projects).exclude(
            status=Task.Status.DONE
        ).select_related("project")
        self.fields["task"].label_from_instance = lambda task: f"{task.project.code}: {task.title}"


class TaskStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Task.Status.choices)
