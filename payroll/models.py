from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from autoslug import AutoSlugField

from PIL import Image

from payroll.generator import emp_id, nin_no, tin_no
from payroll.utils import *
from payroll.choices import *

from monthyear.models import MonthField

# def __str__(self):
#     return self.first_na

# class EmployeeQuerySet(models.QuerySet):
#     # def search(self, query=None):
#     #     if query is None or query == "":
#     #         return self.none()
#     #     lookups = (
#     #         Q(first_name__icontains=query) |
#     #         Q(email__icontains=query)
#     #     )
#     #     return self.filter(lookups)
#     def active(self):


class EmployeeManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")

    # def search(self, query=None):
    #     return self.get_queryset().search(query=query)


class EmployeeProfile(models.Model):
    emp_id = models.CharField(
        default=emp_id, unique=True, max_length=255, editable=False
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, blank=True, null=True, related_name="employee_user")
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(
        max_length=255,
        blank=True,
    )

    employee_pay = models.ForeignKey(
        "Payroll",
        on_delete=models.CASCADE,
        related_name="employee_pay",
        null=True,
        blank=True,
    )
    created = models.DateTimeField(default=timezone.now, blank=False)
    photo = models.FileField(blank=True, null=True, default="default.png")
    nin = models.CharField(default=nin_no, unique=True, max_length=255, editable=False)
    tin_no = models.CharField(
        default=tin_no, unique=True, max_length=255, editable=False
    )
    date_of_birth = MonthField(
        "Date of Birth",
        help_text="date of birth month and year...",
        null=True,
    )
    date_of_employment = MonthField(
        "Date of Employment",
        help_text="date of birth month and year...",
        null=True,
    )
    contract_type = models.CharField(
        choices=CONTRACT_TYPE, max_length=1, blank=True, null=True
    )
    # phone_regex = RegexValidator(
    #     regex=r"^\+?1?\d{3}\d{9,13}$",
    #     message="Phone number must be entered in the format: '+999999999'. Up to 11 digits allowed.",
    # )
    phone = models.CharField(
        default=1234567890,
        max_length=15,
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
        max_length=255,
        verbose_name="Bank Account Name",
        unique=True,
        blank=True,
        null=True,
    )
    bank_account_number = models.CharField(
        max_length=10,
        verbose_name="Bank Account Number",
        unique=True,
        blank=True,
        null=True,
    )
    net_pay = models.DecimalField(
        max_digits=12, default=0.0, decimal_places=2, blank=True
    )
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    objects = models.Manager()  # The default manager.
    emp_objects = EmployeeManager()

    def __str__(self):
        return self.first_name

    class Meta:
        ordering = ["-created"]

    @property
    def save_img(self):
        img = Image.open(self.photo.path)

        if img.height > 300 or img.width > 300:
            output_size = (300, 300)
            img.thumbnail(output_size)
            img.save(self.photo.path)

    @property
    def get_email(self):
        return f"{self.first_name}.{self.last_name}@email.com"

    def save(self, *args, **kwargs):
        self.net_pay = get_net_pay(self)
        self.email = self.get_email

        super(EmployeeProfile, self).save(*args, **kwargs)


class PayrollManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")


