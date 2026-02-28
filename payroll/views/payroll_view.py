from datetime import date
from decimal import Decimal
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Case, When, IntegerField
from django.db import transaction
from django.views.generic import CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseForbidden
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)
from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.template.loader import render_to_string
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
    PayrollRunForm,
    PayrollForm,
    DeductionForm,
    PayrollRunCreateForm,
    PayrollEntryCreateForm,
    CompanyPayrollSettingForm,
    CompanyHealthInsuranceTierFormSet,
)
from payroll.models import (
    EmployeeProfile,
    LeavePolicy,
    LeaveRequest,
    PayrollRun,
    PayrollRunEntry,
    Payroll,
    Allowance,
    IOU,
    AuditTrail,
    Deduction,
    PayrollEntry,
    CompanyPayrollSetting,
)
from django.utils import timezone
from accounting.models import Account
from accounting.models import Journal
from accounting.utils import create_journal_entry
from accounting.permissions import (
    is_auditor,
    can_view_payroll_data,
    can_modify_payroll_data,
)
from payroll import utils
from company.utils import get_user_company

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)

logger = logging.getLogger(__name__)


def _get_payroll_close_journal_transaction_number(payroll_run):
    if not payroll_run or not getattr(payroll_run, "pk", None):
        return None
    payroll_ct = ContentType.objects.get_for_model(PayrollRun)
    journal = (
        Journal.objects.filter(
            content_type=payroll_ct,
            object_id=payroll_run.pk,
            description__startswith="Payroll for period:",
        )
        .order_by("-created_at")
        .first()
    )
    return journal.transaction_number if journal else None


def generate_payslip_pdf(payslip_data, template_path="pay/payslip_pdf.html"):
    """Generates a PDF payslip from an HTML template."""
    template = render_to_string(template_path, payslip_data)
    result = io.BytesIO()
    pdf = pisa.pisaDocument(io.BytesIO(template.encode("UTF-8")), result)
    if not pdf.err:
        return result.getvalue()
    return None


def _send_payslips_for_payroll_run(payroll_run):
    """
    Send payslip emails with PDF attachments to employees included in a payroll run.
    Returns (sent_count, skipped_details).
    """
    sent_count = 0
    skipped_details = []

    run_entries = payroll_run.payroll_run_entries.select_related(
        "payroll_entry__pays__user",
        "payroll_entry__pays",
    )

    for run_entry in run_entries:
        payroll_entry = run_entry.payroll_entry
        employee = payroll_entry.pays
        employee_label = (
            f"{(employee.first_name or '').strip()} {(employee.last_name or '').strip()}".strip()
            if employee
            else "Unknown employee"
        )
        if employee and not employee_label:
            employee_label = employee.emp_id or f"Employee #{employee.id}"

        if not employee:
            skipped_details.append("Unknown employee (missing payroll linkage)")
            continue

        recipient_email = (
            employee.user.email
            if employee.user and employee.user.email
            else employee.email
        )
        if not recipient_email:
            skipped_details.append(f"{employee_label} (missing email)")
            continue

        payslip_data = {
            "payroll": payroll_entry,
            "employee": employee,
        }
        pdf_content = generate_payslip_pdf(payslip_data)
        if not pdf_content:
            logger.error(
                "Failed to generate payslip PDF for employee_id=%s in payroll_run=%s",
                employee.id,
                payroll_run.id,
            )
            skipped_details.append(f"{employee_label} (PDF generation failed)")
            continue

        period_label = (
            payroll_run.paydays.strftime("%B %Y")
            if payroll_run.paydays and hasattr(payroll_run.paydays, "strftime")
            else str(payroll_run.paydays or "")
        )
        employee_identifier = employee.emp_id or str(employee.id)
        filename = f"payslip_{employee_identifier}_{period_label.replace(' ', '_')}.pdf"

        try:
            custom_send_mail(
                subject=f"Payslip for {period_label}",
                template_name="email/payslip_email.html",
                context={
                    "user": employee.user or employee,
                    "employee": employee,
                    "employee_name": (
                        f"{employee.first_name or ''} {employee.last_name or ''}".strip()
                        or recipient_email
                    ),
                    "payroll": payroll_entry,
                    "month_year": period_label,
                    "net_pay_amount": payroll_entry.netpay,
                },
                from_email=DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                attachments=[
                    {
                        "filename": filename,
                        "content": pdf_content,
                        "mimetype": "application/pdf",
                    }
                ],
                fail_silently=False,
            )
            sent_count += 1
        except Exception as exc:
            logger.error(
                "Failed to send payslip email for employee_id=%s in payroll_run=%s: %s",
                employee.id,
                payroll_run.id,
                exc,
            )
            skipped_details.append(f"{employee_label} (email send failed)")

    return sent_count, skipped_details


