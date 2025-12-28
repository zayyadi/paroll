from datetime import date
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.generic import CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseForbidden
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)
from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.template.loader import render_to_string
from num2words import num2words
from payroll.models.payroll import get_leave_balance
from users.email_backend import send_mail as custom_send_mail
from core.settings import DEFAULT_FROM_EMAIL
import io
from xhtml2pdf import pisa

from payroll.forms import (
    AllowanceForm,
    IOUApprovalForm,
    IOURequestForm,
    IOUUpdateForm,
    LeaveRequestForm,
    PaydayForm,
    PayrollForm,
    DeductionForm,
    PaydayCreateForm,
    PayVarCreateForm,
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
    Deduction,
    PayVar,
)
from django.utils import timezone
from accounting.models import Account
from accounting.utils import create_journal_entry
from accounting.permissions import (
    is_auditor,
    can_view_payroll_data,
    can_modify_payroll_data,
)
from payroll import utils

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)

logger = logging.getLogger(__name__)


def generate_payslip_pdf(payslip_data, template_path="pay/payslip_pdf.html"):
    """Generates a PDF payslip from an HTML template."""
    template = render_to_string(template_path, payslip_data)
    result = io.BytesIO()
    pdf = pisa.pisaDocument(io.BytesIO(template.encode("UTF-8")), result)
    if not pdf.err:
        return result.getvalue()
    return None


@permission_required("payroll.add_payroll", raise_exception=True)
def add_pay(request):
    form = PayrollForm(request.POST or None)
    if form.is_valid():
        employee = form.cleaned_data["employee"]
        basic_salary = form.cleaned_data["basic_salary"]

        payroll_instance = Payroll.objects.create(basic_salary=basic_salary)
        employee.employee_pay = payroll_instance
        employee.save()

        messages.success(request, "Pay created successfully")

        # Create Journal Entries
        try:
            salary_expense_account = Account.objects.get(name="Salary Expense")
            pension_expense_account = Account.objects.get(name="Pension Expense")
            salaries_payable_account = Account.objects.get(name="Salaries Payable")
            pension_payable_account = Account.objects.get(name="Pension Payable")
            tax_payable_account = Account.objects.get(name="PAYE Tax Payable")
            nsitf_payable_account = Account.objects.get(name="NSITF Payable")

            entries = [
                {
                    "account": salary_expense_account,
                    "entry_type": "DEBIT",
                    "amount": payroll_instance.gross_income,
                },
                {
                    "account": pension_expense_account,
                    "entry_type": "DEBIT",
                    "amount": payroll_instance.pension_employer,
                },
                {
                    "account": salaries_payable_account,
                    "entry_type": "CREDIT",
                    "amount": employee.net_pay,
                },
                {
                    "account": pension_payable_account,
                    "entry_type": "CREDIT",
                    "amount": payroll_instance.pension,
                },
                {
                    "account": tax_payable_account,
                    "entry_type": "CREDIT",
                    "amount": payroll_instance.payee,
                },
                {
                    "account": nsitf_payable_account,
                    "entry_type": "CREDIT",
                    "amount": payroll_instance.nsitf,
                },
            ]
            create_journal_entry(
                date=timezone.now().date(),
                description=f"Payroll for {employee.first_name} {employee.last_name}",
                entries=entries,
            )
            messages.success(request, "Journal entries created successfully.")
        except Account.DoesNotExist as e:
            messages.error(request, f"Failed to create journal entries: {e}")
        except Exception as e:
            messages.error(request, f"An unexpected error occurred: {e}")

        # Send payslip email
        if employee and employee.user and employee.user.email:
            payslip_data = {
                "payroll": payroll_instance,
                "employee": employee,
                # Add any other data needed for the payslip template
            }
            pdf_content = generate_payslip_pdf(payslip_data)

            if pdf_content:
                subject = f"Your Payslip for {payroll_instance.month_year}"
                context = {
                    "user": employee.user,
                    "payroll": payroll_instance,
                    "month_year": payroll_instance.month_year,
                }

                # Prepare attachments for custom_send_mail
                attachments = [
                    {
                        "filename": f"payslip_{employee.user.username}_{payroll_instance.month_year}.pdf",
                        "content": pdf_content,
                        "mimetype": "application/pdf",
                    }
                ]

                custom_send_mail(
                    subject,
                    "email/payslip_email.html",
                    context,
                    DEFAULT_FROM_EMAIL,
                    [employee.user.email],
                    attachments=attachments,
                )
                messages.info(request, f"Payslip sent to {employee.user.email}")
            else:
                messages.error(request, "Failed to generate payslip PDF.")
        else:
            messages.warning(request, "Employee email not found, payslip not sent.")

        return redirect("payroll:index")
    context = {"form": form}
    return render(request, "pay/add_pay.html", context)