class Payroll(models.Model):
    basic_salary = models.DecimalField(
        max_digits=12, decimal_places=2, null=False, blank=False
    )
    basic = models.DecimalField(
        max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True
    )
    housing = models.DecimalField(
        max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True
    )
    transport = models.DecimalField(
        max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True
    )
    bht = models.DecimalField(
        max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True
    )
    pension_employee = models.DecimalField(
        max_digits=12, default=0.0, decimal_places=2, blank=True
    )
    pension_employer = models.DecimalField(
        max_digits=12, default=0.0, decimal_places=2, blank=True
    )
    pension = models.DecimalField(
        max_digits=12, default=0.0, decimal_places=2, blank=True
    )
    gross_income = models.DecimalField(
        max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True
    )
    consolidated_relief = models.DecimalField(
        max_digits=12, default=0.0, decimal_places=2, blank=True
    )
    taxable_income = models.DecimalField(
        max_digits=12, default=Decimal(0.0), decimal_places=2, blank=True
    )
    payee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    water_rate = models.DecimalField(
        max_digits=12, default=Decimal(200.0), decimal_places=2, blank=True
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    objects = PayrollManager()

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
        return (self.basic_salary * 12) - (get_pension_employee(self) * 12)

    @property
    def calculate_taxable_income(self) -> Decimal:
        if self.basic_salary <= 30000:
            return Decimal(0.00)
        calc = (self.get_gross_income) - (get_consolidated_relief(self))
        if calc <= 0.0:
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


class Allowance(models.Model):
    payee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="employee_allowance",
    )
    name = models.CharField(
        max_length=50,
        verbose_name=(_("Name of allowance to be added")),
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.0,
        verbose_name=(_("Amount of allowance earned")),
    )

    class Meta:
        verbose_name_plural = "Allowance"

    def __str__(self):
        return f"Allowance {self.amount} for {self.payr.first_name}"


class PayVarManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")


class PayVar(models.Model):
    pays = models.ForeignKey(
        EmployeeProfile, related_name="pays", on_delete=models.CASCADE
    )
    is_absent = models.BooleanField(default=False)
    is_late = models.BooleanField(default=False)
    is_loan = models.BooleanField(default=False)
    is_coop = models.BooleanField(default=False)
    lateness = models.DecimalField(
        max_digits=12, default=0.0, decimal_places=2, blank=True
    )
    absent = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    damage = models.DecimalField(
        max_digits=12, default=0.0, decimal_places=2, blank=True
    )
    loan = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    coop = models.DecimalField(max_digits=12, default=0.0, decimal_places=2, blank=True)
    netpay = models.DecimalField(
        max_digits=12, default=0.0, decimal_places=2, blank=True
    )
    status = models.CharField(max_length=10, choices=STATUS, default="pending")

    objects = PayVarManager()

    def __str__(self):
        return self.pays.first_name

    @property
    def get_late(self):
        if self.is_late:
            return self.lateness
        return 0

    @property
    def get_absent(self):
        if self.is_late:
            return self.absent
        return 0

    @property
    def get_damage(self):
        if self.is_late:
            return self.damage
        return 0

    @property
    def get_loan(self):
        if self.is_loan:
            return self.loan
        return 0

    @property
    def get_coop(self):
        if self.is_coop:
            return self.coop
        return 0

    @property
    def get_netpay(self):

        return (
            self.pays.net_pay
            - Decimal(self.lateness or 0)
            - Decimal(self.damage or 0)
            - Decimal(self.absent or 0)
            - Decimal(self.loan or 0)
            - Decimal(self.coop or 0)
        )

    def save(self, *args, **kwargs):
        self.netpay = self.get_netpay
        self.absent = self.get_absent
        self.lateness = self.get_late
        self.damage = self.get_damage
        self.loan = self.get_loan
        self.coop = self.get_coop
        super(PayVar, self).save(*args, **kwargs)


class PayManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class PayT(models.Model):
    name = models.CharField(max_length=50, unique=True, default="test")
    slug = AutoSlugField(populate_from="name", editable=True, always_update=True)  # type: ignore
    paydays = MonthField(
        "Month Value",
        help_text="some help...",
        null=True,
    )
    # month = MonthField()
    payroll_payday = models.ManyToManyField(
        PayVar, related_name="payroll_payday", through="Payday"
    )
    is_active = models.BooleanField(default=False)
    objects = PayManager()

    class Meta:
        verbose_name_plural = "PayTs"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("payroll:payslip", args=[self.slug])

    def __str__(self):
        return str(self.paydays)


class Payday(models.Model):
    paydays_id = models.ForeignKey(PayT, on_delete=models.CASCADE, related_name="pay")
    payroll_id = models.ForeignKey(
        PayVar, on_delete=models.CASCADE, related_name="payroll_paydays"
    )