@permission_required("payroll.add_payroll", raise_exception=True)
def add_pay(request):
    form = PayrollForm(request.POST or None, user=request.user)
    company = get_user_company(request.user)
    if form.is_valid():
        employee = form.cleaned_data["employee"]
        basic_salary = form.cleaned_data["basic_salary"]

        payroll_instance = Payroll.objects.create(
            basic_salary=basic_salary,
            company=company,
        )
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
                    "employee": employee,
                    "employee_name": (
                        f"{employee.first_name or ''} {employee.last_name or ''}".strip()
                        or employee.user.email
                    ),
                    "payroll": payroll_instance,
                    "month_year": payroll_instance.month_year,
                    "net_pay_amount": payroll_instance.net_pay,
                }

                # Prepare attachments for custom_send_mail
                attachments = [
                    {
                        "filename": f"payslip_{employee.emp_id or employee.id}_{payroll_instance.month_year}.pdf",
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
    company = get_user_company(request.user)
    pay = get_object_or_404(Payroll, id=id, company=company)
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

    company = get_user_company(request.user)
    emp = EmployeeProfile.objects.filter(company=company) if company else []
    context = {
        "emp": emp,
        "empty_list": [],  # For empty for loop handling in templates
        "is_auditor": is_auditor(request.user),  # Add auditor flag for template
    }
    return render(request, "pay/dashboard_new.html", context)


@permission_required("payroll.view_companypayrollsetting", raise_exception=True)
def company_payroll_settings(request):
    company = get_user_company(request.user)
    if not company:
        messages.error(request, "No active company found for your account.")
        return redirect("payroll:dashboard")

    settings_obj, created = CompanyPayrollSetting.objects.get_or_create(company=company)
    if created:
        settings_obj.create_default_health_tiers()
    tiers = settings_obj.health_insurance_tiers.all()

    context = {
        "company": company,
        "settings_obj": settings_obj,
        "tiers": tiers,
    }
    return render(request, "payroll/company_payroll_settings.html", context)


@permission_required("payroll.change_companypayrollsetting", raise_exception=True)
def company_payroll_settings_edit(request):
    company = get_user_company(request.user)
    if not company:
        messages.error(request, "No active company found for your account.")
        return redirect("payroll:dashboard")

    settings_obj, created = CompanyPayrollSetting.objects.get_or_create(company=company)
    if created:
        settings_obj.create_default_health_tiers()

    if request.method == "POST":
        form = CompanyPayrollSettingForm(request.POST, instance=settings_obj)
        formset = CompanyHealthInsuranceTierFormSet(
            request.POST, instance=settings_obj, prefix="tiers"
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, "Payroll settings updated successfully.")
            return redirect("payroll:company_payroll_settings")
    else:
        form = CompanyPayrollSettingForm(instance=settings_obj)
        formset = CompanyHealthInsuranceTierFormSet(
            instance=settings_obj, prefix="tiers"
        )

    context = {
        "company": company,
        "form": form,
        "formset": formset,
    }
    return render(request, "payroll/company_payroll_settings_form.html", context)


@login_required
def list_payslip(request, emp_slug):
    company = get_user_company(request.user)
    emp = get_object_or_404(EmployeeProfile, slug=emp_slug, company=company)

    # Check if user can view payroll data (auditors have view-only access)
    if not (
        request.user == emp.user
        or request.user.has_perm("payroll.view_payroll")
        or is_auditor(request.user)
    ):
        raise HttpResponseForbidden("You are not authorized to view this payslip.")

    pay = PayrollRunEntry.objects.filter(
        payroll_entry__pays__slug=emp_slug,
        payroll_entry__company=company,
    ).all()
    paydays = PayrollRunEntry.objects.filter(
        payroll_entry__pays__slug=emp_slug,
        payroll_entry__company=company,
    ).values_list("payroll_run__paydays", flat=True)
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
    # # Check if user can view payroll data (auditors have view-only access)
    # if not can_view_payroll_data(request.user):
    #     return HttpResponseForbidden("You don't have permission to view payroll data.")

    try:
        employee_profile = request.user.employee_user
        pay = PayrollRunEntry.objects.filter(
            payroll_entry__pays__user=request.user,
            payroll_entry__company=employee_profile.company,
        ).all()
        paydays = PayrollRunEntry.objects.filter(
            payroll_entry__pays__user=request.user,
            payroll_entry__company=employee_profile.company,
        ).values_list("payroll_run__paydays", flat=True)
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
        return redirect("payroll:hr_dashboard")


@login_required
def payslip_detail(request, id):
    company = get_user_company(request.user)
    pay_id = get_object_or_404(
        PayrollRunEntry,
        id=id,
        payroll_entry__company=company,
    )
    target_employee_user = pay_id.payroll_entry.pays.user

    # Enforce object-level access to prevent horizontal privilege escalation.
    if not (
        request.user == target_employee_user
        or request.user.has_perm("payroll.view_payroll")
        or is_auditor(request.user)
    ):
        return HttpResponseForbidden("You are not authorized to view this payslip.")

    num2word = utils.format_currency_words_with_kobo(pay_id.payroll_entry.netpay)
    dates = utils.convert_month_to_word(str(pay_id.payroll_run.paydays))
    pay_ids = pay_id.payroll_entry.pays.pk
    payroll_record = pay_id.payroll_entry.pays.employee_pay

    pay_id_nhif = payroll_record.nhif if payroll_record else Decimal("0.00")
    pay_id_basic = payroll_record.basic if payroll_record else Decimal("0.00")
    pay_id_nhf = payroll_record.nhf if payroll_record else Decimal("0.00")
    pay_id_nsitf = (
        (payroll_record.nsitf or Decimal("0.00")) / 12
        if payroll_record
        else Decimal("0.00")
    )
    pay_id_payee = payroll_record.payee if payroll_record else Decimal("0.00")
    pay_id_pension = (
        (payroll_record.pension or Decimal("0.00")) / 12
        if payroll_record
        else Decimal("0.00")
    )
    pay_id_gross = (
        (payroll_record.gross_income or Decimal("0.00")) / 12
        if payroll_record
        else Decimal("0.00")
    )
    pay_id_net = pay_id.payroll_entry.netpay / 12
    pay_id_housing = (
        (payroll_record.housing or Decimal("0.00")) / 12
        if payroll_record
        else Decimal("0.00")
    )
    pay_id_transport = (
        (payroll_record.transport or Decimal("0.00")) / 12
        if payroll_record
        else Decimal("0.00")
    )
    pay_id_taxable = (
        (payroll_record.taxable_income or Decimal("0.00")) / 12
        if payroll_record
        else Decimal("0.00")
    )
    pay_id_water = payroll_record.water_rate if payroll_record else Decimal("0.00")
    iou_deductions = (
        pay_id.payroll_entry.pays.iou_deductions.filter(payday=pay_id.payroll_run)
        .select_related("iou")
        .order_by("iou_id")
    )
    iou_deduction_total = sum((item.amount for item in iou_deductions), Decimal("0.00"))
    # pay_id_
    context = {
        "pay": pay_id,
        "pays": pay_ids,
        "num2words": num2word,
        "dates": dates,
        "basic": pay_id_basic,
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
        "iou_deductions": iou_deductions,
        "iou_deduction_total": iou_deduction_total,
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

    company = get_user_company(request.user)
    var = get_object_or_404(Allowance, id=id, employee__company=company)
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

    company = get_user_company(request.user)
    allowance_obj = get_object_or_404(
        Allowance, id=id, employee__company=company
    )  # Renamed variable
    allowance_obj.delete()
    messages.success(request, "Allowance deleted Successfully!!")
    return redirect("payroll:dashboard")  # Or a list view for allowances


# @permission_required("payroll.add_deduction", raise_exception=True)
class AddDeduction(PermissionRequiredMixin, CreateView):
    model = Deduction
    form_class = DeductionForm
    template_name = "pay/add_deduction.html"  # New template for deductions
    success_url = reverse_lazy(
        "payroll:hr_dashboard"
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
        deduction = form.instance
        print(
            "[DEDUCTION_DEBUG] Deduction form submit: "
            f"employee_id={deduction.employee_id}, type={deduction.deduction_type}, "
            f"amount={deduction.amount}, reason={deduction.reason or ''}."
        )
        messages.success(self.request, "Deduction created successfully!!")
        return super().form_valid(form)


class AddPay(
    PermissionRequiredMixin, CreateView
):  # Removed LoginRequiredMixin, UserPassesTestMixin
    model = PayrollRun
    form_class = PayrollRunForm
    template_name = "pay/add_payday.html"
    success_url = reverse_lazy("payroll:pay_period_list")
    permission_required = "payroll.add_payrollrun"

    # Removed get and post methods if standard CreateView behavior is sufficient with form_class
    # If custom logic within get/post is needed beyond form_valid, it can be kept.
    # For now, assuming standard CreateView. If issues arise, these can be re-evaluated.
    def form_valid(self, form):
        # Delegate persistence to form.save() so closure-posting sequencing and
        # M2M handling remain consistent.
        self.object = form.save()

        messages.success(
            self.request, "PayrollRunEntry (PayrollRun) created successfully!!"
        )
        if self.object.closed:
            txn = _get_payroll_close_journal_transaction_number(self.object)
            if txn:
                messages.success(
                    self.request,
                    f"Payroll period closed and posted to ledger (Journal: {txn}).",
                )
            else:
                messages.warning(
                    self.request,
                    "Payroll period marked closed, but no journal was found. Check Unposted Events report.",
                )
        return redirect(self.success_url)


@permission_required("payroll.view_payrollrun", raise_exception=True)
def varview(request):  # Lists PayrollRun objects (Pay Periods)
    company = get_user_company(request.user)
    var = (
        PayrollRun.objects.filter(company=company)
        .order_by("paydays")
        .distinct("paydays")
    )
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in var
    ]  # Access .paydays attribute
    context = {"pay_var": var, "dates": dates}
    return render(request, "pay/var_view.html", context)


# New Views for PayrollRun (Pay Periods)


@permission_required("payroll.view_payrollrun", raise_exception=True)
def pay_period_list(request):
    company = get_user_company(request.user)
    pay_periods = PayrollRun.objects.filter(company=company).order_by("-paydays")
    paginator = Paginator(pay_periods, 15)  # Show 15 pay periods per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "pay/pay_period_list.html", {"page_obj": page_obj})


@permission_required("payroll.view_payrollrun", raise_exception=True)
def pay_period_detail(request, slug):
    company = get_user_company(request.user)
    pay_period = get_object_or_404(PayrollRun, slug=slug, company=company)
    # Fetch related PayrollRunEntry entries if needed for detail view
    payday_entries = PayrollRunEntry.objects.filter(
        payroll_run=pay_period,
        payroll_entry__company=company,
    )
    context = {
        "pay_period": pay_period,
        "payday_entries": payday_entries,
    }
    return render(request, "pay/pay_period_detail.html", context)


class PayPeriodUpdateView(
    LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView
):
    model = PayrollRun
    form_class = PayrollRunForm
    template_name = "pay/pay_period_form.html"  # Generic form template
    success_url = reverse_lazy("payroll:pay_period_list")
    permission_required = "payroll.change_payrollrun"
    success_message = "Pay Period updated successfully."

    def get_queryset(self):
        return PayrollRun.objects.filter(company=get_user_company(self.request.user))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        was_closed = self.get_object().closed
        response = super().form_valid(form)
        now_closed = self.object.closed
        if not was_closed and now_closed:
            txn = _get_payroll_close_journal_transaction_number(self.object)
            if txn:
                messages.success(
                    self.request,
                    f"Payroll period closed and posted to ledger (Journal: {txn}).",
                )
            else:
                messages.warning(
                    self.request,
                    "Payroll period marked closed, but no journal was found. Check Unposted Events report.",
                )
        return response


class PayPeriodDeleteView(
    LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, DeleteView
):
    model = PayrollRun
    template_name = "pay/pay_period_confirm_delete.html"
    success_url = reverse_lazy("payroll:pay_period_list")
    permission_required = "payroll.delete_payrollrun"
    success_message = "Pay Period deleted successfully."

    def get_queryset(self):
        return PayrollRun.objects.filter(company=get_user_company(self.request.user))


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
        return redirect("payroll:hr_dashboard")
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
    company = get_user_company(user)

    try:
        employee_profile = user.employee_user

        # HR / Staff with permission can see all requests
        if user.has_perm("payroll.view_leaverequest"):
            leave_requests_qs = LeaveRequest.objects.select_related(
                "employee", "approved_by"
            ).filter(employee__company=company).order_by("-created_at")
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
    company = get_user_company(request.user)
    requests = LeaveRequest.objects.filter(
        employee__company=company, status="PENDING"
    )  # Shows only PENDING for action
    return render(
        request, "employee/manage_leave_requests.html", {"requests": requests}
    )


@permission_required("payroll.change_leaverequest", raise_exception=True)
def approve_leave(request, pk):
    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
    leave_request.status = "APPROVED"
    # Pass the current user to the save method for audit logging
    leave_request.save(user=request.user)
    messages.success(request, "Leave request approved.")
    return redirect("payroll:manage_leave_requests")


@permission_required("payroll.change_leaverequest", raise_exception=True)
def reject_leave(request, pk):
    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
    leave_request.status = "REJECTED"
    # Pass current user to the save method for audit logging
    leave_request.save(user=request.user)
    messages.success(request, "Leave request rejected.")
    return redirect("payroll:manage_leave_requests")


@permission_required("payroll.view_leavepolicy", raise_exception=True)
def leave_policies(request):
    company = get_user_company(request.user)
    policies = LeavePolicy.objects.filter(company=company)
    return render(request, "employee/leave_policies.html", {"policies": policies})


@login_required  # Combined with object-level check
def edit_leave_request(request, pk):
    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
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
    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
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
    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
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


@login_required
@permission_required("payroll.add_iou", raise_exception=True)
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
        return redirect("payroll:hr_dashboard")  # Or any other appropriate URL

    monthly_salary = employee_profile.net_pay or Decimal("0.00")
    if monthly_salary <= 0 and employee_profile.employee_pay:
        monthly_salary = employee_profile.employee_pay.basic_salary or Decimal("0.00")
    outstanding_balance = (
        IOU.objects.filter(employee_id=employee_profile)
        .exclude(status__in=["REJECTED", "PAID"])
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )
    max_iou_amount = max(monthly_salary - outstanding_balance, Decimal("0.00"))
    enforce_max_iou_amount = max_iou_amount if max_iou_amount > 0 else None

    if request.method == "POST":
        form = IOURequestForm(request.POST, max_iou_amount=enforce_max_iou_amount)
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
        form = IOURequestForm(max_iou_amount=enforce_max_iou_amount)
        # Or, if you exclude 'employee_id' from the form:
        # form = IOURequestForm()
    context = {
        "form": form,
        "employee_profile": employee_profile,  # Pass the profile for context
        "monthly_salary": monthly_salary,
        "outstanding_balance": outstanding_balance,
        "max_iou_amount": max_iou_amount,
    }

    return render(request, "iou/request_iou_new.html", context)


@permission_required(
    "payroll.change_iou", raise_exception=True
)  # For approving/rejecting IOUs
def approve_iou(request, iou_id):
    company = get_user_company(request.user)
    iou = get_object_or_404(IOU, id=iou_id, employee_id__company=company)
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


class IOUUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    UpdateView,
):
    model = IOU
    form_class = IOUUpdateForm
    template_name = "iou/iou_update_form.html"  # Path to your update template
    context_object_name = "iou"  # To match {{ iou }} in your template
    success_url = reverse_lazy(
        "payroll:iou_list"
    )  # Redirect to IOU list view (assuming you have one)
    success_message = "IOU request updated successfully."
    permission_required = "payroll.change_iou"

    def get_queryset(self):
        company = get_user_company(self.request.user)
        return IOU.objects.filter(employee_id__company=company)

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


class IOUDeleteView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    DeleteView,
):
    model = IOU
    template_name = (
        "iou/iou_confirm_delete.html"  # Path to your delete confirmation template
    )
    context_object_name = "iou"
    success_url = reverse_lazy("payroll:iou_list")  # Redirect to IOU list view
    success_message = "IOU request deleted successfully."
    permission_required = "payroll.delete_iou"

    def get_queryset(self):
        company = get_user_company(self.request.user)
        return IOU.objects.filter(employee_id__company=company)


@login_required  # Shows user's own IOUs or all if staff/has permission
def iou_history(request):
    # Check if user can view payroll data (auditors have view-only access)
    if not can_view_payroll_data(request.user):
        return HttpResponseForbidden("You don't have permission to view payroll data.")

    try:
        employee_profile = request.user.employee_user
        company = get_user_company(request.user)
        if request.user.has_perm("payroll.view_iou"):  # Staff/HR with general view perm
            ious = IOU.objects.filter(employee_id__company=company).order_by(
                "-created_at"
            )
        else:
            ious = IOU.objects.filter(
                employee_id=employee_profile,
                employee_id__company=company,
            ).order_by("-created_at")
    except EmployeeProfile.DoesNotExist:
        ious = IOU.objects.none()
        messages.info(
            request, "Your user account is not linked to an employee profile."
        )

    pending_count = ious.filter(status="PENDING").count()
    approved_amount = (
        ious.filter(status="APPROVED").aggregate(total=Sum("amount")).get("total") or 0
    )
    outstanding_balance = (
        ious.exclude(status__in=["REJECTED", "PAID"])
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )

    context = {
        "ious": ious,
        "pending_count": pending_count,
        "approved_amount": approved_amount,
        "outstanding_balance": outstanding_balance,
        "is_auditor": is_auditor(request.user),  # Add auditor flag for template
    }
    return render(request, "iou/iou_history_new.html", context)


@login_required
def my_iou_tracker(request):
    try:
        employee_profile = request.user.employee_user
    except EmployeeProfile.DoesNotExist:
        messages.info(
            request, "Your user account is not linked to an employee profile."
        )
        return render(
            request,
            "iou/my_iou_tracker.html",
            {
                "ious": IOU.objects.none(),
                "pending_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "paid_count": 0,
                "outstanding_balance": Decimal("0.00"),
            },
        )

    ious = IOU.objects.filter(employee_id=employee_profile).order_by("-created_at")
    pending_count = ious.filter(status="PENDING").count()
    approved_count = ious.filter(status="APPROVED").count()
    rejected_count = ious.filter(status="REJECTED").count()
    paid_count = ious.filter(status="PAID").count()
    outstanding_balance = ious.exclude(status__in=["REJECTED", "PAID"]).aggregate(
        total=Sum("amount")
    ).get("total") or Decimal("0.00")

    context = {
        "ious": ious,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "paid_count": paid_count,
        "outstanding_balance": outstanding_balance,
    }
    return render(request, "iou/my_iou_tracker.html", context)


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
            Q(user__email__icontains=query)
            | Q(action__icontains=query)
            | Q(content_type__model__icontains=query)
            | Q(content_object__icontains=query)
        )
    if user_filter:
        logs = logs.filter(user__email__icontains=user_filter)
    if action_filter:
        logs = logs.filter(action__icontains=action_filter)
    action_choices = (
        AuditTrail.objects.exclude(action__isnull=True)
        .exclude(action__exact="")
        .values_list("action", flat=True)
        .distinct()
        .order_by("action")
    )
    total_logs = logs.count()
    changed_logs_count = logs.exclude(changes={}).exclude(changes__isnull=True).count()
    users_count = logs.values("user").distinct().count()

    params = request.GET.copy()
    if "page" in params:
        params.pop("page")
    filters_querystring = params.urlencode()

    paginator = Paginator(logs, 10)
    page_number = request.GET.get("page")
    audit_logs = paginator.get_page(page_number)
    context = {
        "audit_logs": audit_logs,
        "query": query,
        "user_filter": user_filter,
        "action_filter": action_filter,
        "action_choices": action_choices,
        "total_logs": total_logs,
        "changed_logs_count": changed_logs_count,
        "users_count": users_count,
        "filters_querystring": filters_querystring,
    }
    return render(request, "pay/audit_trail_list.html", context)


