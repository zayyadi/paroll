from decimal import Decimal

from django.db import models
from django.core.validators import RegexValidator
from django.db.models import Q
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import RegexValidator

from autoslug import AutoSlugField

from payroll.generator import emp_id, nin_no, tin_no
from payroll.utils import *
from payroll.choices import *

from monthyear.models import MonthField

class Employee(models.Model):
    emp_id = models.CharField(default=emp_id, unique = True, max_length=255, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="employee_user")
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, unique=True)
    created = models.DateTimeField(default=timezone.now, blank=False)

    class Meta:
        ordering = ["-created"]

    # def __str__(self):
    #     return self.first_na

class EmployeeQuerySet(models.QuerySet):
    def search(self, query=None):
        if query is None or query == "":
            return self.none()
        lookups = (
            Q(first_name__icontains=query) | 
            Q(email__icontains=query) 
        )
        return self.filter(lookups)

class EmployeeManager(models.Manager):
    def get_queryset(self):
        return EmployeeQuerySet(self.model, using=self._db)

    def search(self, query=None):
        return self.get_queryset().search(query=query)


class EmployeeProfile(models.Model):
    employee = models.OneToOneField(Employee, related_name="employee", on_delete=models.CASCADE)
    employee_pay = models.ForeignKey("Payroll", on_delete=models.CASCADE, related_name="employee_pay", null=True, blank=True)
    ad = models.ForeignKey("VariableCalc", on_delete=models.CASCADE, related_name="ad", null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email= models.EmailField(max_length=50, unique=True)
    created = models.DateTimeField(default=timezone.now, blank=False)
    photo = models.FileField(blank=True, null=True)
    nin = models.CharField(default=nin_no, unique = True,max_length=255, editable=False)
    tin_no = models.CharField(default=tin_no, unique = True, max_length=255, editable=False)
    date_of_birth = models.DateField(blank=True, null=True)
    date_of_employment = models.DateField(blank=True, null=True)
    contract_type = models.CharField(choices=CONTRACT_TYPE, max_length=1, blank=True, null=True)
    phone_regex = RegexValidator(
        regex=r"^\+?1?\d{3}\d{9,11}$",
        message="Phone number must be entered in the format: '+999999999'. Up to 11 digits allowed.",
    )
    phone = models.CharField(
        validators=[phone_regex],
        default=1234567890,
        max_length=11,
        blank=True,
        unique=True,
        verbose_name="phone number",
    )
    gender = models.CharField(
        max_length=255,
        choices=GENDER,
        default="others",
        blank=False,
        verbose_name="gender",
    )
    address = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="address"
    )
    created = models.DateTimeField(default=timezone.now, blank=False)
    job_title = models.CharField(
        max_length=255,
        choices=LEVEL,
        default="casual",
        blank=False,
        verbose_name="designation",
    )
    bank = models.CharField(
        max_length=10, choices=BANK, default="Z", verbose_name="employee BANK"
    )
    bank_account_name = models.CharField(
        max_length=255, verbose_name="Bank Account Name", unique=True, blank=True, null=True
    )
    bank_account_number = models.CharField(
        max_length=10, verbose_name="Bank Account Number", unique=True, blank=True, null=True
    )
    # net_pay = models.DecimalField(max_digits=12, default=0.0,decimal_places=2,blank=True)
    is_active = models.BooleanField(default=False)
    objects = EmployeeManager()


    class Meta:
        ordering = ["-created"]

    def save(self, *args, **kwargs):
        self.net_pay = get_net_pay(self)

        super(EmployeeProfile, self).save(*args, **kwargs)


class AccountModelQuerySet(models.QuerySet):

    def active(self):
        return self.filter(active=True)

class PayrollManager(models.Manager):
    def get_queryset(self):
        return AccountModelQuerySet(self.model, using=self._db)

