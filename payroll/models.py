from decimal import Decimal
from django.db import models

from payroll.utils import *
from employee.models import Employee
from monthyear.models import MonthField

from autoslug import AutoSlugField

# class PayDay(models.Model):
#     name = models.CharField(max_length=255, unique=True)
#     date = models.DateField()

class Payroll(models.Model):
    employee = models.ForeignKey(Employee, related_name='employee_payroll', on_delete=models.CASCADE)
    
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, null=False, blank=False)
    basic = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    housing = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    transport = models.DecimalField(max_digits=12, default=0.0,decimal_places=2, blank=True)
    bht = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    pension_employee = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    pension_employer = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    pension = models.DecimalField(max_digits=12, default=0.0,decimal_places=2, blank=True)
    gross_income = models.DecimalField(max_digits=12, default=0.0,decimal_places=2, blank=True)
    consolidated_relief = models.DecimalField(max_digits=12, default=0.0,decimal_places=2, blank=True)
    taxable_income = models.DecimalField(max_digits=12, default=0.0,decimal_places=2, blank=True)
    payee = models.DecimalField(max_digits=12,decimal_places=2, blank=True)
    
    water_rate = models.DecimalField(max_digits=12, default=200.0,decimal_places=2, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True) 
    updated = models.DateTimeField(auto_now=True) 
    active = models.BooleanField(default=True)

    def __str__(self):
        # print(self.basic_salary)

        # # print(first_taxable(self))
        # print(f"tax:{second_taxable(self)}")
        # print(third_taxable(self))
        # print(fourth_taxable(self))
        # print(fifth_taxable(self))
        # print(sixth_taxable(self))
        # print(seventh_taxable(self))
        return f"employee {self.employee.first_name} {self.employee.last_name} payroll"

    @property
    def get_gross_income(self):
        return (self.basic_salary *12) - (get_pension_employee(self)*12)

    @property
    def calculate_taxable_income(self) -> Decimal:
        calc= (
            (self.get_gross_income)
            - (get_consolidated_relief(self))
            
        )
        if calc <=0.0:
            return 0.0
        return calc

    @property
    def get_name(self):
        return self.employee.first_name

    
    
    def save(self, *args, **kwargs):
        self.name = self.get_name
        self.basic = get_basic(self)
        self.housing = get_housing(self)
        self.transport = get_transport(self)
        self.bht = get_bht(self)
        self.pension_employee = get_pension_employee(self)
        self.pension_employer = get_pension_employer(self)
        self.pension = get_pension(self)
        self.gross_income = self.get_gross_income
        self.consolidated_relief = get_consolidated_relief(self)
        self.taxable_income = self.calculate_taxable_income
        self.payee = get_payee(self)
        self.water_rate = get_water_rate(self)

        super(Payroll, self).save(*args, **kwargs)


class VariableCalc(models.Model):
    payr = models.ForeignKey(Payroll, on_delete=models.CASCADE, related_name='variable_payroll')
    is_leave = models.BooleanField(default=False)
    is_overtime = models.BooleanField(default=False)
    is_absent = models.BooleanField(default=False)
    is_late = models.BooleanField(default=False)
    leave_allowance = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    lateness = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    overtime = models.DecimalField(max_digits=12, decimal_places=2,blank=True)
    absent = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    damage = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    net_pay = models.DecimalField(max_digits=12, default=0.0,decimal_places=2,blank=True)

    class Meta:
        verbose_name_plural = "Payroll Variable"

    def __str__(self):
        return f"{self.payr.employee.first_name} - netpay: #{self.net_pay:,.2f}"
    
    @property
    def get_leave_allowance(self):
        if self.is_leave:
            return (self.payr.basic_salary * 12) * Decimal(3.6) / 100
        return 0.0

    @property
    def get_overtime(self):
        if self.is_overtime:
            return 1000
        return 0.0

    @property
    def get_late(self):
        if self.is_late:
            return self.payr.basic_salary * Decimal(0.05) / 100
        return 0
    
    @property
    def get_absent(self):
        if self.is_late:
            return self.payr.basic_salary * Decimal(0.5) / 100
        return 0
    
    @property
    def get_damage(self):
        if self.is_late:
            return self.payr.basic_salary * 10 / 100
        return 0


    def save(self, *args, **kwargs):
        self.leave_allowance = self.get_leave_allowance
        self.overtime = self.get_overtime
        self.lateness = self.get_late
        self.absent = self.get_absent
        self.damage = self.get_damage
        # self.total_net_pay = self.get_total_netpay
        self.net_pay = get_net_pay(self)
        super(VariableCalc, self).save(*args, **kwargs)

class PayT(models.Model):
    class PayTManager(models.Model):
        def get_queryset(self):
            return super().get_queryset().filter(is_active=True)
    name = models.CharField(max_length=50, unique=True, default="test")
    slug = AutoSlugField(populate_from="name",editable=True,always_update=True)
    paydays = MonthField("Month Value", help_text="some help...", null=True)
    # month = MonthField()
    payroll_payday= models.ManyToManyField(VariableCalc, related_name="payroll_payday", through='Payday')
    is_active = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = "PayTs"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("payroll:payslip",args=[self.slug])

    def __str__(self):
        return str(self.paydays)

class Payday(models.Model):
    paydays_id = models.ForeignKey(PayT, on_delete=models.CASCADE, related_name="pay")
    payroll_id = models.ForeignKey(VariableCalc, on_delete=models.CASCADE, related_name="payroll_paydays")