@permission_required("payroll.view_audittrail", raise_exception=True)
def audit_trail_detail(request, id=None, pk=None):
    log_id = pk if pk is not None else id
    log = get_object_or_404(AuditTrail, pk=log_id)
    return render(request, "pay/audit_trail_detail.html", {"log": log})


@permission_required(
    "payroll.change_employeeprofile", raise_exception=True
)  # Restoring is a type of change
def restore_employee(request, id):
    company = get_user_company(request.user)
    employee = get_object_or_404(
        EmployeeProfile,
        id=id,
        company=company,
        deleted_at__isnull=False,
    )
    old_status = "deleted"
    new_status = "active"
    changes = {"status": {"old": old_status, "new": new_status}}
    employee.restore()
    log_audit_trail(request.user, "restore", employee, changes=changes)
    messages.success(request, "Employee restored successfully!")
    return redirect("payroll:employee_list")


@permission_required("payroll.change_iou", raise_exception=True)
def iou_list(request):  # This is a general list, should be protected
    # If this is for admins/HR to see all IOUs:
    # if not request.user.has_perm('payroll.view_iou'):
    #     # If it's for users to see their own, redirect to iou_history or filter by own
    #     # For now, let's assume this is an admin/HR view of ALL IOUs
    #     raise HttpResponseForbidden("You are not authorized to view this list.")
    company = get_user_company(request.user)
    ious = (
        IOU.objects.filter(employee_id__company=company)
        .annotate(
            status_priority=Case(
                When(status="PENDING", then=0),
                When(status="APPROVED", then=1),
                When(status="PAID", then=2),
                When(status="REJECTED", then=3),
                default=9,
                output_field=IntegerField(),
            )
        )
        .order_by("status_priority", "-created_at")
    )
    return render(request, "iou/iou_list.html", {"ious": ious})


