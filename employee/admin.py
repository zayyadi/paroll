from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

# Register your models here.
from employee.models import Employee

class EmployeeResources(resources.ModelResource):
    class Meta:
        model = Employee


admin.site.register(Employee, ImportExportModelAdmin)
