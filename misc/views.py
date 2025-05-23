from typing import Any
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse_lazy
from django.db.models import Sum, Q, Count
from django.views.generic import CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages

# from django.core.cache import cache
from django.template.loader import render_to_string
from django.http import HttpResponse, HttpResponseForbidden

# from django.core.files.storage import FileSystemStorage
from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT

# from django.views.decorators.cache import cache_page
from users import forms as user_forms

from payroll.forms import (
    AllowanceForm,
    IOUApprovalForm,
    IOURequestForm,
    LeaveRequestForm,
    PaydayForm,
    PayrollForm,
    EmployeeProfileForm,
)
from payroll.models import (
    IOU,
    Department,
    EmployeeProfile,
    LeavePolicy,
    LeaveRequest,
    PayT,
    PayVar,
    Payday,
    Payroll,
    Allowance,
    PerformanceReview,
    AuditTrail,
)
from payroll import utils


from num2words import num2words

# import xhtml2pdf.pisa as pisa
from weasyprint import HTML
import xlwt

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)


def check_super(user):
    return user.is_superuser


@login_required
def index(request):
    pay = PayT.objects.all()
    pay_count = PayT.objects.all().count()
    emp = EmployeeProfile.emp_objects.all()
    count = emp.count()

    context = {
        "pay": pay,
        "emp": emp,
        "count": count,
        "pay_count": pay_count,
    }

    if request.user.is_superuser:
        return render(request, "index.html", context)
    else:
        try:
            employee_profile = EmployeeProfile.emp_objects.get(user=request.user)
            context["employee_slug"] = employee_profile.slug
            print(f"employee slug: {context['employee_slug']}")
        except EmployeeProfile.DoesNotExist:
            context["employee_slug"] = None
            print(f"employee slug: {context['employee_slug']}")

        return render(request, "home_normal.html", context)


def hr_dashboard(request):
    total_employees = EmployeeProfile.objects.count()
    active_leave_requests = LeaveRequest.objects.filter(status="PENDING").count()
    recent_performance_reviews = PerformanceReview.objects.all().order_by(
        "-review_date"
    )[:5]

    # Employee Distribution by Department
    department_distribution = EmployeeProfile.objects.values(
        "department__name"
    ).annotate(count=Count("id"))
    department_labels = [item["department__name"] for item in department_distribution]
    department_counts = [item["count"] for item in department_distribution]

    # Leave Requests by Status
    leave_status_counts = [
        LeaveRequest.objects.filter(status="PENDING").count(),
        LeaveRequest.objects.filter(status="APPROVED").count(),
        LeaveRequest.objects.filter(status="REJECTED").count(),
    ]

    context = {
        "total_employees": total_employees,
        "active_leave_requests": active_leave_requests,
        "recent_performance_reviews": recent_performance_reviews,
        "department_labels": department_labels,
        "department_counts": department_counts,
        "leave_status_counts": leave_status_counts,
    }
    return render(request, "employee/dashboard.html", context)


def employee_list(request):
    query = request.GET.get("q")
    department_filter = request.GET.get("department")
    employees = EmployeeProfile.objects.all()

    if query:
        employees = employees.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(job_title__icontains=query)
        )

    if department_filter:
        employees = employees.filter(department__id=department_filter)

    departments = Department.objects.all()
    return render(
        request,
        "employee/employee_list.html",
        {"employees": employees, "departments": departments},
    )


def performance_reviews(request):
    query = request.GET.get("q")
    reviews = PerformanceReview.objects.all()

    if query:
        reviews = reviews.filter(
            Q(employee__user__first_name__icontains=query)
            | Q(employee__user__last_name__icontains=query)
            | Q(comments__icontains=query)
        )

    return render(request, "employee/performance_reviews.html", {"reviews": reviews})