@permission_required("payroll.delete_payroll", raise_exception=True)
def delete_pay(
    request, id
):  # This function was missing from the plan but existed in file, applying perm
    pay = get_object_or_404(Payroll, id=id)
    pay.delete()
    messages.success(request, "Pay deleted Successfully!!")
    return redirect(
        "payroll:index"
    )  # Assuming redirect to index or a relevant list view


@permission_required(
    "payroll.view_payroll", raise_exception=True
)  # Or a more specific dashboard permission
def dashboard(request):  # payroll admin dashboard
    # Check if user can view payroll data (auditors have view-only access)
    if not can_view_payroll_data(request.user):
        return HttpResponseForbidden("You don't have permission to view payroll data.")

    emp = (
        EmployeeProfile.objects.all()
    )  # Consider if this list needs to be permission controlled
    context = {
        "emp": emp,
        "empty_list": [],  # For empty for loop handling in templates
        "is_auditor": is_auditor(request.user),  # Add auditor flag for template
    }
    return render(request, "pay/dashboard_new.html", context)


@login_required
def list_payslip(request, emp_slug):
    emp = get_object_or_404(EmployeeProfile, slug=emp_slug)

    # Check if user can view payroll data (auditors have view-only access)
    if not (
        request.user == emp.user
        or request.user.has_perm("payroll.view_payroll")
        or is_auditor(request.user)
    ):
        raise HttpResponseForbidden("You are not authorized to view this payslip.")

    pay = Payday.objects.filter(payroll_id__pays__slug=emp_slug).all()
    paydays = Payday.objects.filter(payroll_id__pays__slug=emp_slug).values_list(
        "paydays_id__paydays", flat=True
    )
    conv_date = [utils.convert_month_to_word(str(payday)) for payday in paydays]
    context = {
        "emp": emp,
        "pay": pay,
        "dates": conv_date,
        "is_auditor": is_auditor(request.user),  # Add auditor flag for template
    }
    return render(request, "pay/list_payslip_new.html", context)


@login_required
def payslips(request):
    """View to show payslips for the current logged-in user"""
    # Check if user can view payroll data (auditors have view-only access)
    if not can_view_payroll_data(request.user):
        return HttpResponseForbidden("You don't have permission to view payroll data.")

    try:
        employee_profile = request.user.employee_user
        pay = Payday.objects.filter(payroll_id__pays__user=request.user).all()
        paydays = Payday.objects.filter(
            payroll_id__pays__user=request.user
        ).values_list("paydays_id__paydays", flat=True)
        conv_date = [utils.convert_month_to_word(str(payday)) for payday in paydays]
        context = {
            "emp": employee_profile,
            "pay": pay,
            "dates": conv_date,
            "is_auditor": is_auditor(request.user),  # Add auditor flag for template
        }
        return render(request, "pay/list_payslip_new.html", context)
    except EmployeeProfile.DoesNotExist:
        messages.error(
            request,
            "Your user account is not linked to an employee profile. Please contact HR.",
        )
        return redirect("payroll:dashboard_hr")


