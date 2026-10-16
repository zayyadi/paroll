"""Browser consumers of the HR domain services."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from payroll import models
from payroll.forms.hr_surfaces import LeaveTypeForm, TimesheetForm, DatasetQueryForm
from payroll.services.hr_surfaces import active_company, require_permission, timesheets_for, save_timesheet, RESOURCES


@login_required
@require_GET
def people_analytics(request):
    from integrations.people_analytics import dataset_as_json
    company = active_company(request.user)
    require_permission(request.user, company, "payroll.view_employeeprofile")
    require_permission(request.user, company, "payroll.view_payrollentry")
    form = DatasetQueryForm(request.GET)
    dataset = None
    if form.is_valid():
        dataset = dataset_as_json(company, **form.cleaned_data)
    if request.GET.get("format") == "json":
        return JsonResponse(dataset if dataset else {"errors": form.errors.get_json_data()}, status=200 if dataset else 400)
    return render(request, "payroll/people_analytics.html", {"form": form, "dataset": dataset})


@login_required
def timesheets(request):
    active_company(request.user)
    form = TimesheetForm(request.POST or None, initial={"week_start": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            save_timesheet(actor=request.user, **form.cleaned_data)
        except models.EmployeeProfile.DoesNotExist:
            form.add_error(None, "Your account needs an employee profile.")
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Timesheet saved.")
            return redirect("payroll:timesheets")
    from approvals.permissions import can_decide
    from django.core.paginator import Paginator
    rows = Paginator(timesheets_for(request.user), 50).get_page(request.GET.get("page"))
    for sheet in rows:
        sheet.can_decide = bool(sheet.approval_request_id and can_decide(sheet.approval_request, request.user))
    return render(request, "payroll/timesheets.html", {"form": form, "sheets": rows})


@login_required
@require_POST
def timesheet_action(request, pk):
    from payroll.services.timesheet_service import submit_timesheet, cancel_timesheet
    from approvals.services import decide_approval
    sheet = get_object_or_404(timesheets_for(request.user), pk=pk)
    action = request.POST.get("action")
    try:
        if action == "submit":
            submit_timesheet(timesheet=sheet, actor=request.user)
        elif action == "withdraw":
            cancel_timesheet(timesheet=sheet, actor=request.user)
        elif action in ("approve", "reject") and sheet.approval_request_id:
            decide_approval(approval=sheet.approval_request, actor=request.user,
                            decision=action.upper(), comment=request.POST.get("comment", ""))
        else:
            raise ValidationError("Select a valid timesheet action.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Timesheet action recorded.")
    return redirect("payroll:timesheets")


@login_required
def leave_types(request, pk=None):
    from payroll.services.leave_type_service import ensure_default_leave_types
    company = active_company(request.user)
    require_permission(request.user, company, "payroll.view_leavetype")
    ensure_default_leave_types(company)
    instance = get_object_or_404(models.LeaveType, pk=pk, company=company) if pk else None
    form = LeaveTypeForm(request.POST or None, instance=instance, company=company)
    if request.method == "POST":
        require_permission(request.user, company, "payroll.change_leavetype" if instance else "payroll.add_leavetype")
        if form.is_valid():
            form.save()
            messages.success(request, "Leave type saved. Entitlements apply when a yearly balance is first granted.")
            return redirect("payroll:leave_types")
    return render(request, "payroll/leave_types.html", {"form": form, "leave_types": models.LeaveType.objects.filter(company=company)})


@login_required
@require_GET
def hr_records(request, resource):
    if resource not in RESOURCES:
        raise Http404
    model, scope = RESOURCES[resource]
    company = active_company(request.user)
    require_permission(request.user, company, f"payroll.view_{model._meta.model_name}")
    from django.core.paginator import Paginator
    rows = Paginator(model.objects.filter(**{scope: company}).order_by("-pk"), 50).get_page(request.GET.get("page"))
    fields = [f for f in model._meta.fields if (not f.is_relation or f.name == "employee") and f.name not in {"is_deleted", "deleted_at"}]
    return render(request, "payroll/hr_records.html", {
        "title": model._meta.verbose_name_plural.title(), "headers": [f.verbose_name for f in fields],
        "rows": [[getattr(row, f.name) for f in fields] for row in rows], "page": rows,
    })
