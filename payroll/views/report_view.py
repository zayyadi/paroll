from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum

# from django.core.cache import cache
from django.template.loader import render_to_string
from django.http import HttpResponse, HttpResponseForbidden

# from django.core.files.storage import FileSystemStorage
from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT

# from django.views.decorators.cache import cache_page


from payroll.models import (
    PayT,
    PayVar,
    Payday,
    EmployeeProfile,
)

from payroll import utils


from num2words import num2words

# import xhtml2pdf.pisa as pisa
from weasyprint import HTML
import xlwt
from decimal import Decimal # Added for type checking in helper

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)


def check_super(user):
    return user.is_superuser


def is_hr_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.groups.filter(name='HR').exists())


@login_required
def payslip(request, id):
    pay_id = get_object_or_404(Payday, id=id)
    # Authorization check:
    target_employee_user = pay_id.payroll_id.pays.user
    if not (request.user == target_employee_user or is_hr_user(request.user)):
        raise HttpResponseForbidden("You are not authorized to view this payslip.")
    num2word = num2words(pay_id.payroll_id.netpay)
    dates = utils.convert_month_to_word(str(pay_id.paydays_id.paydays))
    context = {
        "pay": pay_id,
        "num2words": num2word,
        "dates": dates,
    }
    return render(request, "pay/payslip.html", context)


# Helper function for Excel report generation
def generate_excel_report(filename_base, sheet_name_base, pay_period_date, columns, data_rows, total_label, total_value_index):
    filename = f"{filename_base}_{pay_period_date.strftime('%Y%m')}.xls" # Changed to .xls
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    wb = xlwt.Workbook(encoding="utf-8")
    sheet_display_name = f"{sheet_name_base} - {pay_period_date.strftime('%B %Y')}"
    # Ensure sheet name is not too long (max 31 chars for Excel)
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
    if total_value_index is not None: # Ensure total_value_index is valid if provided
        for row in data_rows:
            row_num += 1
            for col_num, cell_value in enumerate(row):
                ws.write(row_num, col_num, cell_value, font_style_normal)
            if total_value_index < len(row) and isinstance(row[total_value_index], (int, float, Decimal)): # Check type for sum
                calculated_total += row[total_value_index]
    else: # No total to calculate per row, just write rows
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


@user_passes_test(check_super)
def varview_report(request, paydays):
    var = Payday.objects.filter(paydays_id__paydays=paydays)
    varx = PayT.objects.filter(paydays=paydays).first()
    dates = utils.convert_month_to_word(str(varx))
    paydays_total = Payday.objects.filter(paydays_id__paydays=paydays).aggregate(
        Sum("payroll_id__netpay")
    )

    context = {
        "pay_var": var,
        "dates": dates,
        "paydays": paydays,
        "total": paydays_total["payroll_id__netpay__sum"],
    }
    return render(request, "pay/var_report.html", context)


@login_required
def payslip_pdf(request, id):
    target_employee_profile = get_object_or_404(EmployeeProfile, id=id)

    # Authorization check:
    if not (request.user == target_employee_profile.user or is_hr_user(request.user)):
        raise HttpResponseForbidden("You are not authorized to view this payslip PDF.")

    payroll_entry = PayVar.objects.filter(pays_id=target_employee_profile.id).order_by('-id').first()
    if not payroll_entry:
        return HttpResponse("No payroll data available to generate PDF.", status=404)

    template_path = "pay/payslip_pdf.html"
    html_string = render_to_string(template_path, {"payroll": payroll_entry})

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


@user_passes_test(check_super)
def bank_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    dates = [utils.convert_month_to_word(str(varss)) for varss in payroll]
    return render(
        request,
        "pay/bank_reports.html",
        {"payroll": payroll, "dates": dates},
    )


@user_passes_test(check_super)
def bank_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    varx = PayT.objects.filter(id=pay_id).first()
    dates = utils.convert_month_to_word(str(varx.paydays))
    netpay_total = Payday.objects.filter(paydays_id_id=pay_id).aggregate(
        Sum("payroll_id__netpay")
    )
    return render(
        request,
        "pay/bank_report.html",
        {
            "payroll": payroll,
            "dates": dates,
            "total_netpay": netpay_total["payroll_id__netpay__sum"],
        },
    )