@login_required  # Object-level permission logic inside
def iou_detail(request, pk):
    company = get_user_company(request.user)
    iou = get_object_or_404(IOU, pk=pk, employee_id__company=company)
    if not (
        request.user == iou.employee_id.user
        or request.user.has_perm("payroll.view_iou")
    ):
        raise HttpResponseForbidden("You are not authorized to view this IOU.")
    return render(request, "iou/iou_detail.html", {"iou": iou})


@login_required
def iou_payment_slip(request, pk):
    company = get_user_company(request.user)
    iou = get_object_or_404(IOU, pk=pk, employee_id__company=company)
    if not (
        request.user == iou.employee_id.user
        or request.user.has_perm("payroll.view_iou")
        or request.user.has_perm("payroll.change_iou")
    ):
        raise HttpResponseForbidden(
            "You are not authorized to view this IOU payment slip."
        )

    deductions = iou.deductions.select_related("payday").order_by("payday__paydays")
    repaid_amount = iou.repaid_amount
    outstanding_amount = iou.outstanding_amount
    monthly_expected = Decimal("0.00")
    if iou.employee_id:
        monthly_netpay = Decimal(iou.employee_id.net_pay or Decimal("0.00"))
        if monthly_netpay > 0:
            monthly_expected = (
                monthly_netpay * Decimal(iou.repayment_deduction_percentage or 0)
            ) / Decimal("100")

    context = {
        "iou": iou,
        "deductions": deductions,
        "repaid_amount": repaid_amount,
        "outstanding_amount": outstanding_amount,
        "monthly_expected": monthly_expected,
    }
    return render(request, "iou/iou_payment_slip.html", context)


