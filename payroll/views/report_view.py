from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)  # Added permission_required
from django.db.models import Sum
from django.template.loader import render_to_string
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_POST

# user_passes_test is removed as it's no longer used

from payroll.models import (
    PayrollRun,
    PayrollEntry,
    PayrollRunEntry,
    EmployeeProfile,
    CompanyPayrollSetting,
    RemittanceRecord,
    log_sensitive_employee_data_access,
)
from payroll import utils
from company.utils import get_user_company
from accounting.permissions import is_auditor
from payroll.services.payroll_figures import sum_figures
from payroll.services.payslips import (
    can_view_payslip,
    resolve_payslip_run_entry,
)
from payroll.services.employee_data_export import _simple_pdf
from payroll.services.compliance import compliance_summary
from payroll.views.payroll_helpers import payroll_runs_distinct_by_period
try:
    from weasyprint import HTML
except ImportError:  # pragma: no cover - optional PDF dependency.
    HTML = None
try:
    import xlwt
except ImportError:  # pragma: no cover - optional spreadsheet dependency.
    xlwt = None
from decimal import Decimal

# check_super and is_hr_user functions are removed


def _log_payroll_report_sensitive_access(
    *,
    request,
    payroll_entries,
    fields,
    purpose,
    report_name,
):
    employee_ids = list(
        payroll_entries.values_list("payroll_entry__pays_id", flat=True).distinct()
    )
    employees = EmployeeProfile.objects.filter(id__in=employee_ids)
    for employee in employees:
        log_sensitive_employee_data_access(
            employee=employee,
            accessed_by=request.user,
            fields=fields,
            purpose=purpose,
            metadata={"report": report_name},
        )


@login_required
def payslip(request, id):
    pay_id = resolve_payslip_run_entry(id)
    if pay_id is None:
        raise Http404("No PayrollRunEntry matches the given query.")
    if not can_view_payslip(request.user, pay_id):
        return HttpResponseForbidden("You are not authorized to view this payslip.")

    num2word = utils.format_currency_words_with_kobo(pay_id.payroll_entry.netpay)
    dates = utils.convert_month_to_word(str(pay_id.payroll_run.paydays))
    context = {
        "pay": pay_id,
        "num2words": num2word,
        "dates": dates,
    }
    log_sensitive_employee_data_access(
        employee=pay_id.payroll_entry.pays,
        accessed_by=request.user,
        fields=("tin_no", "bank_account_number"),
        purpose="payslip_view",
        metadata={"view": "payslip", "payroll_run_entry_id": pay_id.id},
    )
    return render(request, "pay/payslip_new.html", context)


# Helper function for Excel report generation (remains unchanged from previous step)
def _run_totals(payroll_data):
    """Monthly figure totals across a run's entries (frozen per entry)."""
    entries = [run_entry.payroll_entry for run_entry in payroll_data.select_related(
        "payroll_entry__pays__employee_pay"
    )]
    return {key: value.quantize(Decimal("0.01")) for key, value in sum_figures(entries).items()}


def _resolve(obj, path):
    for name in path.split("__"):
        obj = getattr(obj, name, None) if obj is not None else None
    return obj


def _figure_rows(payroll_data, fields, figure_keys, trailing_fields=()):
    """Export rows: entry attributes, the entry's monthly figures, then any
    trailing entry attributes."""
    rows = []
    for run_entry in payroll_data.select_related("payroll_entry__pays__employee_pay"):
        figures = run_entry.payroll_entry.figures
        rows.append(
            (
                *(_resolve(run_entry, path) for path in fields),
                *(figures[key].quantize(Decimal("0.01")) for key in figure_keys),
                *(_resolve(run_entry, path) for path in trailing_fields),
            )
        )
    return rows