@user_passes_test(check_super)
@login_required
def add_employee(request):
    # created = EmployeeProfile.objects.get_or_create(user=request.user)  # noqa: F841
    if request.method == "POST":
        u_form = user_forms.CustomUserChangeForm(request.POST, instance=request.user)
        e_form = EmployeeProfileForm(
            request.POST or None,
            request.FILES or None,
        )

        if u_form.is_valid and e_form.is_valid():
            e_form.save()

            messages.success(request, f"Your account has been updated!")  # noqa: F541
            return redirect("payroll:index")

    else:
        # u_form = UserEditForm(instance=request.user)
        e_form = EmployeeProfileForm(instance=request.user)

    context = {
        "e_form": e_form,
        # "u_form": u_form,
    }

    return render(request, "employee/add_employee.html", context)


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


class EmployeeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = EmployeeProfile
    form_class = EmployeeProfileForm
    template_name = "employee/add.html"
    success_url = reverse_lazy("payroll:employee_list")

    def form_valid(self, form):
        messages.success(self.request, "Employee created successfully.")
        return super().form_valid(form)

    def test_func(self):
        return check_super(self.request.user)


class EmployeeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = EmployeeProfile
    form_class = EmployeeProfileForm
    template_name = "employee/update.html"
    success_url = reverse_lazy("payroll:employee_list")

    def form_valid(self, form):
        messages.success(self.request, "Employee updated successfully.")
        return super().form_valid(form)

    def test_func(self):
        return check_super(self.request.user)


class EmployeeDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = EmployeeProfile
    template_name = "employee/delete.html"
    success_url = reverse_lazy("payroll:employee_list")

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Employee deleted successfully.")
        return super().delete(request, *args, **kwargs)

    def test_func(self):
        return check_super(self.request.user)


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

    except Exception as e:
        raise (e, "You re Not Authorized to view this page")

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
@login_required
@user_passes_test(check_super)
def dashboard(request):
    emp = EmployeeProfile.objects.all()

    context = {
        # "payroll":payroll,
        # "payt": payt
        "emp": emp
    }
    return render(request, "pay/dashboard.html", context)


@login_required
def list_payslip(request, emp_slug):
    emp = EmployeeProfile.objects.filter(slug=emp_slug).first()
    pay = Payday.objects.filter(payroll_id__pays__slug=emp_slug).all()
    paydays = Payday.objects.filter(payroll_id__pays__slug=emp_slug).values_list(
        "paydays_id__paydays", flat=True
    )
    conv_date = [utils.convert_month_to_word(str(payday)) for payday in paydays]

    context = {
        "emp": emp,
        "pay": pay,
        "dates": conv_date,
    }

    return render(request, "pay/list_payslip.html", context)


def create_allowance(request):
    a_form = AllowanceForm(request.POST or None)

    if a_form.is_valid():
        a_form.save()
        messages.success(request, "Pay created successfully")
        return redirect("payroll:index")

    else:
        a_form = AllowanceForm()

    return render(request, "pay/add_allowance.html", {"form": a_form})


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

    def get(self, request, *args, **kwargs):
        form = PaydayForm()  # Create an instance of your form
        return render(request, self.template_name, {"form": form})

    def post(self, request, **kwargs: Any) -> dict[str, Any]:
        form = PaydayForm(request.POST or None)

        if request.POST and form.is_valid():
            name = form.cleaned_data["name"]
            slug = form.cleaned_data["slug"]
            paydays = form.cleaned_data["paydays"]
            is_active = form.cleaned_data["is_active"]

            obj = PayT(
                name=name,
                slug=slug,
                paydays=paydays,
                is_active=is_active,
            )

            obj.save()
            forms = PaydayForm(request.POST, instance=obj)
            forms.save(commit=False)
            forms.save_m2m()
            messages.success(request, "Variable updated successfully!!")
            return redirect("payroll:dashboard")

        else:
            form = PaydayForm()
            return render(request, self.template_name, {"form": form})


@login_required
def payslip(request, id):
    pay_id = Payday.objects.filter(id=id).first()
    # print(pay_id)
    # print(f"This is pay id : {pay_id.id}")
    num2word = num2words(pay_id.payroll_id.netpay)
    dates = utils.convert_month_to_word(str(pay_id.paydays_id.paydays))
    context = {
        "pay": pay_id,
        "num2words": num2word,
        "dates": dates,
    }
    return render(request, "pay/payslip.html", context)


