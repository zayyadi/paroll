from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

# Register your models here.
from payroll.models import EmployeeProfile, Payroll, VariableCalc, PayT, Employee


class EmployeeResources(resources.ModelResource):
    class Meta:
        model = Employee
        
class EmployeeProfileResources(resources.ModelResource):
    class Meta:
        model = EmployeeProfile


class PayrollResource(resources.ModelResource):
    class Meta:
        model = Payroll

class VarResource(resources.ModelResource):
    class Meta:
        model = Payroll
        
class PayResource(resources.ModelResource):
    class Meta:
        model = PayT

class PayrollInline(admin.StackedInline):
    model= PayT.payroll_payday.through
    extra= 4
    raw_id_fields = ('payroll_id',)
    # readonly_fields = ['net_pay']

class PayrollAdmin(admin.ModelAdmin):
    model = PayT
    inlines = (PayrollInline,)
    list_display = ['paydays']
    # readonly_fields = ['timestamp', 'updated']
    # raw_id_fields = ['payday']


admin.site.register(PayT, PayrollAdmin)
admin.site.register(Employee, ImportExportModelAdmin)
admin.site.register(EmployeeProfile, ImportExportModelAdmin)
admin.site.register(Payroll, ImportExportModelAdmin)
# admin.site.register(PayT, ImportExportModelAdmin)
admin.site.register(VariableCalc, ImportExportModelAdmin)