def generate_excel_report(
    filename_base,
    sheet_name_base,
    pay_period_date,
    columns,
    data_rows,
    total_label,
    total_value_index,
):
    if xlwt is None:
        return HttpResponse(
            "xlwt is required to generate Excel reports.",
            status=503,
            content_type="text/plain",
        )
    filename = f"{filename_base}_{pay_period_date.strftime('%Y%m')}.xls"
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb = xlwt.Workbook(encoding="utf-8")
    sheet_display_name = f"{sheet_name_base} - {pay_period_date.strftime('%B %Y')}"
    if len(sheet_display_name) > 31:
        sheet_display_name = sheet_display_name[:31]
    ws = wb.add_sheet(sheet_display_name)
    row_num = 0
    font_style_bold = xlwt.XFStyle()
    font_style_bold.font.bold = True
    for col_num, column_title in enumerate(columns):
        ws.write(row_num, col_num, column_title, font_style_bold)
    font_style_normal = xlwt.XFStyle()
    calculated_total = 0
    if total_value_index is not None:
        for row in data_rows:
            row_num += 1
            for col_num, cell_value in enumerate(row):
                ws.write(row_num, col_num, cell_value, font_style_normal)
            if total_value_index < len(row) and isinstance(
                row[total_value_index], (int, float, Decimal)
            ):
                calculated_total += row[total_value_index]
    else:
        for row in data_rows:
            row_num += 1
            for col_num, cell_value in enumerate(row):
                ws.write(row_num, col_num, cell_value, font_style_normal)
    if total_label and total_value_index is not None:
        row_num += 1
        ws.write(row_num, 0, total_label, font_style_bold)
        ws.write(row_num, len(columns) - 1, calculated_total, font_style_bold)
    wb.save(response)
    return response


def try_parse_date(date_str):
    """
    Utility function to parse a date string in 'YYYY-MM-DD' format.
    Returns a datetime.date object or None if parsing fails.
    """
    from datetime import datetime

    try:
        return datetime.strptime(date_str, "%Y-%m").date()
    except ValueError:
        return None


@permission_required("payroll.view_payrollrun", raise_exception=True)
def varview_report(request, paydays):
    # paydays is a string like 'YYYY-MM-DD' from the URL
    # Ensure PayrollRun objects are filtered correctly if 'paydays' in PayrollRun is a DateField
    pay_period_date_obj = try_parse_date(
        paydays
    )  # Assuming you have a utility for this or use Django's converters
    if not pay_period_date_obj:
        raise Http404("Invalid date format for pay period.")

    company = get_user_company(request.user)
    var = PayrollRunEntry.objects.filter(
        payroll_run__paydays=pay_period_date_obj,
        payroll_entry__company=company,
    )
    varx = get_object_or_404(PayrollRun, paydays=pay_period_date_obj, company=company)
    dates = utils.convert_month_to_word(str(varx.paydays))  # Use varx.paydays
    paydays_total = var.aggregate(
        Sum("payroll_entry__netpay")
    )  # Use 'var' which is already filtered

    context = {
        "pay_var": var,
        "dates": dates,
        "paydays": varx.paydays.strftime("%Y-%m-%d"),  # Pass consistent date string
        "total": paydays_total["payroll_entry__netpay__sum"],
    }
    return render(request, "pay/var_report.html", context)


