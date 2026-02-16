from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)  # Added permission_required
from django.db.models import Sum
from django.template.loader import render_to_string
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.views.decorators.cache import cache_page

# user_passes_test is removed as it's no longer used
from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT

from payroll.models import (
    PayrollRun,
    PayrollEntry,
    PayrollRunEntry,
    EmployeeProfile,
)
from payroll import utils
from company.utils import get_user_company
from num2words import num2words
from weasyprint import HTML
import xlwt
from decimal import Decimal

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)

# check_super and is_hr_user functions are removed


@login_required
@cache_page(CACHE_TTL)
def payslip(request, id):
    company = get_user_company(request.user)
    pay_id = get_object_or_404(PayrollRunEntry, id=id, payroll_entry__company=company)
    target_employee_user = pay_id.payroll_entry.pays.user
    if not (
        request.user == target_employee_user
        or request.user.has_perm("payroll.view_payroll")
    ):
        raise HttpResponseForbidden("You are not authorized to view this payslip.")

    num2word = num2words(pay_id.payroll_entry.netpay)
    dates = utils.convert_month_to_word(str(pay_id.payroll_run.paydays))
    context = {
        "pay": pay_id,
        "num2words": num2word,
        "dates": dates,
    }
    return render(request, "pay/payslip_new.html", context)