@login_required
def payslip_detail(request, id):
    pay_id = get_object_or_404(Payday, id=id)
    target_employee_user = pay_id.payroll_id.pays.user

    # Check if user can view payroll data (auditors have view-only access)
    if not (
        request.user == target_employee_user
        or request.user.has_perm("payroll.view_payroll")
        or is_auditor(request.user)
    ):
        raise HttpResponseForbidden("You are not authorized to view this payslip.")

    num2word = num2words(pay_id.payroll_id.netpay)
    dates = utils.convert_month_to_word(str(pay_id.paydays_id.paydays))
    pay_ids = pay_id.payroll_id.pays.pk
    # pay_id = pay_id.payroll_id.pays.pk
    print(pay_id)
    pay_id_nhif = pay_id.payroll_id.nhif
    pay_id_nhf = pay_id.payroll_id.nhf
    pay_id_nsitf = pay_id.payroll_id.pays.employee_pay.nsitf / 12
    pay_id_payee = pay_id.payroll_id.pays.employee_pay.payee
    pay_id_pension = pay_id.payroll_id.pays.employee_pay.pension / 12
    pay_id_gross = pay_id.payroll_id.pays.employee_pay.gross_income / 12
    pay_id_net = pay_id.payroll_id.netpay / 12
    pay_id_housing = pay_id.payroll_id.pays.employee_pay.housing / 12
    pay_id_transport = pay_id.payroll_id.pays.employee_pay.transport / 12
    pay_id_taxable = pay_id.payroll_id.pays.employee_pay.taxable_income / 12
    pay_id_water = pay_id.payroll_id.pays.employee_pay.water_rate
    # pay_id_
    context = {
        "pay": pay_id,
        "pays": pay_ids,
        "num2words": num2word,
        "dates": dates,
        "pay_id_nhif": pay_id_nhif,
        "pay_id_nhf": pay_id_nhf,
        "pay_id_nsitf": pay_id_nsitf,
        "pay_id_payee": pay_id_payee,
        "pay_id_pension": pay_id_pension,
        "pay_id_gross": pay_id_gross,
        "pay_id_net": pay_id_net,
        "pay_id_housing": pay_id_housing,
        "pay_id_transport": pay_id_transport,
        "pay_id_taxable": pay_id_taxable,
        "pay_id_water_rate": pay_id_water,
        "is_auditor": is_auditor(request.user),  # Add auditor flag for template
    }
    return render(request, "pay/payslip_new.html", context)


@permission_required("payroll.add_allowance", raise_exception=True)
def create_allowance(request):
    # Check if user can modify payroll data (auditors have view-only access)
    if not can_modify_payroll_data(request.user):
        return HttpResponseForbidden(
            "You don't have permission to modify payroll data."
        )

    a_form = AllowanceForm(request.POST or None)
    if a_form.is_valid():
        a_form.save()
        messages.success(request, "Allowance created successfully")
        return redirect("payroll:index")
    context = {"form": a_form}
    return render(request, "pay/add_allowance.html", context)


@permission_required("payroll.change_allowance", raise_exception=True)
def edit_allowance(request, id):
    # Check if user can modify payroll data (auditors have view-only access)
    if not can_modify_payroll_data(request.user):
        return HttpResponseForbidden(
            "You don't have permission to modify payroll data."
        )

    var = get_object_or_404(Allowance, id=id)
    form = AllowanceForm(request.POST or None, instance=var)
    if form.is_valid():
        form.save()
        messages.success(request, "Allowance updated successfully!!")
        return redirect("payroll:dashboard")  # Or a list view for allowances
    context = {"form": form, "var": var}
    return render(
        request, "pay/var.html", context
    )  # var.html seems generic, consider renaming template


@permission_required("payroll.delete_allowance", raise_exception=True)
def delete_allowance(request, id):
    # Check if user can modify payroll data (auditors have view-only access)
    if not can_modify_payroll_data(request.user):
        return HttpResponseForbidden(
            "You don't have permission to modify payroll data."
        )

    allowance_obj = get_object_or_404(Allowance, id=id)  # Renamed variable
    allowance_obj.delete()
    messages.success(request, "Allowance deleted Successfully!!")
    return redirect("payroll:dashboard")  # Or a list view for allowances


# @permission_required("payroll.add_deduction", raise_exception=True)
class AddDeduction(PermissionRequiredMixin, CreateView):
    model = Deduction
    form_class = DeductionForm
    template_name = "pay/add_deduction.html"  # New template for deductions
    success_url = reverse_lazy(
        "payroll:dashboard_hr"
    )  # Redirect to HR dashboard or a list of deductions
    permission_required = "payroll.add_deduction"

    def dispatch(self, request, *args, **kwargs):
        # Check if user can modify payroll data (auditors have view-only access)
        if not can_modify_payroll_data(request.user):
            return HttpResponseForbidden(
                "You don't have permission to modify payroll data."
            )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Deduction created successfully!!")
        return super().form_valid(form)