@login_required
def payslip_pdf(request, id):
    pay_id = resolve_payslip_run_entry(id)
    if pay_id is None:
        raise Http404("No PayrollRunEntry matches the given query.")

    if not can_view_payslip(request.user, pay_id):
        return HttpResponseForbidden("You are not authorized to view this payslip PDF.")

    payroll_entry = pay_id.payroll_entry
    template_path = "pay/payslip_pdf.html"
    num2word = utils.format_currency_words_with_kobo(payroll_entry.netpay)
    html_string = render_to_string(
        template_path, context={"payroll": payroll_entry, "num2words": num2word}
    )
    pdf_file_name = (
        f"{payroll_entry.pays.first_name}-{payroll_entry.pays.last_name}-payslip.pdf"
    )
    log_sensitive_employee_data_access(
        employee=payroll_entry.pays,
        accessed_by=request.user,
        fields=("tin_no", "bank_account_number"),
        purpose="payslip_pdf",
        metadata={"view": "payslip_pdf", "payroll_run_entry_id": pay_id.id},
    )

    pdf_file_path = f"/tmp/{pdf_file_name}"
    if HTML is None:
        response = HttpResponse(_simple_pdf(html_string), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{pdf_file_name}"'
        return response
    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    html.write_pdf(target=pdf_file_path)
    with open(pdf_file_path, "rb") as pdf_file:
        response = HttpResponse(pdf_file.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{pdf_file_name}"'
        return response


@permission_required("payroll.view_payrollrun", raise_exception=True)
def bank_reports(request):
    company = get_user_company(request.user)
    payroll = payroll_runs_distinct_by_period(company)
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(
        request, "pay/bank_reports_new.html", {"payroll": payroll, "dates": dates}
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def bank_report(request, pay_id):  # pay_id here is PayrollRun.id
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    )
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    netpay_total = payroll_data.aggregate(Sum("payroll_entry__netpay"))
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=payroll_data,
        fields=("bank_account_name", "bank_account_number"),
        purpose="payroll_report_view",
        report_name="bank_report",
    )
    return render(
        request,
        "pay/bank_report_new.html",
        {
            "payroll": payroll_data,
            "dates": dates,
            "total_netpay": netpay_total["payroll_entry__netpay__sum"],
        },
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def bank_report_download(request, pay_id):
    company = get_user_company(request.user)
    pay_period = get_object_or_404(PayrollRun, id=pay_id, company=company)
    columns = [
        "Employee No",
        "Employee First Name",
        "Employee Last Name",
        "Employee Bank Name",
        "Employee Bank Account Name",
        "Employee Bank Account No.",
        "Net Pay",
    ]
    data_rows = PayrollRunEntry.objects.filter(
        payroll_run_id=pay_id,
        payroll_entry__company=company,
    ).values_list(
        "payroll_entry__pays__emp_id",
        "payroll_entry__pays__first_name",
        "payroll_entry__pays__last_name",
        "payroll_entry__pays__bank",
        "payroll_entry__pays__bank_account_name",
        "payroll_entry__pays__bank_account_number",
        "payroll_entry__netpay",
    )
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=PayrollRunEntry.objects.filter(
            payroll_run_id=pay_id,
            payroll_entry__company=company,
        ),
        fields=("bank_account_name", "bank_account_number"),
        purpose="payroll_report_export",
        report_name="bank_report",
    )
    return generate_excel_report(
        "bank_report",
        "Bank Report",
        pay_period.paydays,
        columns,
        data_rows,
        "Total Net Pay",
        len(columns) - 1,
    )


COST_REPORT_KEYS = (
    "gross",
    "employee_paye",
    "employee_pension",
    "employee_nhf",
    "employee_nhia",
    "employee_water",
    "net_pay",
    "employer_pension",
    "employer_nhia",
    "employer_nsitf",
    "employer_itf",
    "employer_cost",
)


def _cost_of_employment_rows(payroll_data):
    """
    Per-employee monthly employer-vs-employee cost rows for a pay run.

    Reads the figures frozen on each entry (``payroll_figures``), which use
    the same math as ``utils.monthly_cost_breakdown`` and the dashboard.
    """
    rows = []
    totals = {key: Decimal("0.00") for key in COST_REPORT_KEYS}

    for entry in payroll_data:
        payroll_entry = entry.payroll_entry
        if payroll_entry.pays.employee_pay is None and not payroll_entry.statutory_snapshot:
            continue
        values = payroll_entry.figures
        rows.append({"employee": entry.payroll_entry.pays, **values})
        for key in COST_REPORT_KEYS:
            totals[key] += values[key]

    return rows, {key: value.quantize(Decimal("0.01")) for key, value in totals.items()}


@permission_required("payroll.view_payrollrun", raise_exception=True)
def cost_of_employment_reports(request):
    company = get_user_company(request.user)
    payroll = payroll_runs_distinct_by_period(company)
    dates = [utils.convert_month_to_word(str(run.paydays)) for run in payroll]
    return render(
        request,
        "pay/cost_of_employment_reports.html",
        {"payroll": payroll, "dates": dates},
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def cost_of_employment_report(request, pay_id):
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    ).select_related("payroll_entry__pays__employee_pay")
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    rows, totals = _cost_of_employment_rows(payroll_data)
    return render(
        request,
        "pay/cost_of_employment_report.html",
        {"rows": rows, "totals": totals, "dates": dates},
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def cost_of_employment_report_download(request, pay_id):
    """Excel export of the cost-of-employment report for finance handoff.

    Reuses ``_cost_of_employment_rows`` so the export matches the page row
    for row (same monthly conventions and totals).
    """
    company = get_user_company(request.user)
    pay_period = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period,
        payroll_entry__company=company,
    ).select_related("payroll_entry__pays__employee_pay")
    rows, totals = _cost_of_employment_rows(payroll_data)
    columns = [
        "EmpNo",
        "Employee First_Name",
        "Employee Last Name",
        "Gross",
        "PAYE",
        "Pension (EE)",
        "NHF",
        "NHIA (EE)",
        "Water",
        "Net Pay",
        "Pension (ER)",
        "NHIA (ER)",
        "NSITF",
        "ITF",
        "Employer Cost",
    ]
    data_rows = [
        [
            row["employee"].emp_id,
            row["employee"].first_name,
            row["employee"].last_name,
            row["gross"],
            row["employee_paye"],
            row["employee_pension"],
            row["employee_nhf"],
            row["employee_nhia"],
            row["employee_water"],
            row["net_pay"],
            row["employer_pension"],
            row["employer_nhia"],
            row["employer_nsitf"],
            row["employer_itf"],
            row["employer_cost"],
        ]
        for row in rows
    ]
    return generate_excel_report(
        "cost_of_employment_report",
        "Cost of Employment Report",
        pay_period.paydays,
        columns,
        data_rows,
        "Total Employer Cost",
        len(columns) - 1,
    )


def _nhis_mode_label(company):
    """Human-readable NHIA computation mode for the report header."""
    setting = CompanyPayrollSetting.objects.filter(company=company).first()
    if setting is None:
        return "Basic salary basis \u2014 employee 5% / employer 10%"
    if setting.hmo_monthly_premium:
        return (
            f"HMO premium \u20a6{Decimal(setting.hmo_monthly_premium):,.2f} "
            f"per employee/month ({setting.get_health_basis_display()})"
        )
    return setting.get_health_basis_display()


@permission_required("payroll.view_payrollrun", raise_exception=True)
def nhis_reports(request):
    company = get_user_company(request.user)
    payroll = payroll_runs_distinct_by_period(company)
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(
        request, "pay/nhis_reports.html", {"payroll": payroll, "dates": dates}
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def nhis_report(request, pay_id):
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    )
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    totals = _run_totals(payroll_data)
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=payroll_data,
        fields=("bank_account_number",),
        purpose="payroll_report_view",
        report_name="nhis_report",
    )
    return render(
        request,
        "pay/nhis_report.html",
        {
            "payroll": payroll_data,
            "total": totals["nhia_total"],
            "employee_total": totals["employee_nhia"],
            "employer_total": totals["employer_nhia"],
            "mode": _nhis_mode_label(company),
            "dates": dates,
        },
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def nhis_report_download(request, pay_id):
    company = get_user_company(request.user)
    pay_period = get_object_or_404(PayrollRun, id=pay_id, company=company)
    columns = [
        "EmpNo",
        "Emp First_Name",
        "Last Name",
        "HMO Provider",
        "Bank Name",
        "Account No.",
        "Health insurance payment",
    ]
    data_rows = _figure_rows(
        PayrollRunEntry.objects.filter(
            payroll_run_id=pay_id,
            payroll_entry__company=company,
        ),
        (
            "payroll_entry__pays__emp_id",
            "payroll_entry__pays__first_name",
            "payroll_entry__pays__last_name",
            "payroll_entry__pays__hmo_provider",
            "payroll_entry__pays__bank",
            "payroll_entry__pays__bank_account_number",
        ),
        ("nhia_total",),
    )
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=PayrollRunEntry.objects.filter(
            payroll_run_id=pay_id,
            payroll_entry__company=company,
        ),
        fields=("bank_account_number",),
        purpose="payroll_report_export",
        report_name="nhis_report",
    )
    return generate_excel_report(
        "health_insurance_report",
        "Health Insurance Report",
        pay_period.paydays,
        columns,
        data_rows,
        "Total NHIS payment",
        len(columns) - 1,
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def nhf_reports(request):
    company = get_user_company(request.user)
    payroll = payroll_runs_distinct_by_period(company)
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(request, "pay/nhf_reports.html", {"payroll": payroll, "dates": dates})


@permission_required("payroll.view_payrollrun", raise_exception=True)
def nhf_report(request, pay_id):
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    )
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    totals = _run_totals(payroll_data)
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=payroll_data,
        fields=("bank_account_number",),
        purpose="payroll_report_view",
        report_name="nhf_report",
    )
    return render(
        request,
        "pay/nhf_report.html",
        {
            "payroll": payroll_data,
            "total": totals["employee_nhf"],
            "dates": dates,
        },
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def nhf_report_download(request, pay_id):
    company = get_user_company(request.user)
    pay_period = get_object_or_404(PayrollRun, id=pay_id, company=company)
    columns = [
        "EmpNo",
        "Emp First_Name",
        "Last Name",
        "Bank Name",
        "Account No.",
        "National Housing Fund payment",
    ]
    data_rows = _figure_rows(
        PayrollRunEntry.objects.filter(
            payroll_run_id=pay_id,
            payroll_entry__company=company,
        ),
        (
            "payroll_entry__pays__emp_id",
            "payroll_entry__pays__first_name",
            "payroll_entry__pays__last_name",
            "payroll_entry__pays__bank",
            "payroll_entry__pays__bank_account_number",
        ),
        ("employee_nhf",),
    )
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=PayrollRunEntry.objects.filter(
            payroll_run_id=pay_id,
            payroll_entry__company=company,
        ),
        fields=("bank_account_number",),
        purpose="payroll_report_export",
        report_name="nhf_report",
    )
    return generate_excel_report(
        "nhf_report",
        "National Housing Fund Report",
        pay_period.paydays,
        columns,
        data_rows,
        "Total National Housing Fund payment",
        len(columns) - 1,
    )


