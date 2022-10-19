from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.views.generic import CreateView
from django.contrib import messages
from django.core.cache import cache
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.core.files.storage import FileSystemStorage

from payroll.forms import PaydayForm, PayrollForm, VariableForm, EmployeeForm
from payroll.models import EmployeeProfile, PayT, Payday, Payroll, VariableCalc, Employee

from num2words import num2words

# import xhtml2pdf.pisa as pisa
from weasyprint import HTML
import xlwt



def add_employee(request):
    form = EmployeeForm(request.POST or None)

    if form.is_valid():
        form.save()

        messages.success(request, "Added employee!")
        return redirect("payroll:index")

    return render(request, 'employee/add_employee.html', {'form': form})

def update_employee(request, id):
    employee = get_object_or_404(Employee, id=id)
    form = EmployeeForm(request.POST or None, instance=employee)

    if form.is_valid():
        form.save()
        messages.success(request, "Employee updated successfully!!")
        return redirect("payroll:index")

    else:
        form = EmployeeForm()
    
    return render(request, 'employee/update_employee.html', {'form': form})

def delete_employee(request, id):
    pay = get_object_or_404(Employee,id=id)
    pay.delete()
    messages.success(request,"Employee deleted Successfully!!")
    
def add_employee(request):
    form = EmployeeForm(request.POST or None)

    if form.is_valid():
        form.save()

        messages.success(request, "Added employee!")
        return redirect("payroll:index")

    return render(request, 'employee/add_employee.html', {'form': form})

def update_employee(request, id):
    employee = get_object_or_404(Employee, id=id)
    form = EmployeeForm(request.POST or None, instance=employee)

    if form.is_valid():
        form.save()
        messages.success(request, "Employee updated successfully!!")
        return redirect("payroll:index")

    else:
        form = EmployeeForm()
    
    return render(request, 'employee/update_employee.html', {'form': form})

def delete_employee(request, id):
    pay = get_object_or_404(Employee,id=id)
    pay.delete()
    messages.success(request,"Employee deleted Successfully!!")


def employee(request, id):
    emp = get_object_or_404(EmployeeProfile,id=id)
    pay = Payday.objects.all().filter(payroll_id_id=id)

    context = {
        "emp": emp,
        "pay":pay

    }
    return render(request,"employee/employee.html", context)

@login_required
def index(request):
    pay = PayT.objects.all()
    emp = Employee.objects.all().count()

    context = {
        "pay":pay,
        "emp": emp
    }
    return render(request, 'index.html', context)

def add_pay(request):

    form = PayrollForm(request.POST or None)

    if form.is_valid():
        form.save()
        messages.success(request,"Pay created successfully")
        return redirect("payroll:index")

    else:
        form = PayrollForm()

    return render(request, "pay/add_pay.html", {"form":form})

def delete_pay(request, id):
    pay = get_object_or_404(Payroll,id=id)
    pay.delete()
    messages.success(request,"Pay deleted Successfully!!")

def dashboard(request):
    emp = Employee.objects.all()

    context = {
        # "payroll":payroll,
        # "payt": payt
        "emp": emp
    }
    return render(request,"pay/dashboard.html", context)

def add_var(request):
    form = VariableForm(request.POST or None)

    if form.is_valid():
        form.save()
        messages.success(request, "Add Variable Pay")
        return redirect("payroll:index")

    else:
        form = VariableForm()

    return render(request, "pay/var.html", {'form': form})

def edit_var(request, id):
    var = get_object_or_404(VariableCalc, id=id)
    form = VariableForm(request.POST or None, instance=var)

    if form.is_valid():
        form.save()
        messages.success(request, "Variable updated successfully!!")
        return redirect("payroll:dashboard")

    else:
        form = VariableForm()

    context = {
        "form": form,
        "var": var,
    }
    return render(request, "pay/var.html", context)

def delete_var(request, id):
    pay = get_object_or_404(VariableCalc,id=id)
    pay.delete()
    messages.success(request,"Pay deleted Successfully!!")


class AddPay(CreateView):
    model = PayT
    form_class = PaydayForm
    template_name = 'pay/add_payday.html'
    success_url = reverse_lazy('payroll:index')