class AddPay(
    PermissionRequiredMixin, CreateView
):  # Removed LoginRequiredMixin, UserPassesTestMixin
    model = PayT
    form_class = PaydayForm
    template_name = "pay/add_payday.html"
    success_url = reverse_lazy("payroll:pay_period_list")
    permission_required = "payroll.add_payt"

    # Removed get and post methods if standard CreateView behavior is sufficient with form_class
    # If custom logic within get/post is needed beyond form_valid, it can be kept.
    # For now, assuming standard CreateView. If issues arise, these can be re-evaluated.
    def form_valid(self, form):
        # Save the PayT instance first
        self.object = form.save(commit=False)
        self.object.save()  # Now save the PayT instance to the database

        # Handle the ManyToMany field with the 'through' model
        selected_payvars = form.cleaned_data["payroll_payday"]
        for payvar_obj in selected_payvars:
            Payday.objects.create(paydays_id=self.object, payroll_id=payvar_obj)

        messages.success(self.request, "Payday (PayT) created successfully!!")
        return super().form_valid(form)  # This will now just handle the redirect


@permission_required("payroll.view_payt", raise_exception=True)
def varview(request):  # Lists PayT objects (Pay Periods)
    var = PayT.objects.order_by("paydays").distinct("paydays")
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in var
    ]  # Access .paydays attribute
    context = {"pay_var": var, "dates": dates}
    return render(request, "pay/var_view.html", context)


# New Views for PayT (Pay Periods)


@permission_required("payroll.view_payt", raise_exception=True)
def pay_period_list(request):
    pay_periods = PayT.objects.all().order_by("-paydays")  # Order by most recent
    paginator = Paginator(pay_periods, 15)  # Show 15 pay periods per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "pay/pay_period_list.html", {"page_obj": page_obj})


@permission_required("payroll.view_payt", raise_exception=True)
def pay_period_detail(request, slug):
    pay_period = get_object_or_404(PayT, slug=slug)
    # Fetch related Payday entries if needed for detail view
    payday_entries = Payday.objects.filter(paydays_id=pay_period)
    context = {
        "pay_period": pay_period,
        "payday_entries": payday_entries,
    }
    return render(request, "pay/pay_period_detail.html", context)


class PayPeriodUpdateView(
    LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView
):
    model = PayT
    form_class = PaydayForm
    template_name = "pay/pay_period_form.html"  # Generic form template
    success_url = reverse_lazy("payroll:pay_period_list")
    permission_required = "payroll.change_payt"
    success_message = "Pay Period updated successfully."


class PayPeriodDeleteView(
    LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, DeleteView
):
    model = PayT
    template_name = "pay/pay_period_confirm_delete.html"
    success_url = reverse_lazy("payroll:pay_period_list")
    permission_required = "payroll.delete_payt"
    success_message = "Pay Period deleted successfully."


@permission_required("payroll.add_leaverequest", raise_exception=True)
def apply_leave(request):
    try:
        current_user = request.user.id
        employee_profile = EmployeeProfile.objects.get(user_id=current_user)
    except EmployeeProfile.DoesNotExist:
        # This can happen if the OneToOneField relation from User to EmployeeProfile
        # is not yet created for this user, or if the related_name is different.
        # Or, if EmployeeProfile has a ForeignKey to User, and no profile exists.
        messages.error(
            request,
            "Your user account is not linked to an employee profile. Please contact HR.",
        )
        # Redirect to a relevant page, perhaps the main dashboard or a profile creation page
        return redirect("payroll:dashboard_hr")
    if request.method == "POST":
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = employee_profile
            # Pass the current user to the save method for audit logging
            leave_request.save(user=request.user)
            messages.success(request, "Leave request submitted successfully.")
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm()
    return render(request, "employee/apply_leave_new.html", {"form": form})


# def calculate_days(start_date: date, end_date: date) -> int:
#     """
#     Returns number of days between two dates (inclusive).
#     """
#     if start_date > end_date:
#         raise ValueError("Start date cannot be after end date")

#     return (end_date - start_date).days + 1


