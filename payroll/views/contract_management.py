from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import FileResponse

from company.utils import get_user_company
from payroll.models import EmployeeProfile
from payroll.models.employee_profile import ContractTemplate, EmploymentContract
from payroll.services.contract_service import (
    create_contract,
    generate_contract_pdf,
    sign_contract,
)


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def contract_template_list(request):
    company = get_user_company(request.user)
    templates = ContractTemplate.objects.filter(company=company)
    return render(request, "employee/contract_template_list.html", {
        "templates": templates,
        "page_title": "Contract Templates",
    })


@login_required
@permission_required("payroll.add_employeeprofile", raise_exception=True)
def contract_template_create(request):
    company = get_user_company(request.user)

    if request.method == "POST":
        name = request.POST.get("name")
        template_html = request.POST.get("template_html", "")
        ContractTemplate.objects.create(
            company=company,
            name=name,
            template_html=template_html,
        )
        messages.success(request, f"Template '{name}' created.")
        return redirect("payroll:contract_template_list")

    return render(request, "employee/contract_template_form.html", {
        "page_title": "Create Contract Template",
    })


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def contract_list(request):
    company = get_user_company(request.user)
    contracts = EmploymentContract.objects.filter(
        company=company
    ).select_related("employee", "template", "signed_by")
    return render(request, "employee/contract_list.html", {
        "contracts": contracts,
        "page_title": "Employment Contracts",
    })


@login_required
@permission_required("payroll.add_employeeprofile", raise_exception=True)
def contract_generate(request):
    company = get_user_company(request.user)
    employees = EmployeeProfile.objects.filter(company=company, status="active")
    templates = ContractTemplate.objects.filter(company=company, is_active=True)

    if request.method == "POST":
        employee_id = request.POST.get("employee")
        template_id = request.POST.get("template")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date") or None

        employee = get_object_or_404(EmployeeProfile, id=employee_id, company=company)
        template = get_object_or_404(ContractTemplate, id=template_id, company=company) if template_id else None

        try:
            contract = create_contract(
                employee=employee,
                template=template,
                start_date=start_date,
                end_date=end_date,
            )
            messages.success(request, f"Contract generated for {employee}.")
            return redirect("payroll:contract_detail", pk=contract.pk)
        except Exception as e:
            messages.error(request, f"Error generating contract: {e}")

    return render(request, "employee/contract_generate.html", {
        "employees": employees,
        "templates": templates,
        "page_title": "Generate Contract",
    })


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def contract_detail(request, pk):
    company = get_user_company(request.user)
    contract = get_object_or_404(
        EmploymentContract.objects.select_related("employee", "template", "signed_by"),
        pk=pk, company=company,
    )
    return render(request, "employee/contract_detail.html", {
        "contract": contract,
        "page_title": f"Contract - {contract.employee}",
    })


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)
def contract_download(request, pk):
    company = get_user_company(request.user)
    contract = get_object_or_404(EmploymentContract, pk=pk, company=company)

    if not contract.pdf_file:
        messages.error(request, "PDF not available.")
        return redirect("payroll:contract_detail", pk=pk)

    return FileResponse(
        contract.pdf_file.open("rb"),
        as_attachment=True,
        filename=f"contract_{contract.employee.emp_id}_v{contract.version}.pdf",
    )


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def contract_sign(request, pk):
    company = get_user_company(request.user)
    contract = get_object_or_404(EmploymentContract, pk=pk, company=company)

    if request.method == "POST":
        sign_contract(contract=contract, signed_by=request.user)
        messages.success(request, "Contract signed successfully.")

    return redirect("payroll:contract_detail", pk=pk)


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def contract_regenerate(request, pk):
    company = get_user_company(request.user)
    contract = get_object_or_404(EmploymentContract, pk=pk, company=company)

    if request.method == "POST":
        try:
            generate_contract_pdf(contract=contract)
            messages.success(request, "Contract PDF regenerated.")
        except Exception as e:
            messages.error(request, f"Error: {e}")

    return redirect("payroll:contract_detail", pk=pk)
