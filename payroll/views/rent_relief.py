"""Rent relief: employee declarations and HR review."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from company.utils import get_user_company
from payroll import models
from payroll.forms import RentDeclarationForm
from payroll.services.rent_relief import review_declaration

__all__ = ["my_rent_declarations", "rent_declaration_review", "decide_rent_declaration"]


@login_required
def my_rent_declarations(request):
    company = get_user_company(request.user)
    employee = get_object_or_404(models.EmployeeProfile, user=request.user, company=company)
    form = RentDeclarationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        if employee.rent_declarations.filter(
            tax_year=form.cleaned_data["tax_year"],
            status=models.RentDeclaration.Status.PENDING,
        ).exists():
            form.add_error("tax_year", "You already have a declaration awaiting review for this year.")
        else:
            declaration = form.save(commit=False)
            declaration.company = company
            declaration.employee = employee
            declaration.save()
            messages.success(request, "Rent declaration submitted for HR review.")
            return redirect("payroll:my_rent_declarations")

    return render(
        request,
        "employee/my_rent_declarations.html",
        {
            "page_title": "Rent Relief",
            "form": form,
            "declarations": employee.rent_declarations.all(),
            "current_relief": employee.rent_relief_amount,
        },
    )


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
def rent_declaration_review(request):
    company = get_user_company(request.user)
    declarations = models.RentDeclaration.objects.filter(company=company).select_related(
        "employee", "reviewed_by"
    )
    return render(
        request,
        "employee/rent_declaration_review.html",
        {
            "page_title": "Rent Declarations",
            "pending": declarations.filter(status=models.RentDeclaration.Status.PENDING),
            "decided": declarations.exclude(status=models.RentDeclaration.Status.PENDING)[:50],
        },
    )


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)
@require_POST
def decide_rent_declaration(request, pk):
    company = get_user_company(request.user)
    declaration = get_object_or_404(models.RentDeclaration, pk=pk, company=company)
    approve = request.POST.get("decision") == "approve"
    try:
        review_declaration(
            declaration=declaration,
            reviewer=request.user,
            approve=approve,
            note=request.POST.get("note", ""),
        )
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
    else:
        messages.success(request, "Rent declaration approved." if approve else "Rent declaration rejected.")
    return redirect("payroll:rent_declaration_review")