@login_required
def leave_requests(request):
    user = request.user
    current_year = date.today().year

    try:
        employee_profile = user.employee_user

        # HR / Staff with permission can see all requests
        if user.has_perm("payroll.view_leaverequest"):
            leave_requests_qs = LeaveRequest.objects.select_related(
                "employee", "approved_by"
            ).order_by("-created_at")
        else:
            leave_requests_qs = LeaveRequest.objects.filter(employee=employee_profile)

        # Get leave balance for logged-in user (for dashboard display)
        leave_balance = get_leave_balance(employee_profile, current_year)

        # Calculate total leave taken in the current year
        approved_leaves = LeaveRequest.objects.filter(
            employee=employee_profile,
            status="APPROVED",
        )

        # pending_days = leave_requests_qs.

        # Calculate total days taken by summing durations of approved leaves
        leave_taken = sum(leave.duration for leave in approved_leaves)

        # Calculate pending requests count
        pending_count = LeaveRequest.objects.filter(
            employee=employee_profile, status="PENDING"
        ).count()

        # Calculate available days for each leave type
        if leave_balance:
            leave_balances = {
                "annual": leave_balance.annual_leave,
                "sick": leave_balance.sick_leave,
                "casual": leave_balance.casual_leave,
                "maternity": leave_balance.maternity_leave,
                "paternity": leave_balance.paternity_leave,
            }
        else:
            leave_balances = {}

    except EmployeeProfile.DoesNotExist:
        leave_requests_qs = LeaveRequest.objects.none()
        leave_balance = None
        leave_taken = 0
        pending_count = 0
        leave_balances = {}

        messages.info(
            request, "Your user account is not linked to an employee profile."
        )

    context = {
        "requests": leave_requests_qs,
        "leave_balance": leave_balance,
        "leave_balances": leave_balances,
        "leave_taken": leave_taken,
        "pending_count": pending_count,
        "current_year": current_year,
        "is_hr": user.has_perm("payroll.change_leaverequest"),
    }

    # print(f"leave taken: {leave_taken}  ")
    # print(f"pending count: {pending_count}  ")
    print(f" leave query: {leave_requests_qs}  ")

    return render(request, "employee/leave_requests_new.html", context)


@permission_required(
    "payroll.change_leaverequest", raise_exception=True
)  # For managing any leave request
def manage_leave_requests(request):
    requests = LeaveRequest.objects.filter(
        status="PENDING"
    )  # Shows only PENDING for action
    return render(
        request, "employee/manage_leave_requests.html", {"requests": requests}
    )


