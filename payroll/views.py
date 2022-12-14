from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.db.models import Sum
from django.views.generic import CreateView
from django.contrib import messages

# from django.core.cache import cache
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.core.files.storage import FileSystemStorage
from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.views.decorators.cache import cache_page
from accounts.forms import *

from payroll.forms import (
    AllowanceForm,
    PaydayForm,
    PayrollForm,
    EmployeeProfileForm,
)
from payroll.models import (
    EmployeeProfile,
    PayT,
    PayVar,
    Payday,
    Payroll,
    Allowance,
)


from num2words import num2words

# import xhtml2pdf.pisa as pisa
from weasyprint import HTML
import xlwt

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)


def check_super(user):
    return user.is_superuser


def index(request):
    pay = PayT.objects.all()
    pay_count = PayT.objects.all().count()
    emp = EmployeeProfile.emp_objects.all().count()

    context = {
        "pay": pay,
        "emp": emp,
        "pay_count": pay_count,
    }
    return render(request, "index.html", context)


@user_passes_test(check_super)
def add_employee(request):
    created = EmployeeProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        u_form = UserEditForm(request.POST, instance=request.user)
        e_form = EmployeeProfileForm(
            request.POST or None,
            request.FILES or None,
        )

        if u_form.is_valid and e_form.is_valid():
            e_form.save()

            messages.success(request, f"Your account has been updated!")
            return redirect("users:profile")

    else:
        # u_form = UserEditForm(instance=request.user)
        e_form = EmployeeProfileForm(instance=request.user)

    context = {"e_form": e_form}

    return render(request, "accounts/profile.html", context)


def input_id(request):
    return render(request, "pay/input.html")


@user_passes_test(check_super)
def update_employee(request, id):
    employee = get_object_or_404(EmployeeProfile, id=id)
    form = EmployeeProfileForm(request.POST or None, instance=employee)

    if form.is_valid():
        form.save()
        messages.success(request, "Employee updated successfully!!")
        return redirect("payroll:index")

    else:
        form = EmployeeProfileForm()

    return render(request, "employee/update_employee.html", {"form": form})


@user_passes_test(check_super)
def delete_employee(request, id):
    pay = get_object_or_404(EmployeeProfile, id=id)
    pay.delete()
    messages.success(request, "Employee deleted Successfully!!")


@login_required
def employee(request, user_id: int):
    try:
        user_id = request.user.id
        print(user_id)
        if user_id:
            user = get_object_or_404(EmployeeProfile, user_id=user_id)

            pay = Payday.objects.all().filter(payroll_id__pays__user_id=user_id)
            print(f"payroll_id:{pay}")
        else:
            raise Exception("You are not the owner")

    except:
        raise Exception("You re Not Authorized to view this page")

    context = {"emp": user, "pay": pay}
    return render(request, "employee/profile.html", context)

    # Start of Pay view


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
def dashboard(request):
    emp = EmployeeProfile.objects.all()

    context = {
        # "payroll":payroll,
        # "payt": payt
        "emp": emp
    }
    return render(request, "pay/dashboard.html", context)


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


@login_required
def payslip(request, id):
    pay_id = Payday.objects.filter(id=id).first()
    print(pay_id.id)
    # print(f"This is pay id : {pay_id.id}")
    num2word = num2words(pay_id.payroll_id.netpay)
    context = {"pay": pay_id, "num2words": num2word}
    return render(request, "pay/payslip.html", context)


def varview(request):

    var = PayT.objects.order_by("paydays").distinct("paydays")

    context = {
        "pay_var": var,
    }

    return render(request, "pay/var_view.html", context)


@user_passes_test(check_super)
def varview_report(request, paydays):
    var = Payday.objects.filter(paydays_id__paydays=paydays)
    paydays_total = Payday.objects.filter(paydays_id__paydays=paydays).aggregate(
        Sum("payroll_id__netpay")
    )

    context = {
        "pay_var": var,
        "paydays": paydays,
        "total": paydays_total["payroll_id__netpay__sum"],
    }
    return render(request, "pay/var_report.html", context)


def payslip_pdf(request, id):
    payroll = PayVar.objects.filter(id=id)
    pre_total = payroll.first().netpay
    template_path = "pay/payslip_pdf.html"
    html_string = render_to_string("pay/payslip_pdf.html", {"payroll": payroll.first()})
    html = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(
        target=f"/tmp/{payroll.first().pays.first_name}mypayslip.pdf"
    )

    fs = FileSystemStorage("/tmp")
    with fs.open("mypayslip.pdf") as pdf:
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="mypayslip.pdf"'
        return response
    return response


@user_passes_test(check_super)
def bank_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    return render(request, "pay/bank_reports.html", {"payroll": payroll})


