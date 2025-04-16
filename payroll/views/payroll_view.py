from typing import Any
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse_lazy

from django.views.generic import CreateView

from django.contrib import messages

# from django.core.cache import cache
from django.http import HttpResponseForbidden

# from django.core.files.storage import FileSystemStorage
from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT


from payroll.forms import (
    AllowanceForm,
    IOUApprovalForm,
    IOURequestForm,
    LeaveRequestForm,
    PaydayForm,
    PayrollForm,
)
from payroll.models import (
    EmployeeProfile,
    LeavePolicy,
    LeaveRequest,
    PayT,
    Payday,
    Payroll,
    Allowance,
    IOU,
    AuditTrail,
)

from payroll import utils


CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)


def check_super(user):
    return user.is_superuser


@user_passes_test(check_super)
def add_pay(request):
    form = PayrollForm(request.POST or None)

    if form.is_valid():
        form.save()
        messages.success(request, "Pay created successfully")
        return redirect("payroll:index")

    else:
        form = PayrollForm()

    return render(request, "pay/add_pay.html", {"form": form})


@user_passes_test(check_super)
def delete_pay(request, id):
    pay = get_object_or_404(Payroll, id=id)
    pay.delete()
    messages.success(request, "Pay deleted Successfully!!")


# @cache_page(CACHE_TTL)
@login_required
@user_passes_test(check_super)
def dashboard(request):
    emp = EmployeeProfile.objects.all()

    context = {
        # "payroll":payroll,
        # "payt": payt
        "emp": emp
    }
    return render(request, "pay/dashboard.html", context)


@login_required
def list_payslip(request, emp_slug):
    emp = EmployeeProfile.objects.filter(slug=emp_slug).first()
    pay = Payday.objects.filter(payroll_id__pays__slug=emp_slug).all()
    paydays = Payday.objects.filter(payroll_id__pays__slug=emp_slug).values_list(
        "paydays_id__paydays", flat=True
    )
    conv_date = [utils.convert_month_to_word(str(payday)) for payday in paydays]

    context = {
        "emp": emp,
        "pay": pay,
        "dates": conv_date,
    }

    return render(request, "pay/list_payslip.html", context)


def create_allowance(request):
    a_form = AllowanceForm(request.POST or None)

    if a_form.is_valid():
        a_form.save()
        messages.success(request, "Pay created successfully")
        return redirect("payroll:index")

    else:
        a_form = AllowanceForm()

    return render(request, "pay/add_allowance.html", {"form": a_form})


@user_passes_test(check_super)
def edit_allowance(request, id):
    var = get_object_or_404(Allowance, id=id)
    form = AllowanceForm(request.POST or None, instance=var)

    if form.is_valid():
        form.save()
        messages.success(request, "Variable updated successfully!!")
        return redirect("payroll:dashboard")

    else:
        form = AllowanceForm()

    context = {
        "form": form,
        "var": var,
    }
    return render(request, "pay/var.html", context)


@user_passes_test(check_super)
def delete_allowance(request, id):
    pay = get_object_or_404(Allowance, id=id)
    pay.delete()
    messages.success(request, "Allowance deleted Successfully!!")


class AddPay(CreateView):
    model = PayT
    form_class = PaydayForm
    template_name = "pay/add_payday.html"
    success_url = reverse_lazy("payroll:index")

    def get(self, request, *args, **kwargs):
        form = PaydayForm()  # Create an instance of your form
        return render(request, self.template_name, {"form": form})

    def post(self, request, **kwargs: Any) -> dict[str, Any]:
        form = PaydayForm(request.POST or None)

        if request.POST and form.is_valid():
            name = form.cleaned_data["name"]
            slug = form.cleaned_data["slug"]
            paydays = form.cleaned_data["paydays"]
            is_active = form.cleaned_data["is_active"]

            obj = PayT(
                name=name,
                slug=slug,
                paydays=paydays,
                is_active=is_active,
            )

            obj.save()
            forms = PaydayForm(request.POST, instance=obj)
            forms.save(commit=False)
            forms.save_m2m()
            messages.success(request, "Variable updated successfully!!")
            return redirect("payroll:dashboard")

        else:
            form = PaydayForm()
            return render(request, self.template_name, {"form": form})


