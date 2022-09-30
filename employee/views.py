from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from employee.forms import EmployeeForm
from employee.models import Employee


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