def payslip(request, id):
    pay_id = Employee.objects.filter(id=id).first()
    num2word = num2words(pay_id.net_pay)
    if cache.get(pay_id):
        payr = cache.get(pay_id)
        print("hit the cache")
        return payr
    else:
        payroll = Employee.objects.get(id=id)
        cache.set(
            id,
            payroll
        )
        print("hti the db")
    context = {
        "pay": pay_id,
        "num2words": num2word
    }
    return render(request, "pay/payslip.html", context)

def varview(request,pay_id):
    
    var = Payday.objects.filter(paydays_id_id=pay_id)
    var_total = var.aggregate(
        Sum("payroll_id__net_pay")
    )
    # var_sum = Payday.objects.filter(paydays_id_id=pay_id)
    # pay = PayT.objects.filter(is_active=True,payroll_payday=var)
#     # pay = None
    # for id in pay_id:
    # if id in var.payroll_id_id:
    #     print(pay_id)
    #     return id
#     # if pay_id:
#     #     pay = get_object_or_404(VariableCalc, var_id=pay_id)
#     #     var = PayT.objects.filter(payroll_payday__in[pay])

    context = {
        "pay_var":var,
        "var_total": var_total["payroll_id__net_pay__sum"]
    }

    return render(request, "pay/var_view.html", context)


def payslip_pdf(request, id):
    payroll = Employee.objects.filter(id=id)
    pre_total = payroll.first().net_pay
    template_path = "pay/payslip_pdf.html"
    html_string = render_to_string(
        "pay/payslip_pdf.html", {"payroll": payroll.first()}
    )
    html = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(target='/tmp/mypayslip.pdf')

    fs = FileSystemStorage("/tmp")
    with fs.open("mypayslip.pdf") as pdf:
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="mypayslip.pdf"'
        return response
    return response

def bank_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    return render(request, "pay/bank_reports.html", {"payroll": payroll})

def bank_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    return render(
        request,
        "pay/bank_report.html",
        {"payroll": payroll},
    )

def bank_report_download(request,pay_id):
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
        "payroll_id__emp_id",
        "payroll_id__first_name",
        "payroll_id__last_name",
        "payroll_id__bank",
        "payroll_id__bank_account_number",
        "payroll_id__net_pay"
    )

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)

    wb.save(response)

    return response

def payee_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    return render(request, "pay/payee_reports.html", {"payroll": payroll})

def payee_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    return render(
        request,
        "pay/payee_report.html",
        {"payroll": payroll}, 
    )

def payee_report_download(request,pay_id):
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
        "payroll_id__emp_id",
        "payroll_id__first_name",
        "payroll_id__last_name",
        "payroll_id__tin_no",
        "payroll_id__employee_pay__basic_salary",
        "payroll_id__employee_pay__payee"
    )

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)

    wb.save(response)

    return response


def pension_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    return render(request, "pay/pension_reports.html", {"payroll": payroll})

def pension_report(request, pay_id):
    payroll = Payday.objects.filter(paydays_id_id=pay_id)
    return render(
        request,
        "pay/pension_report.html",
        {"payroll": payroll}, 
    )


def pension_report_download(request,pay_id):
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
        "Pension Contribution",
    ]

    for col_num in range(len(columns)):
        ws.write(row_num, col_num, columns[col_num], font_style)

    font_style = xlwt.XFStyle()

    rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__emp_id",
        "payroll_id__first_name",
        "payroll_id__last_name",
        "payroll_id__employee_pay__basic_salary",
        # "payroll_id__payr__pension_employer",
        # "payroll_id__payr__pension_employee",
        "payroll_id__payr__pension",
    )

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)

    wb.save(response)

    return response


def varview_download(request, pay_id):

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

    rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__first_name",
        "payroll_id__last_name",
        "payroll_id__employee_pay__basic_salary",
        "payroll_id__employee_pay__water_rate",
        "payroll_id__employee_pay__payee",
        "payroll_id__employee_pay__pension_employee",
        "payroll_id__net_pay",
    )
    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)

    wb.save(response)

    return response