# Helper function for Excel report generation (remains unchanged from previous step)
def generate_excel_report(
    filename_base,
    sheet_name_base,
    pay_period_date,
    columns,
    data_rows,
    total_label,
    total_value_index,
):
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
@cache_page(CACHE_TTL)
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
def payslip_pdf(request, id):  # id here is EmployeeProfile.id
    company = get_user_company(request.user)
    target_employee_profile = get_object_or_404(EmployeeProfile, id=id, company=company)
    if not (
        request.user == target_employee_profile.user
        or request.user.has_perm("payroll.view_payroll")
    ):
        raise HttpResponseForbidden("You are not authorized to view this payslip PDF.")

    payroll_entry = (
        PayrollEntry.objects.filter(pays_id=target_employee_profile.id)
        .order_by("-id")
        .first()
    )
    if not payroll_entry:
        return HttpResponse("No payroll data available to generate PDF.", status=404)
    template_path = "pay/payslip_pdf.html"
    num2word = num2words(payroll_entry.netpay)
    html_string = render_to_string(
        template_path, context={"payroll": payroll_entry, "num2words": num2word}
    )
    pdf_file_name = (
        f"{payroll_entry.pays.first_name}-{payroll_entry.pays.last_name}-payslip.pdf"
    )

    pdf_file_path = f"/tmp/{pdf_file_name}"
    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    html.write_pdf(target=pdf_file_path)
    with open(pdf_file_path, "rb") as pdf_file:
        response = HttpResponse(pdf_file.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{pdf_file_name}"'
        return response


@permission_required("payroll.view_payrollrun", raise_exception=True)
@cache_page(CACHE_TTL)
def bank_reports(request):
    company = get_user_company(request.user)
    payroll = PayrollRun.objects.filter(company=company).order_by("paydays").distinct("paydays")
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(
        request, "pay/bank_reports_new.html", {"payroll": payroll, "dates": dates}
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
@cache_page(CACHE_TTL)
def bank_report(request, pay_id):  # pay_id here is PayrollRun.id
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    )
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    netpay_total = payroll_data.aggregate(Sum("payroll_entry__netpay"))
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
    return generate_excel_report(
        "bank_report",
        "Bank Report",
        pay_period.paydays,
        columns,
        data_rows,
        "Total Net Pay",
        len(columns) - 1,
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
@cache_page(CACHE_TTL)
def nhis_reports(request):
    company = get_user_company(request.user)
    payroll = PayrollRun.objects.filter(company=company).order_by("paydays").distinct("paydays")
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(
        request, "pay/nhis_reports.html", {"payroll": payroll, "dates": dates}
    )


@permission_required("payroll.view_payrollrun", raise_exception=True)
@cache_page(CACHE_TTL)
def nhis_report(request, pay_id):
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    )
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    nhis_total = payroll_data.aggregate(Sum("payroll_entry__nhif"))
    return render(
        request,
        "pay/nhis_report.html",
        {
            "payroll": payroll_data,
            "total": nhis_total["payroll_entry__nhif__sum"],
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
        "Bank Name",
        "Account No.",
        "Health insurance payment",
    ]
    data_rows = PayrollRunEntry.objects.filter(
        payroll_run_id=pay_id,
        payroll_entry__company=company,
    ).values_list(
        "payroll_entry__pays__emp_id",
        "payroll_entry__pays__first_name",
        "payroll_entry__pays__last_name",
        "payroll_entry__pays__bank",
        "payroll_entry__pays__bank_account_number",
        "payroll_entry__nhif",
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
@cache_page(CACHE_TTL)
def nhf_reports(request):
    company = get_user_company(request.user)
    payroll = PayrollRun.objects.filter(company=company).order_by("paydays").distinct("paydays")
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(request, "pay/nhf_reports.html", {"payroll": payroll, "dates": dates})


@permission_required("payroll.view_payrollrun", raise_exception=True)
@cache_page(CACHE_TTL)
def nhf_report(request, pay_id):
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    )
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    nhf_total = payroll_data.aggregate(Sum("payroll_entry__nhf"))
    return render(
        request,
        "pay/nhf_report.html",
        {
            "payroll": payroll_data,
            "total": nhf_total["payroll_entry__nhf__sum"],
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
    data_rows = PayrollRunEntry.objects.filter(
        payroll_run_id=pay_id,
        payroll_entry__company=company,
    ).values_list(
        "payroll_entry__pays__emp_id",
        "payroll_entry__pays__first_name",
        "payroll_entry__pays__last_name",
        "payroll_entry__pays__bank",
        "payroll_entry__pays__bank_account_number",
        "payroll_entry__nhf",
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
@cache_page(CACHE_TTL)
def payee_reports(request):
    company = get_user_company(request.user)
    payroll = PayrollRun.objects.filter(company=company).order_by("paydays").distinct("paydays")
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(
        request, "pay/payee_reports_new.html", {"payroll": payroll, "dates": dates}
    )


@permission_required(
    "payroll.view_payrollrun", raise_exception=True
)  # Specific report for a PayrollRun period
@cache_page(CACHE_TTL)
def payee_report(request, pay_id):
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    )
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    payee_total = payroll_data.aggregate(Sum("payroll_entry__pays__employee_pay__payee"))
    return render(
        request,
        "pay/payee_report_new.html",
        {
            "payroll": payroll_data,
            "total": payee_total["payroll_entry__pays__employee_pay__payee__sum"],
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
    data_rows = PayrollRunEntry.objects.filter(
        payroll_run_id=pay_id,
        payroll_entry__company=company,
    ).values_list(
        "payroll_entry__pays__emp_id",
        "payroll_entry__pays__first_name",
        "payroll_entry__pays__last_name",
        "payroll_entry__pays__tin_no",
        "payroll_entry__pays__employee_pay__basic_salary",
        "payroll_entry__pays__employee_pay__payee",
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


@permission_required(
    "payroll.view_payrollrun", raise_exception=True
)  # Assuming these list PayrollRun periods
@cache_page(CACHE_TTL)
def pension_reports(request):
    company = get_user_company(request.user)
    payroll = PayrollRun.objects.filter(company=company).order_by("paydays").distinct("paydays")
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in payroll
    ]  # Access .paydays
    return render(
        request, "pay/pension_reports_new.html", {"payroll": payroll, "dates": dates}
    )


@permission_required(
    "payroll.view_payrollrun", raise_exception=True
)  # Specific report for a PayrollRun period
@cache_page(CACHE_TTL)
def pension_report(request, pay_id):
    company = get_user_company(request.user)
    pay_period_obj = get_object_or_404(PayrollRun, id=pay_id, company=company)
    payroll_data = PayrollRunEntry.objects.filter(
        payroll_run=pay_period_obj,
        payroll_entry__company=company,
    )
    dates = utils.convert_month_to_word(str(pay_period_obj.paydays))
    pension_total = payroll_data.aggregate(
        Sum("payroll_entry__pays__employee_pay__pension")
    )
    return render(
        request,
        "pay/pension_report_new.html",
        {
            "payroll": payroll_data,
            "total": pension_total["payroll_entry__pays__employee_pay__pension__sum"],
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
        "Tax Number",
        "Gross Pay",
        "Total Pension Contribution",
    ]
    data_rows = PayrollRunEntry.objects.filter(
        payroll_run_id=pay_id,
        payroll_entry__company=company,
    ).values_list(
        "payroll_entry__pays__emp_id",
        "payroll_entry__pays__first_name",
        "payroll_entry__pays__last_name",
        "payroll_entry__pays__pension_rsa",
        "payroll_entry__pays__employee_pay__basic_salary",
        "payroll_entry__pays__employee_pay__pension",
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
    data_rows = PayrollRunEntry.objects.filter(
        payroll_run=pay_period,
        payroll_entry__company=company,
    ).values_list(
        "payroll_entry__pays__first_name",
        "payroll_entry__pays__last_name",
        "payroll_entry__pays__employee_pay__basic_salary",
        "payroll_entry__pays__employee_pay__water_rate",
        "payroll_entry__pays__employee_pay__payee",
        "payroll_entry__pays__employee_pay__pension_employee",
        "payroll_entry__netpay",
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