def varview(request):
    var = PayT.objects.order_by("paydays").distinct("paydays")
    dates = [utils.convert_month_to_word(str(varss)) for varss in var]

    context = {
        "pay_var": var,
        "dates": dates,
    }

    return render(request, "pay/var_view.html", context)


@login_required
@permission_required("leave.add_leaverequest", raise_exception=True)
def apply_leave(request):
    if request.method == "POST":
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = request.user
            leave_request.save()
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm()
    return render(request, "employee/apply_leave.html", {"form": form})


@login_required
def leave_requests(request):
    requests = LeaveRequest.objects.filter(employee=request.user)
    return render(request, "employee/leave_requests.html", {"requests": requests})


@login_required
@permission_required("change_leaverequest", raise_exception=True)
def manage_leave_requests(request):

    requests = LeaveRequest.objects.filter(status="PENDING")
    return render(
        request, "employee/manage_leave_requests.html", {"requests": requests}
    )


@login_required
@permission_required("change_leaverequest", raise_exception=True)
def approve_leave(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    leave_request.status = "APPROVED"
    leave_request.save()
    return redirect("payroll:manage_leave_requests")


@login_required
@permission_required("change_leaverequest", raise_exception=True)
def reject_leave(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    leave_request.status = "REJECTED"
    leave_request.save()
    return redirect("payroll:manage_leave_requests")


@login_required
def leave_policies(request):
    policies = LeavePolicy.objects.all()
    return render(request, "employee/leave_policies.html", {"policies": policies})


def edit_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if request.method == "POST":
        form = LeaveRequestForm(request.POST, instance=leave_request)
        if form.is_valid():
            form.save()
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm(instance=leave_request)
    return render(request, "employee/edit_leave_request.html", {"form": form})


def delete_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    leave_request.delete()
    return redirect("payroll:leave_requests")


def view_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    return render(
        request, "employee/view_leave_request.html", {"leave_request": leave_request}
    )


@login_required
def request_iou(request):
    if request.method == "POST":
        form = IOURequestForm(request.POST)
        if form.is_valid():
            iou = form.save(commit=False)
            if hasattr(request.user, "employee_profile"):
                iou.employee_id = request.user.employee_profile
                iou.save()
                return redirect("iou_history")
            else:
                # Handle the case where the user doesn't have an employee profile
                form.add_error(
                    None, "User does not have an associated employee profile."
                )
    else:
        form = IOURequestForm()
    return render(request, "iou/request_iou.html", {"form": form})


@login_required
def approve_iou(request, iou_id):
    iou = get_object_or_404(IOU, id=iou_id)
    if not request.user.is_staff:  # Only staff can approve IOUs
        return HttpResponseForbidden("You do not have permission to approve IOUs.")

    if request.method == "POST":
        form = IOUApprovalForm(request.POST, instance=iou)
        if form.is_valid():
            form.save()
            return redirect("iou_history")
    else:
        form = IOUApprovalForm(instance=iou)
    return render(request, "iou/approve_iou.html", {"form": form, "iou": iou})


@login_required
def iou_history(request):
    if request.user.is_staff:  # Managers can view all IOUs
        ious = IOU.objects.all()
    else:  # Employees can only view their own IOUs
        if hasattr(request.user, "employee_profile"):
            ious = IOU.objects.filter(employee_id=request.user.employee_profile)
        else:
            ious = IOU.objects.none()  # Return an empty queryset if no profile exists
    return render(request, "iou/iou_history.html", {"ious": ious})


def log_audit_trail(user, action, content_object):
    AuditTrail.objects.create(
        user=user,
        action=action,
        content_object=content_object,
    )


@login_required
def restore_employee(request, id):
    employee = get_object_or_404(EmployeeProfile, id=id, deleted_at__isnull=False)
    employee.restore()
    log_audit_trail(request.user, "restore", employee)
    messages.success(request, "Employee restored successfully!")
    return redirect("payroll:employee_list")