def varview(request):
    var = PayT.objects.order_by("paydays").distinct("paydays")
    dates = [utils.convert_month_to_word(str(varss)) for varss in var]

    context = {
        "pay_var": var,
        "dates": dates,
    }

    return render(request, "pay/var_view.html", context)


@user_passes_test(check_super)
def varview_report(request, paydays):
    var = Payday.objects.filter(paydays_id__paydays=paydays)
    varx = PayT.objects.filter(paydays=paydays).first()
    # print(f"dates var: {varx}")
    dates = utils.convert_month_to_word(str(varx))
    # print(f"stringified dates: {dates}")
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


def payslip_pdf(request, id):
    payroll = PayVar.objects.filter(pays_id=id)
    pre_total = payroll.first().netpay  # noqa: F841
    template_path = "pay/payslip_pdf.html"
    html_string = render_to_string(template_path, {"payroll": payroll.first()})

    pdf_file_path = f"/tmp/{payroll.first().pays.first_name}-mypayslip.pdf"

    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    html.write_pdf(target=pdf_file_path)

    with open(pdf_file_path, "rb") as pdf_file:
        response = HttpResponse(pdf_file.read(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{payroll.first().pays.first_name}-mypayslip.pdf"'
        )
        return response
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
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = 'attachment; filename="bank_report.xlsx"'

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Bank Report")

    row_num = 0

    font_style = xlwt.XFStyle()
    font_style.font.bold = True

    columns = [
        "Employee No",
        "Employee First Name",
        "Employee Last Name",
        "Employee Bank Name",
        "Employee Bank Account Name",
        "Employee Bank Account No.",
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
        "payroll_id__pays__bank_account_name",
        "payroll_id__pays__bank_account_number",
        "payroll_id__netpay",
    )

    total_netpay = 0

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)
        total_netpay += row[-1]

    # Write total netpay
    row_num += 1
    ws.write(row_num, 0, "Total Net Pay", font_style)
    ws.write(row_num, len(columns) - 1, total_netpay, font_style)

    wb.save(response)
    return response


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
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = (
        'attachment; filename=health_insurance_report.xlsx"'
    )

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
        "Health insurane payment",
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
        "payroll_id__health",
    )

    total_nhis = 0

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)
        total_nhis += row[-1]

    # Write total netpay
    row_num += 1
    ws.write(row_num, 0, "Total NHIS payment", font_style)
    ws.write(row_num, len(columns) - 1, total_nhis, font_style)

    wb.save(response)

    return response


@user_passes_test(check_super)
def nhf_reports(request):
    payroll = PayT.objects.order_by("paydays").distinct("paydays")
    dates = [utils.convert_month_to_word(str(varss)) for varss in payroll]
    return render(
        request, "pay/nhis_reports.html", {"payroll": payroll, "dates": dates}
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
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = 'attachment; filename=nhf_report.xlsx"'

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
        "National Housing Fund payment",
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
        "payroll_id__housing",
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
    pension_total = Payday.objects.filter(paydays_id_id=pay_id).aggregate(
        Sum("payroll_id__pays__employee_pay__payee")
    )
    return render(
        request,
        "pay/payee_report.html",
        {
            "payroll": payroll,
            "total": pension_total["payroll_id__pays__employee_pay__payee__sum"],
            "dates": dates,
        },
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

    total_payee = 0

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)
        total_payee += row[-1]

    # Write total netpay
    row_num += 1
    ws.write(row_num, 0, "Total Payee", font_style)
    ws.write(row_num, len(columns) - 1, total_payee, font_style)

    wb.save(response)

    return response


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
        "Total Pension Contribution",
    ]

    for col_num in range(len(columns)):
        ws.write(row_num, col_num, columns[col_num], font_style)

    font_style = xlwt.XFStyle()

    rows = Payday.objects.filter(paydays_id_id=pay_id).values_list(
        "payroll_id__pays__emp_id",
        "payroll_id__pays__first_name",
        "payroll_id__pays__last_name",
        "payroll_id__pays__pension_rsa",
        "payroll_id__pays__employee_pay__basic_salary",
        "payroll_id__pays__employee_pay__pension",
    )

    total_pension = 0

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)
        total_pension += row[-1]

    # Write total netpay
    row_num += 1
    ws.write(row_num, 0, "Total Pension", font_style)
    ws.write(row_num, len(columns) - 1, total_pension, font_style)

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
    total_netpay = 0

    for row in rows:
        row_num += 1
        for col_num in range(len(row)):
            ws.write(row_num, col_num, row[col_num], font_style)
        total_netpay += row[-1]

    # Write total netpay
    row_num += 1
    ws.write(row_num, 0, "Total Net Pay", font_style)
    ws.write(row_num, len(columns) - 1, total_netpay, font_style)

    wb.save(response)

    return response


