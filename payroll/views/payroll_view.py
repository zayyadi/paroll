from typing import Any
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.db.models import Q

from django.views.generic import CreateView

from django.contrib import messages

# from django.core.cache import cache
from django.http import HttpResponseForbidden
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

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

    context = {"form": form}
    return render(request, "pay/add_pay.html", context)


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


@user_passes_test(check_super)
def create_allowance(request):
    a_form = AllowanceForm(request.POST or None)

    if a_form.is_valid():
        a_form.save()
        messages.success(request, "Allowance created successfully")
        return redirect("payroll:index")

    context = {"form": a_form}
    return render(request, "pay/add_allowance.html", context)


@user_passes_test(check_super)
def edit_allowance(request, id):
    var = get_object_or_404(Allowance, id=id)
    form = AllowanceForm(request.POST or None, instance=var)

    if form.is_valid():
        form.save()
        messages.success(request, "Allowance updated successfully!!")
        return redirect("payroll:dashboard")

    else:
        form = AllowanceForm(instance=var)  # Corrected line

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


class AddPay(LoginRequiredMixin, UserPassesTestMixin, CreateView):
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
            # The following lines are redundant for a CreateView's form_valid
            # forms = PaydayForm(request.POST, instance=obj)
            # forms.save(commit=False)
            # forms.save_m2m()
            messages.success(
                self.request, "Payday created successfully!!"
            )  # Changed message
            return redirect(self.get_success_url())  # Use get_success_url

        else:
            form = PaydayForm(request.POST)  # Retain data on invalid form
            return render(request, self.template_name, {"form": form})

    def test_func(self):
        return check_super(self.request.user)


@user_passes_test(check_super)
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
            # Fix: Assign EmployeeProfile, not CustomUser
            if hasattr(request.user, "employee_profile"):
                leave_request.employee = request.user.employee_profile
            else:
                messages.error(
                    request, "User does not have an associated employee profile."
                )
                return redirect(
                    "payroll:apply_leave"
                )  # Redirect back to form with error
            leave_request.save()
            messages.success(
                request, "Leave request submitted successfully."
            )  # Added success message
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm()
    return render(request, "employee/apply_leave.html", {"form": form})


@login_required
def leave_requests(request):
    if hasattr(request.user, 'employee_profile'):
        requests = LeaveRequest.objects.filter(employee=request.user.employee_profile).order_by('-created_at')
    else:
        # If the user has no employee profile, they shouldn't have any leave requests.
        requests = LeaveRequest.objects.none()
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
    messages.success(request, "Leave request approved.")  # Added success message
    return redirect("payroll:manage_leave_requests")


@login_required
@permission_required("change_leaverequest", raise_exception=True)
def reject_leave(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    leave_request.status = "REJECTED"
    leave_request.save()
    messages.success(request, "Leave request rejected.")  # Added success message
    return redirect("payroll:manage_leave_requests")


@login_required
def leave_policies(request):
    policies = LeavePolicy.objects.all()
    return render(request, "employee/leave_policies.html", {"policies": policies})


@login_required
def edit_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if not (request.user == leave_request.employee.user or request.user.is_staff or check_super(request.user)):
        raise HttpResponseForbidden("You are not authorized to edit this leave request.")
    if request.method == "POST":
        form = LeaveRequestForm(request.POST, instance=leave_request)
        if form.is_valid():
            form.save()
            messages.success(
                request, "Leave request updated successfully."
            )  # Added success message
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm(instance=leave_request)
    return render(request, "employee/edit_leave_request.html", {"form": form})


@login_required
def delete_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if not (request.user == leave_request.employee.user or request.user.is_staff or check_super(request.user)):
        raise HttpResponseForbidden("You are not authorized to delete this leave request.")
    leave_request.delete()
    messages.success(
        request, "Leave request deleted successfully."
    )  # Added success message
    return redirect("payroll:leave_requests")


@login_required
def view_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if not (request.user == leave_request.employee.user or request.user.is_staff or check_super(request.user)):
        raise HttpResponseForbidden("You are not authorized to view this leave request.")
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
                messages.success(
                    request, "IOU request submitted successfully."
                )  # Added success message
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
            messages.success(
                request, "IOU approved successfully."
            )  # Added success message
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


def log_audit_trail(
    user, action, content_object, changes=None
):  # Added changes parameter
    if changes is None:
        changes = {}
    AuditTrail.objects.create(
        user=user,
        action=action,
        content_object=content_object,
        changes=changes,  # Pass changes to AuditTrail
    )


@user_passes_test(check_super)
def audit_trail_list(request):
    query = request.GET.get("q")
    user_filter = request.GET.get("user")
    action_filter = request.GET.get("action")

    logs = AuditTrail.objects.all().order_by("-timestamp")

    if query:
        logs = logs.filter(
            Q(user__username__icontains=query)
            | Q(action__icontains=query)
            | Q(content_type__model__icontains=query)
            | Q(content_object__icontains=query)
        )

    if user_filter:
        logs = logs.filter(user__username__icontains=user_filter)

    if action_filter:
        logs = logs.filter(action__icontains=action_filter)

    paginator = Paginator(logs, 10)  # 10 logs per page
    page_number = request.GET.get("page")
    audit_logs = paginator.get_page(page_number)

    context = {
        "audit_logs": audit_logs,
        "query": query,
        "user_filter": user_filter,
        "action_filter": action_filter,
    }
    return render(request, "pay/audit_trail_list.html", context)


@user_passes_test(check_super)
def audit_trail_detail(request, pk):
    log = get_object_or_404(AuditTrail, pk=pk)
    return render(request, "pay/audit_trail_detail.html", {"log": log})


@login_required
def restore_employee(request, id):
    employee = get_object_or_404(EmployeeProfile, id=id, deleted_at__isnull=False)
    # Capture changes for audit trail
    old_status = "deleted"
    new_status = "active"
    changes = {"status": {"old": old_status, "new": new_status}}
    employee.restore()
    log_audit_trail(request.user, "restore", employee, changes=changes)  # Pass changes
    messages.success(request, "Employee restored successfully!")
    return redirect("payroll:employee_list")


@login_required
def iou_list(request):
    ious = IOU.objects.all()
    return render(request, "iou/iou_list.html", {"ious": ious})


@login_required
def iou_detail(request, pk):
    iou = get_object_or_404(IOU, pk=pk)
    return render(request, "iou/iou_detail.html", {"iou": iou})