class Payroll(models.Model):
    # employee = models.ForeignKey(Employee, related_name='employee_payroll', on_delete=models.CASCADE)
    # var = models.ForeignKey("VariableCalc", on_delete=models.CASCADE, related_name="var_pay")
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, null=False, blank=False)
    basic = models.DecimalField(max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True)
    housing = models.DecimalField(max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True)
    transport = models.DecimalField(max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True)
    bht = models.DecimalField(max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True)
    pension_employee = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    pension_employer = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    pension = models.DecimalField(max_digits=12, default=0.0,decimal_places=2, blank=True)
    gross_income = models.DecimalField(max_digits=12, default=Decimal(0.0),decimal_places=2, blank=True)
    consolidated_relief = models.DecimalField(max_digits=12, default=0.0,decimal_places=2, blank=True)
    taxable_income = models.DecimalField(max_digits=12, default=Decimal(0.0),decimal_places=2, blank=True)
    payee = models.DecimalField(max_digits=12,decimal_places=2, null=True, blank=True)
    
    water_rate = models.DecimalField(max_digits=12, default=Decimal(200.0),decimal_places=2, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True) 
    updated = models.DateTimeField(auto_now=True) 
    active = models.BooleanField(default=False)
    objects= PayrollManager()

    def __str__(self):
        print(f"this is the basic salary: {self.basic_salary}")

        # print(first_taxable(self))
        print(f"second tax:{second_taxable(self)}")
        print(f"third tax: {third_taxable(self)}")
        print(f"fourth tax: {fourth_taxable(self)}")
        print(f"fifth tax: {fifth_taxable(self)}")
        print(f"sixth tax: {sixth_taxable(self)}")
        print(f"seventh tax: {seventh_taxable(self)}")
        return str(self.basic_salary)

    @property
    def get_gross_income(self):
        return (self.basic_salary *12) - (get_pension_employee(self)*12)

    @property
    def calculate_taxable_income(self) -> Decimal:
        if self.basic_salary <= 30000:
            return Decimal(0.00)
        calc= (
            (self.get_gross_income)
            - (get_consolidated_relief(self))
            
        )
        if calc <=0.0:
            return Decimal(0.0)
        return calc

    
    
    def save(self, *args, **kwargs):
        # self.name = self.get_name
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
    # payr = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='variable_payroll')
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, blank=False, null=False)
    is_leave = models.BooleanField(default=False)
    is_overtime = models.BooleanField(default=False)
    is_absent = models.BooleanField(default=False)
    is_late = models.BooleanField(default=False)
    leave_allowance = models.DecimalField(max_digits=12,default=0.0, decimal_places=2, blank=True)
    lateness = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    overtime = models.DecimalField(max_digits=12, decimal_places=2,blank=True)
    absent = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    damage = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    # total_net_pay = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    
    class Meta:
        verbose_name_plural = "Payroll Variable"

    def __str__(self):
        return str(self.basic_salary)
    
    @property
    def get_leave_allowance(self):
        if self.is_leave:
            return (self.basic_salary * 12) * Decimal(3.6) / 100
        return 0.0

    @property
    def get_overtime(self):
        if self.is_overtime:
            return 1000
        return 0.0

    @property
    def get_late(self):
        if self.is_late:
            return self.basic_salary * Decimal(0.05) / 100
        return 0
    
    @property
    def get_absent(self):
        if self.is_late:
            return self.basic_salary * Decimal(0.5) / 100
        return 0
    
    @property
    def get_damage(self):
        if self.is_late:
            return self.basic_salary * 10 / 100
        return 0


    def save(self, *args, **kwargs):
        self.leave_allowance = self.get_leave_allowance
        self.overtime = self.get_overtime
        self.lateness = self.get_late
        self.absent = self.get_absent
        self.damage = self.get_damage
        # self.total_net_pay = self.get_total_netpay
        super(VariableCalc, self).save(*args, **kwargs)

# class PayVar(models.Model):
#     pays = models.ForeignKey(Payroll, related_name="pays", on_delete=models.CASCADE)
#     var = models.ForeignKey(VariableCalc, on_delete=models.CASCADE, related_name="var")
#     net_pay = models.

class PayT(models.Model):
    class PayTManager(models.Model):
        def get_queryset(self):
            return super().get_queryset().filter(is_active=True)  # type: ignore
    name = models.CharField(max_length=50, unique=True, default="test")
    slug = AutoSlugField(populate_from="name",editable=True,always_update=True)  # type: ignore
    paydays = MonthField("Month Value", help_text="some help...", null=True)
    # month = MonthField()
    payroll_payday= models.ManyToManyField(Employee, related_name="payroll_payday", through='Payday')
    is_active = models.BooleanField(default=False)
    objects = PayTManager()
    
    class Meta:
        verbose_name_plural = "PayTs"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("payroll:payslip",args=[self.slug])

    def __str__(self):
        return str(self.paydays)

    # def __unicode__(self):
    #     return unicode(self.month_year)

class Payday(models.Model):
    paydays_id = models.ForeignKey(PayT, on_delete=models.CASCADE, related_name="pay")
    payroll_id = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="payroll_paydays")


# class Employee_pay(models.Model):
#     employee_id = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="employee_id")