@user_passes_test(check_super)
def bank_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    return render(
        request,
        "pay/bank_report.html",
        {"payroll": payroll},
    )


@user_passes_test(check_super)
def bank_report_download(request, pay_id):
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = 'attachment; filename="bank_report.xlsx"'

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Bank Report")

    row_num = 0

    font_style = xlwt.XFStyle()
    font_style.font.bold = True

    columns = [
        "EmpNo",
        "Emp First_Name",
        "Last Name",
        "Bank Name",
        "Account No.",
        "Net Pay",
    ]

    for col_num in range(len(columns)):
        ws.write(row_num, col_num, columns[col_num], font_style)

    font_style = xlwt.XFStyle()

    rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__pays__emp_id",
        "payroll_id__pays__first_name",
        "payroll_id__pays__last_name",
        "payroll_id__pays__bank",
        "payroll_id__pays__bank_account_number",
        "payroll_id__netpay",
    )

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)

    wb.save(response)

    return response


@user_passes_test(check_super)
def payee_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    return render(request, "pay/payee_reports.html", {"payroll": payroll})


@user_passes_test(check_super)
def payee_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    return render(
        request,
        "pay/payee_report.html",
        {"payroll": payroll},
    )


@user_passes_test(check_super)
def payee_report_download(request, pay_id):
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = 'attachment; filename="payee_report.xlsx"'

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Payee Report")

    row_num = 0

    font_style = xlwt.XFStyle()
    font_style.font.bold = True

    columns = [
        "EmpNo",
        "Employee First_Name",
        "Employee Last Name",
        "Tax Number",
        "Gross Pay",
        "Payee Amount",
    ]

    for col_num in range(len(columns)):
        ws.write(row_num, col_num, columns[col_num], font_style)

    font_style = xlwt.XFStyle()

    rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__pays__emp_id",
        "payroll_id__pays__first_name",
        "payroll_id__pays__last_name",
        "payroll_id__pays__tin_no",
        "payroll_id__pays__employee_pay__basic_salary",
        "payroll_id__pays__employee_pay__payee",
    )

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)

    wb.save(response)

    return response


@user_passes_test(check_super)
def pension_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    return render(request, "pay/pension_reports.html", {"payroll": payroll})


@user_passes_test(check_super)
def pension_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    return render(
        request,
        "pay/pension_report.html",
        {"payroll": payroll},
    )


@user_passes_test(check_super)
def pension_report_download(request, pay_id):
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = 'attachment; filename="pension_report.xlsx"'

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Pension Report")

    row_num = 0

    font_style = xlwt.XFStyle()
    font_style.font.bold = True

    columns = [
        "EmpNo",
        "Employee First_Name",
        "Employee Last Name",
        "Tax Number",
        "Gross Pay",
        "Employee Pension Contribution",
        "Employer Pension Contribution",
    ]

    for col_num in range(len(columns)):
        ws.write(row_num, col_num, columns[col_num], font_style)

    font_style = xlwt.XFStyle()

    rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__pays__emp_id",
        "payroll_id__pays__first_name",
        "payroll_id__pays__last_name",
        "payroll_id__pays__employee_pay__basic_salary",
        "payroll_id__payr__pension_employer",
        "payroll_id__payr__pension_employee",
        # "payroll_id__pays__employee_pay__pension",
    )

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)

    wb.save(response)

    return response


@user_passes_test(check_super)
def varview_download(request, paydays):

    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = 'attachment; filename="payroll_report.xlsx"'

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Payroll Report")

    row_num = 0

    font_style = xlwt.XFStyle()
    font_style.font.bold = True

    columns = [
        "Employee First_Name",
        "Employee Last Name",
        "Gross Salary",
        "Water Fee",
        "Payee",
        "Pension Contribution",
        "Net Pay",
    ]

    for col_num in range(len(columns)):
        ws.write(row_num, col_num, columns[col_num], font_style)

    font_style = xlwt.XFStyle()

    rows = Payday.objects.filter(paydays_id__paydays=paydays).values_list(
        "payroll_id__pays__first_name",
        "payroll_id__pays__last_name",
        "payroll_id__pays__employee_pay__basic_salary",
        "payroll_id__pays__employee_pay__water_rate",
        "payroll_id__pays__employee_pay__payee",
        "payroll_id__pays__employee_pay__pension_employee",
        "payroll_id__netpay",
    )
    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)

    wb.save(response)

    return response


@user_passes_test(check_super)
def create_allowance(request):
    form = AllowanceForm(request.POST or None)

    if form.is_valid():
        form.save()
        messages.success(request, "Allowance created successfully")
        return redirect("payroll:index")

    else:
        form = PayrollForm()

    return render(request, "pay/add_allowance.html", {"form": form})