@user_passes_test(check_super)
def bank_report_download(request, pay_id):
    pay_period = get_object_or_404(PayT, id=pay_id)
    columns = [
        "Employee No", "Employee First Name", "Employee Last Name",
        "Employee Bank Name", "Employee Bank Account Name",
        "Employee Bank Account No.", "Net Pay"
    ]
    data_rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__pays__emp_id", "payroll_id__pays__first_name",
        "payroll_id__pays__last_name", "payroll_id__pays__bank",
        "payroll_id__pays__bank_account_name", "payroll_id__pays__bank_account_number",
        "payroll_id__netpay"
    )
    return generate_excel_report(
        "bank_report", "Bank Report", pay_period.paydays,
        columns, data_rows, "Total Net Pay", len(columns) - 1
    )


@user_passes_test(check_super)
def nhis_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    dates = [utils.convert_month_to_word(str(varss)) for varss in payroll]
    return render(
        request,
        "pay/nhis_reports.html",
        {
            "payroll": payroll,
            "dates": dates,
        },
    )


@user_passes_test(check_super)
def nhis_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    varx = PayT.objects.filter(id=pay_id).first()
    dates = utils.convert_month_to_word(str(varx.paydays))
    nhis_total = Payday.objects.filter(paydays_id_id=pay_id).aggregate(
        Sum("payroll_id__nhif")
    )
    return render(
        request,
        "pay/nhis_report.html",
        {
            "payroll": payroll,
            "total": nhis_total["payroll_id__nhif__sum"],
            "dates": dates,
        },
    )


@user_passes_test(check_super)
def nhis_report_download(request, pay_id):
    pay_period = get_object_or_404(PayT, id=pay_id)
    columns = [
        "EmpNo", "Emp First_Name", "Last Name",
        "Bank Name", "Account No.", "Health insurance payment"
    ]
    data_rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__pays__emp_id", "payroll_id__pays__first_name",
        "payroll_id__pays__last_name", "payroll_id__pays__bank",
        "payroll_id__pays__bank_account_number", "payroll_id__nhif"
    )
    return generate_excel_report(
        "health_insurance_report", "Health Insurance Report", pay_period.paydays,
        columns, data_rows, "Total NHIS payment", len(columns) - 1
    )


@user_passes_test(check_super)
def nhf_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    dates = [utils.convert_month_to_word(str(varss)) for varss in payroll]
    return render(
        request,
        "pay/nhf_reports.html",
        {"payroll": payroll, "dates": dates},  # Corrected template name
    )


@user_passes_test(check_super)
def nhf_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    nhf_total = Payday.objects.filter(paydays_id_id=pay_id).aggregate(
        Sum("payroll_id__nhf")
    )
    varx = PayT.objects.filter(id=pay_id).first()
    dates = utils.convert_month_to_word(str(varx.paydays))
    return render(
        request,
        "pay/nhf_report.html",
        {
            "payroll": payroll,
            "total": nhf_total["payroll_id__nhf__sum"],
            "dates": dates,
        },
    )


@user_passes_test(check_super)
def nhf_report_download(request, pay_id):
    pay_period = get_object_or_404(PayT, id=pay_id)
    columns = [
        "EmpNo", "Emp First_Name", "Last Name",
        "Bank Name", "Account No.", "National Housing Fund payment"
    ]
    data_rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__pays__emp_id", "payroll_id__pays__first_name",
        "payroll_id__pays__last_name", "payroll_id__pays__bank",
        "payroll_id__pays__bank_account_number", "payroll_id__nhf"
    )
    return generate_excel_report(
        "nhf_report", "National Housing Fund Report", pay_period.paydays,
        columns, data_rows, "Total National Housing Fund payment", len(columns) - 1
    )


@user_passes_test(check_super)
def payee_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    dates = [utils.convert_month_to_word(str(varss)) for varss in payroll]
    return render(
        request,
        "pay/payee_reports.html",
        {
            "payroll": payroll,
            "dates": dates,
        },
    )