@permission_required("payroll.change_leaverequest", raise_exception=True)
def approve_leave(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    leave_request.status = "APPROVED"
    # Pass the current user to the save method for audit logging
    leave_request.save(user=request.user)
    messages.success(request, "Leave request approved.")
    return redirect("payroll:manage_leave_requests")


@permission_required("payroll.change_leaverequest", raise_exception=True)
def reject_leave(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    leave_request.status = "REJECTED"
    # Pass current user to the save method for audit logging
    leave_request.save(user=request.user)
    messages.success(request, "Leave request rejected.")
    return redirect("payroll:manage_leave_requests")


@permission_required("payroll.view_leavepolicy", raise_exception=True)
def leave_policies(request):
    policies = LeavePolicy.objects.all()
    return render(request, "employee/leave_policies.html", {"policies": policies})


@login_required  # Combined with object-level check
def edit_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    # User must be owner or have general change permission
    if not (
        request.user == leave_request.employee.user
        or request.user.has_perm("payroll.change_leaverequest")
    ):
        raise HttpResponseForbidden(
            "You are not authorized to edit this leave request."
        )

    if request.method == "POST":
        form = LeaveRequestForm(request.POST, instance=leave_request)
        if form.is_valid():
            # Pass the current user to the save method for audit logging
            form.save(user=request.user)
            messages.success(request, "Leave request updated successfully.")
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm(instance=leave_request)
    return render(request, "employee/edit_leave_request.html", {"form": form})


@login_required  # Combined with object-level check
def delete_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    # User must be owner or have general delete permission
    if not (
        request.user == leave_request.employee.user
        or request.user.has_perm("payroll.delete_leaverequest")
    ):
        raise HttpResponseForbidden(
            "You are not authorized to delete this leave request."
        )
    leave_request.delete()
    messages.success(request, "Leave request deleted successfully.")
    return redirect("payroll:leave_requests")


@login_required  # Combined with object-level check
def view_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    # User must be owner or have general view permission
    if not (
        request.user == leave_request.employee.user
        or request.user.has_perm("payroll.view_leaverequest")
    ):
        raise HttpResponseForbidden(
            "You are not authorized to view this leave request."
        )
    return render(
        request, "employee/view_leave_request.html", {"leave_request": leave_request}
    )


# @permission_required(
#     "payroll.add_iou", raise_exception=True
# )  # User needs permission to add any IOU (usually self)
def request_iou(request):
    # Try to get the employee profile linked to the current user
    try:
        current_user = request.user.id
        employee_profile = EmployeeProfile.objects.get(user_id=current_user)
    except EmployeeProfile.DoesNotExist:
        # This can happen if the OneToOneField relation from User to EmployeeProfile
        # is not yet created for this user, or if the related_name is different.
        # Or, if EmployeeProfile has a ForeignKey to User, and no profile exists.
        messages.error(
            request,
            "Your user account is not linked to an employee profile. Please contact HR.",
        )
        # Redirect to a relevant page, perhaps the main dashboard or a profile creation page
        return redirect("payroll:dashboard_hr")  # Or any other appropriate URL

    if request.method == "POST":
        form = IOURequestForm(request.POST)
        if form.is_valid():
            iou = form.save(commit=False)
            iou.employee_id = employee_profile  # Assign the EmployeeProfile instance
            iou.save()
            messages.success(request, "IOU request submitted successfully.")
            return redirect("payroll:iou_history")
    else:
        # Pass the employee_profile to the form if you want to pre-fill or hide the employee field
        # This depends on how IOURequestForm is defined.
        # If 'employee_id' is a field in your form, you might want to make it read-only
        # or exclude it if it's always the current user.
        form = IOURequestForm(initial={"employee_id": employee_profile})
        # Or, if you exclude 'employee_id' from the form:
        # form = IOURequestForm()
        context = {
            "form": form,
            "employee_profile": employee_profile,  # Pass the profile for context
        }

    return render(request, "iou/request_iou_new.html", context)


@permission_required(
    "payroll.change_iou", raise_exception=True
)  # For approving/rejecting IOUs
def approve_iou(request, iou_id):
    iou = get_object_or_404(IOU, id=iou_id)
    if request.method == "POST":
        form = IOUApprovalForm(request.POST, instance=iou)
        if form.is_valid():
            form.save()
            messages.success(request, "IOU approved successfully.")
            return redirect(
                "payroll:iou_history"
            )  # Assuming iou_history is the correct name
    else:
        form = IOUApprovalForm(instance=iou)
    return render(request, "iou/approve_iou.html", {"form": form, "iou": iou})


class IOUUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = IOU
    form_class = IOUUpdateForm
    template_name = "iou/iou_update_form.html"  # Path to your update template
    context_object_name = "iou"  # To match {{ iou }} in your template
    success_url = reverse_lazy(
        "payroll:iou_list"
    )  # Redirect to IOU list view (assuming you have one)
    success_message = "IOU request updated successfully."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The 'iou' object (the instance being updated) is already in context
        # You can add more context if needed
        # context['page_title'] = f"Update IOU: {self.object.id}"
        return context

    # Optional: If you need to perform actions before/after form validation/saving
    # def form_valid(self, form):
    #     # For example, log who updated the IOU
    #     # form.instance.last_modified_by = self.request.user
    #     return super().form_valid(form)


class IOUDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = IOU
    template_name = (
        "iou/iou_confirm_delete.html"  # Path to your delete confirmation template
    )
    context_object_name = "iou"
    success_url = reverse_lazy("payroll:iou_list")  # Redirect to IOU list view
    success_message = "IOU request deleted successfully."


@login_required  # Shows user's own IOUs or all if staff/has permission
def iou_history(request):
    # Check if user can view payroll data (auditors have view-only access)
    if not can_view_payroll_data(request.user):
        return HttpResponseForbidden("You don't have permission to view payroll data.")

    try:
        employee_profile = request.user.employee_user
        if request.user.has_perm("payroll.view_iou"):  # Staff/HR with general view perm
            ious = IOU.objects.all().order_by("-created_at")
        else:
            ious = IOU.objects.filter(employee_id=employee_profile).order_by(
                "-created_at"
            )
    except EmployeeProfile.DoesNotExist:
        ious = IOU.objects.none()
        messages.info(
            request, "Your user account is not linked to an employee profile."
        )
    context = {
        "ious": ious,
        "is_auditor": is_auditor(request.user),  # Add auditor flag for template
    }
    return render(request, "iou/iou_history_new.html", context)


# log_audit_trail is a utility, no permission needed directly on it
def log_audit_trail(user, action, content_object, changes=None):
    if changes is None:
        changes = {}
    AuditTrail.objects.create(
        user=user, action=action, content_object=content_object, changes=changes
    )


@permission_required("payroll.view_audittrail", raise_exception=True)
def audit_trail_list(request):
    # ... (rest of the view logic remains the same)
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
    paginator = Paginator(logs, 10)
    page_number = request.GET.get("page")
    audit_logs = paginator.get_page(page_number)
    context = {
        "audit_logs": audit_logs,
        "query": query,
        "user_filter": user_filter,
        "action_filter": action_filter,
    }
    return render(request, "pay/audit_trail_list.html", context)


@permission_required("payroll.view_audittrail", raise_exception=True)
def audit_trail_detail(request, pk):
    log = get_object_or_404(AuditTrail, pk=pk)
    return render(request, "pay/audit_trail_detail.html", {"log": log})


@permission_required(
    "payroll.change_employeeprofile", raise_exception=True
)  # Restoring is a type of change
def restore_employee(request, id):
    employee = get_object_or_404(EmployeeProfile, id=id, deleted_at__isnull=False)
    old_status = "deleted"
    new_status = "active"
    changes = {"status": {"old": old_status, "new": new_status}}
    employee.restore()
    log_audit_trail(request.user, "restore", employee, changes=changes)
    messages.success(request, "Employee restored successfully!")
    return redirect("payroll:employee_list")


@login_required  # Replaced user_passes_test with permission based logic inside or specific view perm
def iou_list(request):  # This is a general list, should be protected
    # If this is for admins/HR to see all IOUs:
    # if not request.user.has_perm('payroll.view_iou'):
    #     # If it's for users to see their own, redirect to iou_history or filter by own
    #     # For now, let's assume this is an admin/HR view of ALL IOUs
    #     raise HttpResponseForbidden("You are not authorized to view this list.")
    ious = IOU.objects.all()
    return render(request, "iou/iou_list.html", {"ious": ious})


@login_required  # Object-level permission logic inside
def iou_detail(request, pk):
    iou = get_object_or_404(IOU, pk=pk)
    if not (
        request.user == iou.employee_id.user
        or request.user.has_perm("payroll.view_iou")
    ):
        raise HttpResponseForbidden("You are not authorized to view this IOU.")
    return render(request, "iou/iou_detail.html", {"iou": iou})


# New Views for Enhanced Payday and PayVar Creation


@permission_required("payroll.add_payt", raise_exception=True)
def payday_create_new(request):
    """
    Enhanced view for creating PayT (Pay Period) with efficient employee selection.
    Supports search, filtering, and bulk selection of employees.
    """
    from django.http import JsonResponse
    import json

    # Get all active employees with their related data
    employees = (
        EmployeeProfile.objects.filter(status="active")
        .select_related("user", "employee_pay", "department")
        .prefetch_related("allowances", "deductions")
    )

    # Prepare employee data for JSON serialization
    employees_data = []
    for emp in employees:
        employees_data.append(
            {
                "id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "email": emp.email or emp.user.email if emp.user else "",
                "emp_id": emp.emp_id,
                "department": emp.department.name if emp.department else "N/A",
                "department_id": emp.department.id if emp.department else "",
                "job_title": emp.get_job_title_display(),
                "net_pay": float(emp.net_pay) if emp.net_pay else 0,
                "photo": emp.photo.url if emp.photo else "default.png",
                "initials": f"{(emp.first_name or '')[:1]}{(emp.last_name or '')[:1]}".upper(),
                "selected": False,
            }
        )

    # Get unique departments and job titles for filters
    from payroll.models import Department

    departments = Department.objects.all()
    job_titles = EmployeeProfile._meta.get_field("job_title").choices

    if request.method == "POST":
        logger.info(f"Pay period create POST request received")
        logger.debug(f"POST data: {request.POST}")

        form = PaydayCreateForm(request.POST)
        if not form.is_valid():
            logger.error(f"Form validation errors: {form.errors}")
        else:
            logger.info("Form is valid, proceeding to save")
            # Use the custom save method that creates PayT, PayVar, and Payday entries
            payt = form.save()

            # Get the number of employees added
            employee_count = payt.payroll_payday.count()

            logger.info(
                f"Pay period '{payt.name}' created successfully with {employee_count} employees"
            )

            messages.success(
                request,
                f"Pay period '{payt.name}' created successfully with {employee_count} employees.",
            )
            return redirect("payroll:pay_period_detail", slug=payt.slug)
    else:
        form = PaydayCreateForm()

    context = {
        "form": form,
        "employees_json": json.dumps(employees_data),
        "total_employees": len(employees_data),
        "departments": departments,
        "job_titles": job_titles,
    }
    return render(request, "payroll/payday_create_new.html", context)


@permission_required("payroll.add_payt", raise_exception=True)
def payday_create(request):
    """
    Enhanced view for creating PayT (Pay Period) with efficient employee selection.
    Uses the original PaydayForm with proper ManyToMany handling.
    Supports search, filtering, and bulk selection of employees.
    """
    from django.http import JsonResponse
    import json

    # Get all active employees with their related data
    employees = (
        EmployeeProfile.objects.filter(status="active")
        .select_related("user", "employee_pay", "department")
        .prefetch_related("allowances", "deductions")
    )

    # Prepare employee data for JSON serialization
    employees_data = []
    for emp in employees:
        employees_data.append(
            {
                "id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "email": emp.email or emp.user.email if emp.user else "",
                "emp_id": emp.emp_id,
                "department": emp.department.name if emp.department else "N/A",
                "department_id": emp.department.id if emp.department else "",
                "job_title": emp.get_job_title_display(),
                "net_pay": float(emp.net_pay) if emp.net_pay else 0,
                "photo": emp.photo.url if emp.photo else "default.png",
                "initials": f"{(emp.first_name or '')[:1]}{(emp.last_name or '')[:1]}".upper(),
                "selected": False,
            }
        )

    # Get unique departments and job titles for filters
    from payroll.models import Department

    departments = Department.objects.all()
    job_titles = EmployeeProfile._meta.get_field("job_title").choices

    if request.method == "POST":
        form = PaydayForm(request.POST)
        if form.is_valid():
            # Save the PayT instance - the form handles ManyToMany automatically
            payt = form.save()

            # Count how many employees were added
            employee_count = payt.payroll_payday.count()

            messages.success(
                request,
                f"Pay period '{payt.name}' created successfully with {employee_count} employees.",
            )
            return redirect("payroll:pay_period_detail", slug=payt.slug)
    else:
        form = PaydayForm()

    context = {
        "form": form,
        "employees_json": json.dumps(employees_data),
        "total_employees": len(employees_data),
        "departments": departments,
        "job_titles": job_titles,
    }
    return render(request, "payroll/payday_create.html", context)


@permission_required("payroll.add_payvar", raise_exception=True)
def payvar_create_new(request):
    """
    Enhanced view for creating PayVar (Payroll Variables) for multiple employees.
    Supports search, filtering, and bulk selection of employees.
    """
    from django.http import JsonResponse
    import json

    # Get all active employees with their related data
    employees = (
        EmployeeProfile.objects.filter(status="active")
        .select_related("user", "employee_pay", "department")
        .prefetch_related("allowances", "deductions")
    )

    # Prepare employee data for JSON serialization
    employees_data = []
    for emp in employees:
        employees_data.append(
            {
                "id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "email": emp.email or emp.user.email if emp.user else "",
                "emp_id": emp.emp_id,
                "department": emp.department.name if emp.department else "N/A",
                "department_id": emp.department.id if emp.department else "",
                "job_title": emp.get_job_title_display(),
                "net_pay": float(emp.net_pay) if emp.net_pay else 0,
                "photo": emp.photo.url if emp.photo else "default.png",
                "initials": f"{(emp.first_name or '')[:1]}{(emp.last_name or '')[:1]}".upper(),
                "selected": False,
            }
        )

    # Get unique departments and job titles for filters
    from payroll.models import Department

    departments = Department.objects.all()
    job_titles = EmployeeProfile._meta.get_field("job_title").choices

    if request.method == "POST":
        form = PayVarCreateForm(request.POST)
        if form.is_valid():
            # Use the custom save method that creates PayVar entries
            payvars = form.save()

            # Count how many PayVar entries were created
            payvar_count = len(payvars)

            messages.success(
                request,
                f"Payroll variables created successfully for {payvar_count} employees.",
            )
            return redirect("payroll:varview")
    else:
        form = PayVarCreateForm()

    context = {
        "form": form,
        "employees_json": json.dumps(employees_data),
        "total_employees": len(employees_data),
        "departments": departments,
        "job_titles": job_titles,
    }
    return render(request, "payroll/payvar_create_new.html", context)
