from django.contrib import admin

# Register your models here.
from payroll.models import Payroll, VariableCalc, PayT

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
admin.site.register(Payroll)
admin.site.register(VariableCalc)