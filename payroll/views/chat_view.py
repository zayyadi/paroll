from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from company.utils import get_user_company
from payroll import models
from payroll.services.chat_service import get_company_chat_room


@login_required
def company_chat(request):
    company = get_user_company(request.user)
    employee = getattr(request.user, "employee_user", None)

    if company is None or employee is None or employee.company_id != company.id:
        messages.error(
            request,
            "Your account needs an employee profile in the active company before chat is available.",
        )
        return redirect("payroll:dashboard")

    room = get_company_chat_room(company)
    context = {
        "chat_room": room,
        "chat_employee_id": employee.id,
        "chat_member_count": models.EmployeeProfile.objects.filter(company=company, status="active").count(),
        "chat_default_room_id": room.id,
    }
    return render(request, "employee/company_chat.html", context)