@permission_required(
    "payroll.view_payrollrun", raise_exception=True
)  # Assuming these list PayrollRun periods for selection
def payee_reports(request):
    company = get_user_company(request.user)
    payroll = payroll_runs_distinct_by_period(company)
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(
        request, "pay/payee_reports_new.html", {"payroll": payroll, "dates": dates}
    )


@permission_required(
    "payroll.view_payrollrun", raise_exception=True
)  # Specific report for a PayrollRun period
def payee_report(request, pay_id):
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    )
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    totals = _run_totals(payroll_data)
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=payroll_data,
        fields=("tin_no",),
        purpose="payroll_report_view",
        report_name="payee_report",
    )
    return render(
        request,
        "pay/payee_report_new.html",
        {
            "payroll": payroll_data,
            "total": totals["employee_paye"],
            "dates": dates,
        },
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def payee_report_download(request, pay_id):
    company = get_user_company(request.user)
    pay_period = get_object_or_404(PayrollRun, id=pay_id, company=company)
    columns = [
        "EmpNo",
        "Employee First_Name",
        "Employee Last Name",
        "Tax Number",
        "Gross Pay",
        "Payee Amount",
    ]
    data_rows = _figure_rows(
        PayrollRunEntry.objects.filter(
            payroll_run_id=pay_id,
            payroll_entry__company=company,
        ),
        (
            "payroll_entry__pays__emp_id",
            "payroll_entry__pays__first_name",
            "payroll_entry__pays__last_name",
            "payroll_entry__pays__tin_no",
        ),
        ("gross", "employee_paye"),
    )
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=PayrollRunEntry.objects.filter(
            payroll_run_id=pay_id,
            payroll_entry__company=company,
        ),
        fields=("tin_no",),
        purpose="payroll_report_export",
        report_name="payee_report",
    )
    return generate_excel_report(
        "payee_report",
        "PAYE Report",
        pay_period.paydays,
        columns,
        data_rows,
        "Total Payee",
        len(columns) - 1,
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def compliance_calendar(request):
    """
    Statutory compliance calendar: due dates for PAYE, pension, NHF, NHIA,
    NSITF and ITF remittances derived from the company's payroll runs, with
    overdue flags and penalty exposure.
    """
    company = get_user_company(request.user)
    return render(request, "pay/compliance_calendar.html", compliance_summary(company))


@require_POST
@permission_required("payroll.view_payrollrun", raise_exception=True)
def mark_remittance(request, obligation, period):
    """
    Record (or clear, with ``unmark=1``) the remittance/filing for one
    obligation-period of the caller's company.
    """
    company = get_user_company(request.user)
    valid_obligations = {key for key, _ in RemittanceRecord.OBLIGATION_CHOICES}
    if obligation not in valid_obligations:
        raise Http404("Unknown obligation type.")

    period_date = utils.try_parse_date(period)  # YYYY-MM
    if period_date is None:
        raise Http404("Invalid pay period.")

    record, _ = RemittanceRecord.objects.get_or_create(
        company=company,
        obligation=obligation,
        period=period_date,
        defaults={"remitted_on": None},
    )
    if request.POST.get("unmark"):
        record.remitted_on = None
    else:
        record.remitted_on = timezone.localdate()
        # Fan out a signed webhook when a remittance is filed (P1-9).
        from webhooks.services import emit_event

        emit_event(
            company,
            "remittance.filed",
            {
                "obligation": obligation,
                "period": period,
                "remitted_on": record.remitted_on.isoformat(),
            },
        )
    record.save(update_fields=["remitted_on", "updated_at"])
    return redirect("payroll:compliance_calendar")


@permission_required(
    "payroll.view_payrollrun", raise_exception=True
)  # Assuming these list PayrollRun periods
def pension_reports(request):
    company = get_user_company(request.user)
    payroll = payroll_runs_distinct_by_period(company)
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(
        request, "pay/pension_reports_new.html", {"payroll": payroll, "dates": dates}
    )


@permission_required(
    "payroll.view_payrollrun", raise_exception=True
)  # Specific report for a PayrollRun period
def pension_report(request, pay_id):
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    ).select_related("payroll_entry__pays__employee_pay")
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    totals = _run_totals(payroll_data)
    rows = [(entry, entry.payroll_entry.figures) for entry in payroll_data]
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=payroll_data,
        fields=("pension_rsa",),
        purpose="payroll_report_view",
        report_name="pension_report",
    )
    return render(
        request,
        "pay/pension_report_new.html",
        {
            "rows": rows,
            "total": totals["pension_total"],
            "employee_total": totals["employee_pension"],
            "employer_total": totals["employer_pension"],
            "dates": dates,
        },
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def pension_report_download(request, pay_id):
    company = get_user_company(request.user)
    pay_period = get_object_or_404(PayrollRun, id=pay_id, company=company)
    columns = [
        "EmpNo",
        "Employee First_Name",
        "Employee Last Name",
        "Pension Fund Manager",
        "Pension RSA",
        "Gross Pay",
        "Total Pension Contribution",
    ]
    data_rows = _figure_rows(
        PayrollRunEntry.objects.filter(
            payroll_run_id=pay_id,
            payroll_entry__company=company,
        ),
        (
            "payroll_entry__pays__emp_id",
            "payroll_entry__pays__first_name",
            "payroll_entry__pays__last_name",
            "payroll_entry__pays__pension_fund_manager",
            "payroll_entry__pays__pension_rsa",
        ),
        ("gross", "pension_total"),
    )
    _log_payroll_report_sensitive_access(
        request=request,
        payroll_entries=PayrollRunEntry.objects.filter(
            payroll_run_id=pay_id,
            payroll_entry__company=company,
        ),
        fields=("pension_rsa",),
        purpose="payroll_report_export",
        report_name="pension_report",
    )
    return generate_excel_report(
        "pension_report",
        "Pension Report",
        pay_period.paydays,
        columns,
        data_rows,
        "Total Pension",
        len(columns) - 1,
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
def varview_download(request, paydays):
    pay_period_date_obj = utils.try_parse_date(paydays)
    if not pay_period_date_obj:
        raise Http404("Invalid date format for pay period.")
    company = get_user_company(request.user)
    pay_period = get_object_or_404(PayrollRun, paydays=pay_period_date_obj, company=company)
    columns = [
        "Employee First_Name",
        "Employee Last Name",
        "Gross Salary",
        "Water Fee",
        "Payee",
        "Pension Contribution",
        "Net Pay",
    ]
    data_rows = _figure_rows(
        PayrollRunEntry.objects.filter(
            payroll_run=pay_period,
            payroll_entry__company=company,
        ),
        ("payroll_entry__pays__first_name", "payroll_entry__pays__last_name"),
        ("gross", "employee_water", "employee_paye", "employee_pension"),
        trailing_fields=("payroll_entry__netpay",),
    )
    return generate_excel_report(
        "payroll_report",
        "Payroll Report",
        pay_period.paydays,
        columns,
        data_rows,
        "Total Net Pay",
        len(columns) - 1,
    )