@user_passes_test(check_super)
def payee_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    varx = PayT.objects.filter(id=pay_id).first()
    dates = utils.convert_month_to_word(str(varx.paydays))
    payee_total = Payday.objects.filter(
        paydays_id_id=pay_id
    ).aggregate(  # Corrected variable name
        Sum("payroll_id__pays__employee_pay__payee")
    )
    return render(
        request,
        "pay/payee_report.html",
        {
            "payroll": payroll,
            "total": payee_total["payroll_id__pays__employee_pay__payee__sum"],
            "dates": dates,
        },
    )


@user_passes_test(check_super)
def payee_report_download(request, pay_id):
    pay_period = get_object_or_404(PayT, id=pay_id)
    columns = [
        "EmpNo", "Employee First_Name", "Employee Last Name",
        "Tax Number", "Gross Pay", "Payee Amount"
    ]
    data_rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__pays__emp_id", "payroll_id__pays__first_name",
        "payroll_id__pays__last_name", "payroll_id__pays__tin_no",
        "payroll_id__pays__employee_pay__basic_salary", "payroll_id__pays__employee_pay__payee"
    )
    return generate_excel_report(
        "payee_report", "PAYE Report", pay_period.paydays,
        columns, data_rows, "Total Payee", len(columns) - 1
    )


@user_passes_test(check_super)
def pension_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    dates = [utils.convert_month_to_word(str(varss)) for varss in payroll]
    return render(
        request,
        "pay/pension_reports.html",
        {
            "payroll": payroll,
            "dates": dates,
        },
    )


@user_passes_test(check_super)
def pension_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    varx = PayT.objects.filter(id=pay_id).first()
    dates = utils.convert_month_to_word(str(varx.paydays))
    pension_total = Payday.objects.filter(paydays_id_id=pay_id).aggregate(
        Sum("payroll_id__pays__employee_pay__pension")
    )
    return render(
        request,
        "pay/pension_report.html",
        {
            "payroll": payroll,
            "total": pension_total["payroll_id__pays__employee_pay__pension__sum"],
            "dates": dates,
        },
    )


@user_passes_test(check_super)
def pension_report_download(request, pay_id):
    pay_period = get_object_or_404(PayT, id=pay_id)
    columns = [
        "EmpNo", "Employee First_Name", "Employee Last Name",
        "Tax Number", "Gross Pay", "Total Pension Contribution"
    ]
    data_rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__pays__emp_id", "payroll_id__pays__first_name",
        "payroll_id__pays__last_name", "payroll_id__pays__pension_rsa",
        "payroll_id__pays__employee_pay__basic_salary", "payroll_id__pays__employee_pay__pension"
    )
    return generate_excel_report(
        "pension_report", "Pension Report", pay_period.paydays,
        columns, data_rows, "Total Pension", len(columns) - 1
    )


@user_passes_test(check_super)
def varview_download(request, paydays): # paydays here is the date string, not an ID
    pay_period = get_object_or_404(PayT, paydays=paydays)  # Get PayT object by paydays date
    columns = [
        "Employee First_Name", "Employee Last Name", "Gross Salary",
        "Water Fee", "Payee", "Pension Contribution", "Net Pay"
    ]
    # Note: The original query used paydays_id__paydays=paydays.
    # If paydays is the actual date string from URL, and PayT.paydays is the date field,
    # then the filter should be on the Payday model's relation to PayT.
    # Assuming Payday.paydays_id is the FK to PayT, and PayT.paydays is the date.
    # The filter should be on Payday objects that relate to the PayT object fetched as pay_period.
    data_rows = Payday.objects.filter(paydays_id=pay_period).values_list(
        "payroll_id__pays__first_name", "payroll_id__pays__last_name",
        "payroll_id__pays__employee_pay__basic_salary", "payroll_id__pays__employee_pay__water_rate",
        "payroll_id__pays__employee_pay__payee", "payroll_id__pays__employee_pay__pension_employee",
        "payroll_id__netpay"
    )
    return generate_excel_report(
        "payroll_report", "Payroll Report", pay_period.paydays,
        columns, data_rows, "Total Net Pay", len(columns) - 1
    )
