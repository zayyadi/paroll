"""Payroll views module."""

from decimal import Decimal
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Case, When, IntegerField
from django.db import transaction
from django.views.generic import CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from django.utils import timezone

from company.utils import get_user_company
from accounting.permissions import is_auditor
from payroll import utils
from payroll import models
from payroll.models import EmployeeProfile, PayrollRun, PayrollRunEntry, Payroll, IOU, AuditTrail

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)
logger = logging.getLogger(__name__)
from payroll.models import PayslipEmailJob, PayrollEntry
from payroll.forms import PayrollRunForm, PayrollRunCreateForm, PayrollEntryCreateForm
from payroll.services.payslips import resolve_payslip_run_entry
from users.email_backend import send_mail as custom_send_mail
from core.settings import DEFAULT_FROM_EMAIL
import io
try:
    from xhtml2pdf import pisa
except ImportError:
    pisa = None

def generate_payslip_pdf(payslip_data, template_path="pay/payslip_pdf.html"):
    """Generates a PDF payslip from an HTML template."""
    if pisa is None:
        raise RuntimeError("xhtml2pdf is required to generate payslip PDFs.")
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



def _queue_payslip_emails_for_payroll_run(payroll_run):
    """
    Queue payslip email delivery after the payroll run transaction commits.

    The request that creates the pay period should only persist payroll data.
    PDF rendering and SMTP delivery happen in Celery so slow email providers do
    not block payroll creation.
    """
    if not payroll_run or not getattr(payroll_run, "pk", None):
        return False

    job = PayslipEmailJob.objects.create(payroll_run=payroll_run)
    transaction.on_commit(lambda: job.enqueue())
    return job


@permission_required("payroll.add_payroll", raise_exception=True)

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
    pay_id = resolve_payslip_run_entry(id)
    if pay_id is None:
        raise Http404("No PayrollRunEntry matches the given query.")
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
        "pays": pay_id.id,
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

