from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView
from django.contrib import messages
from django.core.cache import cache
from django.template.loader import get_template, render_to_string
from django.http import HttpResponse
from django.core.files.storage import FileSystemStorage


from payroll.forms import PaydayForm, PayrollForm, VariableForm
from payroll.models import PayT, Payday, Payroll, VariableCalc

from num2words import num2words

import xhtml2pdf.pisa as pisa
from weasyprint import HTML


def index(request):
    ...
    return render(request, 'index.html')

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