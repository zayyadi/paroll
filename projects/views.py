from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from approvals.permissions import has_company_permission
from payroll.services.hr_surfaces import active_company
from projects import services
from projects.forms import ProjectForm, TaskForm, TaskStatusForm, TimeEntryForm
from projects.models import Project, Task, TimeEntry


def _require(user, company, permission):
    if not has_company_permission(user, company, permission):
        raise PermissionDenied("You do not have permission for this project resource.")


def _can(user, company, permission):
    return has_company_permission(user, company, permission)


def _project(request, pk, permission="projects.view_project"):
    company = active_company(request.user)
    _require(request.user, company, permission)
    return company, get_object_or_404(Project, pk=pk, company=company)


def _code_taken(company, code, exclude_pk=None):
    taken = Project.objects.filter(company=company, code__iexact=code)
    if exclude_pk:
        taken = taken.exclude(pk=exclude_pk)
    return taken.exists()


@login_required
def project_list(request):
    company = active_company(request.user)
    _require(request.user, company, "projects.view_project")
    projects = Project.objects.filter(company=company).select_related("manager")
    status = request.GET.get("status", "")
    if status in Project.Status.values:
        projects = projects.filter(status=status)
    return render(
        request,
        "projects/project_list.html",
        {
            "projects": projects,
            "status": status,
            "statuses": Project.Status.choices,
            "can_add": _can(request.user, company, "projects.add_project"),
            "can_view_costs": _can(request.user, company, "projects.view_projectcostallocation"),
        },
    )


@login_required
def project_form(request, pk=None):
    company = active_company(request.user)
    project = None
    if pk:
        _, project = _project(request, pk, "projects.change_project")
    else:
        _require(request.user, company, "projects.add_project")
    form = ProjectForm(request.POST or None, instance=project, company=company)
    if request.method == "POST" and form.is_valid():
        if _code_taken(company, form.cleaned_data["code"], exclude_pk=pk):
            form.add_error("code", "Another project in this company uses this code.")
        else:
            project = form.save(commit=False)
            project.company = company
            try:
                project.full_clean()
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                project.save()
                messages.success(request, f"Project {project.code} saved.")
                return redirect("projects:detail", pk=project.pk)
    return render(request, "projects/project_form.html", {"form": form, "project": project})


@login_required
def project_detail(request, pk):
    company, project = _project(request, pk)
    can_add_task = _can(request.user, company, "projects.add_task")
    task_form = TaskForm(request.POST or None, company=company) if can_add_task else None
    if request.method == "POST":
        if not can_add_task:
            raise PermissionDenied
        if task_form.is_valid():
            task = task_form.save(commit=False)
            task.project = project
            try:
                task.full_clean()
            except ValidationError as exc:
                task_form.add_error(None, exc)
            else:
                task.save()
                messages.success(request, "Task added.")
                return redirect("projects:detail", pk=project.pk)
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "tasks": project.tasks.select_related("assignee"),
            "summary": services.project_summary(project),
            "task_form": task_form,
            "status_choices": Task.Status.choices,
            "can_edit": _can(request.user, company, "projects.change_project"),
            "can_change_task": _can(request.user, company, "projects.change_task"),
            "can_view_costs": _can(request.user, company, "projects.view_projectcostallocation"),
        },
    )


@login_required
def task_form(request, pk):
    company = active_company(request.user)
    _require(request.user, company, "projects.change_task")
    task = get_object_or_404(Task, pk=pk, project__company=company)
    form = TaskForm(request.POST or None, instance=task, company=company)
    if request.method == "POST" and form.is_valid():
        try:
            form.instance.full_clean()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            form.save()
            messages.success(request, "Task saved.")
            return redirect("projects:detail", pk=task.project_id)
    return render(request, "projects/task_form.html", {"form": form, "task": task})


@login_required
@require_POST
def task_status(request, pk):
    company = active_company(request.user)
    _require(request.user, company, "projects.change_task")
    task = get_object_or_404(Task, pk=pk, project__company=company)
    form = TaskStatusForm(request.POST)
    if form.is_valid():
        task.status = form.cleaned_data["status"]
        task.save(update_fields=["status", "updated_at"])
    return redirect("projects:detail", pk=task.project_id)


@login_required
def timesheet_time(request, timesheet_pk):
    from payroll.models import Timesheet

    company = active_company(request.user)
    sheet = get_object_or_404(
        Timesheet, pk=timesheet_pk, company=company, employee__user=request.user
    )
    editable = services.timesheet_is_editable(sheet)
    form = TimeEntryForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        try:
            services.add_time_entry(actor=request.user, timesheet=sheet, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Project time added.")
            return redirect("projects:timesheet_time", timesheet_pk=sheet.pk)
    return render(
        request,
        "projects/timesheet_time.html",
        {
            "sheet": sheet,
            "entries": sheet.project_time.select_related("project", "task"),
            "booked": services.booked_hours(sheet),
            "form": form if editable else None,
            "editable": editable,
        },
    )


@login_required
@require_POST
def time_entry_delete(request, pk):
    company = active_company(request.user)
    entry = get_object_or_404(
        TimeEntry, pk=pk, timesheet__company=company, timesheet__employee__user=request.user
    )
    try:
        services.remove_time_entry(actor=request.user, entry=entry)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("projects:timesheet_time", timesheet_pk=entry.timesheet_id)


@login_required
def project_costs(request):
    from payroll.models import PayrollRun

    company = active_company(request.user)
    _require(request.user, company, "projects.view_projectcostallocation")
    # all_objects: include inactive runs; costing applies to every run.
    runs = PayrollRun.all_objects.filter(company=company).order_by("-paydays", "-pk")
    run = None
    run_id = request.POST.get("run") or request.GET.get("run")
    if run_id:
        run = get_object_or_404(runs, pk=run_id)
    elif runs:
        run = runs[0]
    if request.method == "POST":
        _require(request.user, company, "projects.add_projectcostallocation")
        if run is None:
            raise PermissionDenied
        rows = services.allocate_run_costs(run)
        messages.success(request, f"Project costs recalculated: {len(rows)} allocation(s).")
        return redirect(f"{request.path}?run={run.pk}")
    return render(
        request,
        "projects/project_costs.html",
        {
            "runs": runs,
            "run": run,
            "summary": services.run_cost_summary(run) if run else None,
            "can_allocate": _can(request.user, company, "projects.add_projectcostallocation"),
        },
    )
