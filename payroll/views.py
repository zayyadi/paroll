from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView
from django.contrib import messages
from django.core.cache import cache
from django.template.loader import get_template, render_to_string
from django.http import HttpResponse
from django.core.files.storage import FileSystemStorage
from employee.models import Employee


from payroll.forms import PaydayForm, PayrollForm, VariableForm
from payroll.models import PayT, Payday, Payroll, VariableCalc

from num2words import num2words

import xhtml2pdf.pisa as pisa
from weasyprint import HTML
import xlwt


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
    payroll = Payroll.objects.all()
    payt = VariableCalc.objects.all()

    context = {
        "payroll":payroll,
        "payt": payt
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
    pay_id = VariableCalc.objects.filter(id=id).first()
    num2word = num2words(pay_id.net_pay)
    if cache.get(pay_id):
        payr = cache.get(pay_id)
        print("hit the cache")
        return payr
    else:
        payroll = VariableCalc.objects.get(id=id)
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
        # "var":pay
    }

    return render(request, "pay/var_view.html", context)

# class VarView(TemplateView):
#     template_name = 'pay/var_view.html'

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)

#         context['pay'] = PayT.objects.all()
#         context['var' ] = VariableCalc.objects.all()
#         context['pay_var'] = Payday.objects.all()

#         return context

def payslip_pdf(request, id):
    payroll = VariableCalc.objects.filter(id=id)
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
        "payroll_id__payr__employee__emp_id",
        "payroll_id__payr__employee__first_name",
        "payroll_id__payr__employee__last_name",
        "payroll_id__payr__employee__bank",
        "payroll_id__payr__employee__bank_account_number",
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
    response["Content-Disposition"] = 'attachment; filename="bank_report.xlsx"'

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Bank Report")

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
        "payroll_id__payr__employee__emp_id",
        "payroll_id__payr__employee__first_name",
        "payroll_id__payr__employee__last_name",
        "payroll_id__payr__employee__tin_no",
        "payroll_id__payr__basic_salary",
        "payroll_id__payr__payee"
    )

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)

    wb.save(response)

    return response