@login_required
@permission_required("leave.add_leaverequest", raise_exception=True)
def apply_leave(request):
    if request.method == "POST":
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = request.user
            leave_request.save()
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm()
    return render(request, "employee/apply_leave.html", {"form": form})


@login_required
def leave_requests(request):
    requests = LeaveRequest.objects.filter(employee=request.user)
    return render(request, "employee/leave_requests.html", {"requests": requests})


@login_required
@permission_required("change_leaverequest", raise_exception=True)
def manage_leave_requests(request):

    requests = LeaveRequest.objects.filter(status="PENDING")
    return render(
        request, "employee/manage_leave_requests.html", {"requests": requests}
    )


@login_required
@permission_required("change_leaverequest", raise_exception=True)
def approve_leave(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    leave_request.status = "APPROVED"
    leave_request.save()
    return redirect("payroll:manage_leave_requests")


@login_required
@permission_required("change_leaverequest", raise_exception=True)
def reject_leave(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    leave_request.status = "REJECTED"
    leave_request.save()
    return redirect("payroll:manage_leave_requests")


@login_required
def leave_policies(request):
    policies = LeavePolicy.objects.all()
    return render(request, "employee/leave_policies.html", {"policies": policies})


def edit_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if request.method == "POST":
        form = LeaveRequestForm(request.POST, instance=leave_request)
        if form.is_valid():
            form.save()
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm(instance=leave_request)
    return render(request, "employee/edit_leave_request.html", {"form": form})


def delete_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    leave_request.delete()
    return redirect("payroll:leave_requests")


def view_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    return render(
        request, "employee/view_leave_request.html", {"leave_request": leave_request}
    )


@login_required
def request_iou(request):
    if request.method == "POST":
        form = IOURequestForm(request.POST)
        if form.is_valid():
            iou = form.save(commit=False)
            if hasattr(request.user, "employee_profile"):
                iou.employee_id = request.user.employee_profile
                iou.save()
                return redirect("iou_history")
            else:
                # Handle the case where the user doesn't have an employee profile
                form.add_error(
                    None, "User does not have an associated employee profile."
                )
    else:
        form = IOURequestForm()
    return render(request, "iou/request_iou.html", {"form": form})


@login_required
def approve_iou(request, iou_id):
    iou = get_object_or_404(IOU, id=iou_id)
    if not request.user.is_staff:  # Only staff can approve IOUs
        return HttpResponseForbidden("You do not have permission to approve IOUs.")

    if request.method == "POST":
        form = IOUApprovalForm(request.POST, instance=iou)
        if form.is_valid():
            form.save()
            return redirect("iou_history")
    else:
        form = IOUApprovalForm(instance=iou)
    return render(request, "iou/approve_iou.html", {"form": form, "iou": iou})


@login_required
def iou_history(request):
    if request.user.is_staff:  # Managers can view all IOUs
        ious = IOU.objects.all()
    else:  # Employees can only view their own IOUs
        if hasattr(request.user, "employee_profile"):
            ious = IOU.objects.filter(employee_id=request.user.employee_profile)
        else:
            ious = IOU.objects.none()  # Return an empty queryset if no profile exists
    return render(request, "iou/iou_history.html", {"ious": ious})


def log_audit_trail(user, action, content_object):
    AuditTrail.objects.create(
        user=user,
        action=action,
        content_object=content_object,
    )


@login_required
def restore_employee(request, id):
    employee = get_object_or_404(EmployeeProfile, id=id, deleted_at__isnull=False)
    employee.restore()
    log_audit_trail(request.user, "restore", employee)
    messages.success(request, "Employee restored successfully!")
    return redirect("payroll:employee_list")
