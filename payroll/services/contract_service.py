from __future__ import annotations
from typing import Any, Optional
from decimal import Decimal
from django.utils import timezone
from django.template.loader import render_to_string
from django.db import transaction


def generate_contract_pdf(*, contract: Any) -> str:
    try:
        from weasyprint import HTML
    except ImportError:
        from django.core.files.base import ContentFile
        file_name = f"contract_{contract.employee.emp_id}_v{contract.version}.html"
        html_bytes = render_to_string("contracts/contract_base.html", {
            "employee": contract.employee,
            "salary": contract.employee.employee_pay,
            "company": contract.employee.company,
            "contract": contract,
        }).encode("utf-8")
        contract.pdf_file.save(file_name, ContentFile(html_bytes))
        return contract.pdf_file.path

    employee = contract.employee
    salary = employee.employee_pay
    company = employee.company

    context = {
        "employee": employee,
        "salary": salary,
        "company": company,
        "contract": contract,
    }

    if contract.template and contract.template.template_html:
        from django.template import Context, Template

        tpl = Template(contract.template.template_html)
        html_string = tpl.render(Context(context))
    else:
        html_string = render_to_string("contracts/contract_base.html", context)

    pdf = HTML(string=html_string).write_pdf()

    from django.core.files.base import ContentFile
    file_name = f"contract_{employee.emp_id}_v{contract.version}.pdf"
    contract.pdf_file.save(file_name, ContentFile(pdf))
    return contract.pdf_file.path


def create_contract(
    *, employee: Any, template: Any = None, start_date: Any, end_date: Any = None
) -> Any:
    from payroll.models.employee_profile import EmploymentContract

    last = EmploymentContract.objects.filter(
        employee=employee
    ).order_by("-version").first()
    version = (last.version + 1) if last else 1

    contract = EmploymentContract.objects.create(
        company=employee.company,
        employee=employee,
        template=template,
        version=version,
        start_date=start_date,
        end_date=end_date,
        status="DRAFT",
    )
    generate_contract_pdf(contract=contract)
    return contract


def sign_contract(*, contract: Any, signed_by: Any) -> Any:
    contract.status = "SIGNED"
    contract.signed_at = timezone.now()
    contract.signed_by = signed_by
    contract.save(update_fields=["status", "signed_at", "signed_by"])
    return contract