# New Views for Enhanced PayrollRunEntry and PayrollEntry Creation


@permission_required("payroll.add_payrollrun", raise_exception=True)
def payday_create_new(request):
    """
    Enhanced view for creating PayrollRun (Pay Period) with efficient employee selection.
    Supports search, filtering, and bulk selection of employees.
    """
    from django.http import JsonResponse
    import json

    # Get all active employees with their related data
    company = get_user_company(request.user)
    employees = (
        EmployeeProfile.objects.filter(status="active", company=company)
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

    departments = Department.objects.filter(company=company)
    job_titles = EmployeeProfile._meta.get_field("job_title").choices

    if request.method == "POST":
        logger.info(f"Pay period create POST request received")
        logger.debug(f"POST data: {request.POST}")

        form = PayrollRunCreateForm(request.POST, user=request.user)
        if not form.is_valid():
            logger.error(f"Form validation errors: {form.errors}")
        else:
            logger.info("Form is valid, proceeding to save")
            # Use the custom save method that creates PayrollRun, PayrollEntry, and PayrollRunEntry entries
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
            sent_count, skipped_email_details = _send_payslips_for_payroll_run(payt)
            if sent_count:
                messages.success(
                    request,
                    f"Payslips emailed successfully to {sent_count} employee(s).",
                )
            if skipped_email_details:
                messages.warning(
                    request,
                    f"{len(skipped_email_details)} employee(s) were skipped for payslip email: "
                    + ", ".join(skipped_email_details),
                )
            skipped = getattr(payt, "_skipped_employee_reasons", [])
            if skipped:
                messages.warning(
                    request,
                    "Skipped non-eligible employees: " + ", ".join(skipped),
                )
            if payt.closed:
                txn = _get_payroll_close_journal_transaction_number(payt)
                if txn:
                    messages.success(
                        request,
                        f"Payroll period closed and posted to ledger (Journal: {txn}).",
                    )
                else:
                    messages.warning(
                        request,
                        "Payroll period marked closed, but no journal was found. Check Unposted Events report.",
                    )
            return redirect("payroll:pay_period_detail", slug=payt.slug)
    else:
        form = PayrollRunCreateForm(user=request.user)

    context = {
        "form": form,
        "employees_json": json.dumps(employees_data),
        "total_employees": len(employees_data),
        "departments": departments,
        "job_titles": job_titles,
    }
    return render(request, "payroll/payday_create_new.html", context)


@permission_required("payroll.add_payrollrun", raise_exception=True)
def payday_create(request):
    """
    Enhanced view for creating PayrollRun (Pay Period) with efficient employee selection.
    Uses the original PayrollRunForm with proper ManyToMany handling.
    Supports search, filtering, and bulk selection of employees.
    """
    from django.http import JsonResponse
    import json

    # Get all active employees with their related data
    company = get_user_company(request.user)
    employees = (
        EmployeeProfile.objects.filter(status="active", company=company)
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

    departments = Department.objects.filter(company=company)
    job_titles = EmployeeProfile._meta.get_field("job_title").choices

    if request.method == "POST":
        form = PayrollRunForm(request.POST, user=request.user)
        if form.is_valid():
            # Save the PayrollRun instance - the form handles ManyToMany automatically
            payt = form.save()

            # Count how many employees were added
            employee_count = payt.payroll_payday.count()

            messages.success(
                request,
                f"Pay period '{payt.name}' created successfully with {employee_count} employees.",
            )
            sent_count, skipped_email_details = _send_payslips_for_payroll_run(payt)
            if sent_count:
                messages.success(
                    request,
                    f"Payslips emailed successfully to {sent_count} employee(s).",
                )
            if skipped_email_details:
                messages.warning(
                    request,
                    f"{len(skipped_email_details)} employee(s) were skipped for payslip email: "
                    + ", ".join(skipped_email_details),
                )
            if payt.closed:
                txn = _get_payroll_close_journal_transaction_number(payt)
                if txn:
                    messages.success(
                        request,
                        f"Payroll period closed and posted to ledger (Journal: {txn}).",
                    )
                else:
                    messages.warning(
                        request,
                        "Payroll period marked closed, but no journal was found. Check Unposted Events report.",
                    )
            return redirect("payroll:pay_period_detail", slug=payt.slug)
    else:
        form = PayrollRunForm(user=request.user)

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
    Enhanced view for creating PayrollEntry (Payroll Variables) for multiple employees.
    Supports search, filtering, and bulk selection of employees.
    """
    from django.http import JsonResponse
    import json

    # Get all active employees with their related data
    company = get_user_company(request.user)
    employees = (
        EmployeeProfile.objects.filter(status="active", company=company)
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

    departments = Department.objects.filter(company=company)
    job_titles = EmployeeProfile._meta.get_field("job_title").choices

    if request.method == "POST":
        form = PayrollEntryCreateForm(request.POST, user=request.user)
        if form.is_valid():
            # Use the custom save method that creates PayrollEntry entries
            payvars = form.save()

            # Count how many PayrollEntry entries were created
            payvar_count = len(payvars)

            messages.success(
                request,
                f"Payroll variables created successfully for {payvar_count} employees.",
            )
            return redirect("payroll:varview")
    else:
        form = PayrollEntryCreateForm(user=request.user)

    context = {
        "form": form,
        "employees_json": json.dumps(employees_data),
        "total_employees": len(employees_data),
        "departments": departments,
        "job_titles": job_titles,
    }
    return render(request, "payroll/payvar_create_new.html", context)
