from decimal import Decimal
import os
from uuid import uuid4

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError

from django.db.models.signals import post_save
from django.dispatch import receiver

from autoslug import AutoSlugField

from datetime import timedelta

from PIL import Image
from core import settings

from payroll.generator import emp_id, nin_no, tin_no
from payroll import utils
from payroll import choices

from monthyear.models import MonthField
from users.models import CustomUser


def path_and_rename(instance, filename):
    upload_to = "employee_photo"
    ext = filename.split(".")[-1]
    # get filename
    if instance.pk:
        filename = "{}.{}".format(instance.pk, ext)
    else:
        # set filename as random string
        filename = "{}.{}".format(uuid4().hex, ext)
    # return the whole path to the file
    return os.path.join(upload_to, filename)


class EmployeeManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")

    # def search(self, query=None):
    #     return self.get_queryset().search(query=query)


class EmployeeProfile(models.Model):
    emp_id = models.CharField(
        default=emp_id,
        unique=True,
        max_length=255,
        editable=False,
    )
    slug = models.CharField(
        unique=True,
        max_length=50,
        verbose_name=_("Employee slug to identify and route the employee."),
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="employee_user",
    )
    first_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    last_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
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
    created = models.DateTimeField(
        default=timezone.now,
        blank=False,
        editable=False,
    )
    photo = models.FileField(
        blank=True,
        null=True,
        default="default.png",
        upload_to=path_and_rename,
    )
    nin = models.CharField(
        default=nin_no,
        unique=True,
        max_length=255,
        editable=False,
    )
    tin_no = models.CharField(
        default=tin_no,
        unique=True,
        max_length=255,
        editable=False,
    )
    pension_rsa = models.CharField(
        unique=True,
        max_length=15,
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
        choices=choices.CONTRACT_TYPE,
        max_length=1,
        blank=True,
        null=True,
    )
    phone_regex = RegexValidator(
        regex=r"^(?:\+\d{1,3}\s?)?(\d{3}-\d{3}-\d{4})$",
        message="Phone number must be entered in the format: +1 123-456-7890 Up to 17 digits allowed.",
    )
    phone = models.CharField(
        # default=phone_regex,
        validators=[phone_regex],
        max_length=17,
        blank=True,
        unique=True,
        verbose_name="phone number",
    )
    gender = models.CharField(
        max_length=255,
        choices=choices.GENDER,
        default="others",
        blank=False,
        verbose_name="gender",
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="address",
    )

    job_title = models.CharField(
        max_length=255,
        choices=choices.LEVEL,
        default="casual",
        blank=False,
        verbose_name="designation",
    )
    bank = models.CharField(
        max_length=10,
        choices=choices.BANK,
        default="Z",
        verbose_name="employee BANK",
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
        max_digits=12,
        default=0.0,
        decimal_places=2,
        blank=True,
        editable=False,
    )
    status = models.CharField(
        max_length=10,
        choices=choices.STATUS,
        default="pending",
    )
    objects = models.Manager()  # The default manager.
    emp_objects = EmployeeManager()

    def __str__(self):
        return self.first_name or "test"

    class Meta:
        ordering = ["-created"]

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("payroll:list-payslip", args=[str(self.slug)])

    @property
    def save_img(self):
        img = Image.open(self.photo.path)

        if img.height > 300 or img.width > 300:
            output_size = (300, 300)
            img.thumbnail(output_size)
            img.save(self.photo.path)

    @property
    def get_first_name(self):
        return self.request

    @property
    def format_rsa(self):
        return f"RSA-{self.pension_rsa}"

    @property
    def save_slug(self):
        return f"{self.first_name}-{self.last_name}"

    @property
    def get_email(self):
        return f"{self.first_name}.{self.last_name}@email.com"

    def save(self, *args, **kwargs):
        self.net_pay = utils.get_net_pay(self)  # noqa: F405
        self.email = self.get_email
        self.slug = self.save_slug
        # self.pension_rsa = self.format_rsa

        super(EmployeeProfile, self).save(*args, **kwargs)


@receiver(post_save, sender=CustomUser)
def create_employee(sender, instance, created, **kwargs):
    if created:
        EmployeeProfile.objects.create(
            user=instance, first_name=instance.first_name, last_name=instance.last_name
        )


class PayrollManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")


class Payroll(models.Model):
    basic_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=False,
        blank=False,
    )
    basic = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )
    housing = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )
    transport = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )
    bht = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )
    pension_employee = models.DecimalField(
        max_digits=12,
        default=0.0,
        decimal_places=2,
        blank=True,
    )
    pension_employer = models.DecimalField(
        max_digits=12,
        default=0.0,
        decimal_places=2,
        blank=True,
    )
    pension = models.DecimalField(
        max_digits=12,
        default=0.0,
        decimal_places=2,
        blank=True,
    )
    gross_income = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )
    consolidated_relief = models.DecimalField(
        max_digits=12,
        default=0.0,
        decimal_places=2,
        blank=True,
    )
    taxable_income = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )
    payee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    water_rate = models.DecimalField(
        max_digits=12,
        default=Decimal(200.0),
        decimal_places=2,
        blank=True,
    )
    nsitf = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=10,
        choices=choices.STATUS,
        default="active",
    )
    objects = PayrollManager()

    def __str__(self):
        return str(self.basic_salary)

    @property
    def get_annual_gross(self):
        return self.basic_salary * 12

    @property
    def get_nsitf(self):
        return self.basic_salary * 1 / 100

    @property
    def get_gross_income(self):
        return self.get_annual_gross - utils.get_pension_employee(self)

    @property
    def calculate_taxable_income(self) -> Decimal:
        calc = (
            self.get_annual_gross
            - utils.get_consolidated_relief(self)
            - utils.get_pension_employee(self)
        )
        if calc <= 0:
            return Decimal(0.0)
        return calc

    def save(self, *args, **kwargs):
        print(f"second payee: ₦{utils.second_taxable(self):,.2f}")
        print(f"third payee: ₦{utils.third_taxable(self):,.2f}")
        print(f"fourth payee: ₦{utils.fourth_taxable(self):,.2f}")
        print(f"fifth payee: ₦{utils.fifth_taxable(self):,.2f}")
        print(f"sixth payee: ₦{utils.sixth_taxable(self):,.2f}")
        print(f"seventh payee: ₦{utils.seventh_taxable(self):,.2f}")
        # self.name = self.get_name
        self.basic = utils.get_basic(self)  # noqa: F405
        self.housing = utils.get_housing(self)  # noqa: F405
        self.transport = utils.get_transport(self)  # noqa: F405
        self.bht = utils.get_bht(self)  # noqa: F405
        self.pension_employee = utils.get_pension_employee(self)  # noqa: F405
        self.pension_employer = utils.get_pension_employer(self)  # noqa: F405
        self.pension = utils.get_pension(self)  # noqa: F405
        self.gross_income = self.get_gross_income
        self.consolidated_relief = utils.get_consolidated_relief(self)  # noqa: F405
        self.taxable_income = self.calculate_taxable_income
        self.payee = utils.get_payee(self)  # noqa: F405
        self.water_rate = utils.get_water_rate(self)  # noqa: F405
        self.nsitf = self.get_nsitf

        super(Payroll, self).save(*args, **kwargs)


class Allowance(models.Model):
    name = models.CharField(
        max_length=50,
        choices=choices.ALLOWANCES,
        verbose_name=(_("Name of allowance to be added")),
    )
    percentage = models.DecimalField(
        decimal_places=2,
        max_digits=4,
        verbose_name="percentage of allowance to be given",
        default=0.0,
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
        return f"{self.name} Allowance"

    # @property
    # def calc_amount(self):
    #     return (self.payee.employee_pay.basic_salary * 12) * self.percentage / 100

    # def save(self, *args, **kwargs):
    #     self.amount = self.calc_amount

    #     super(Allowance, self).save(*args, **kwargs)


class Deduction(models.Model):
    name = models.CharField(
        max_length=50,
        choices=choices.DEDUCTIONS,
        verbose_name=(_("Name of deduction to be added")),
    )
    percentage = models.DecimalField(
        decimal_places=2,
        max_digits=4,
        verbose_name="percentage of Deductions to be deducted",
        default=0.0,
    )

    class Meta:
        verbose_name_plural = "Deductions"

    def __str__(self):
        return f"{self.name} Deduction"


#    @property
#     def calc_amount(self):
#         return (self.payee.employee_pay.basic_salary * 12) * self.percentage / 100

#     def save(self, *args, **kwargs):
#         self.amount = self.calc_amount

#         super(Deduction, self).save(*args, **kwargs)


class PayVarManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")


class PayVar(models.Model):
    pays = models.ForeignKey(
        EmployeeProfile, related_name="pays", on_delete=models.CASCADE
    )
    allowance_id = models.ForeignKey(
        Allowance,
        related_name="pay_allowance",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    deduction_id = models.ForeignKey(
        Deduction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    is_housing = models.BooleanField(
        verbose_name="is NHF deductable",
        default=False,
    )
    is_nhif = models.BooleanField(
        verbose_name="is NHIF deductable",
        default=False,
    )
    nhf = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        default=0.0,
    )
    employee_health = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        default=0.0,
    )
    nhif = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        default=0.0,
    )
    emplyr_health = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        default=0.0,
    )
    status = models.CharField(
        max_length=10,
        choices=choices.STATUS,
        default="pending",
    )
    netpay = models.DecimalField(
        max_digits=12,
        default=0.0,
        decimal_places=2,
        blank=True,
    )

    objects = PayVarManager()

    def __str__(self):
        return self.pays.first_name

    @property
    def calc_allowance(self):
        return (
            self.pays.net_pay
            * (
                self.allowance_id.percentage
                if self.allowance_id.percentage
                else Decimal(0)
            )
            / 100
        )

    @property
    def calc_deduction(self):
        return (
            self.pays.net_pay
            * (
                self.deduction_id.percentage
                if self.deduction_id.percentage
                else Decimal(0)
            )
            / 100
        )

    @property
    def calc_housing(self) -> Decimal:
        if self.is_housing:
            return self.pays.employee_pay.basic_salary * Decimal(2.5) / 100
        else:
            return Decimal(0.0)

    @property
    def calc_employer_health_contrib(self) -> Decimal:
        if self.is_nhif:
            return self.pays.employee_pay.basic_salary * Decimal(3.25) / 100
        else:
            return Decimal(0.0)

    @property
    def calc_employee_health_contrib(self) -> Decimal:
        if self.is_nhif:
            return self.pays.employee_pay.basic_salary * Decimal(1.75) / 100
        else:
            return Decimal(0.0)

    @property
    def calc_health_contrib(self) -> Decimal:
        return self.calc_employee_health_contrib + self.calc_employer_health_contrib

    @property
    def total_deductions(self) -> Decimal:
        return

    @property
    def get_netpay(self):
        return (
            self.pays.net_pay
            + (self.calc_allowance or 0)
            - self.calc_deduction
            - self.employee_health
            - self.nhf
            - self.pays.employee_pay.nsitf
        )

    def save(self, *args, **kwargs):
        self.netpay = self.get_netpay
        self.nhf = self.calc_housing
        self.employee_health = self.calc_employee_health_contrib
        self.emplyr_health = self.calc_employer_health_contrib
        self.nhif = self.calc_health_contrib
        super(PayVar, self).save(*args, **kwargs)


class PayManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class PayT(models.Model):
    name = models.CharField(
        max_length=50,
        unique=True,
        default="test",
    )
    slug = AutoSlugField(
        populate_from="name",
        editable=True,
        always_update=True,
    )  # type: ignore
    paydays = MonthField(
        "Month Value",
        help_text="some help...",
        null=True,
    )
    paydays_str = models.CharField(
        editable=True,
        # unique=Tru?e,
        max_length=100,
        null=True,
        blank=True,
        default="a",
    )
    # month = MonthField()
    payroll_payday = models.ManyToManyField(
        PayVar, related_name="payroll_payday", through="Payday"
    )
    is_active = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)
    objects = PayManager()

    class Meta:
        verbose_name_plural = "PayTs"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("payroll:payslip", args=[self.slug])

    def __str__(self):
        return str(self.paydays)

    @property
    def save_month_str(self):

        return utils.convert_month_to_word(str(self.paydays))

    def save(self, *args, **kwargs):
        if self.pk and PayT.objects.filter(pk=self.pk, closed=True).exists():
            raise ValidationError("This entry is closed and cannot be edited.")
        self.paydays_str = self.save_month_str

        super(PayT, self).save(*args, **kwargs)


class Payday(models.Model):
    paydays_id = models.ForeignKey(
        PayT,
        on_delete=models.CASCADE,
        related_name="paydays_id",
    )
    payroll_id = models.ForeignKey(
        PayVar,
        on_delete=models.CASCADE,
        related_name="payroll_paydays",
    )


class IOU(models.Model):
    employee_id = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.PROTECT,
        related_name="employee_iou",
    )
    amount = models.DecimalField(
        decimal_places=2,
        max_digits=12,
    )
    tenor = models.IntegerField(
        help_text="Tenor of the IOU",
    )
    created_at = models.DateField(
        auto_now_add=True,
        help_text="Date the record of IOU is created",
    )
    approved_at = models.DateField(
        help_text="Date the IOU is approved",
    )
    due_date = models.DateTimeField(
        help_text="due date of IOU taken",
    )

    def __str__(self):
        return f"{self.employee_id.first_name} with iou of {self.amount}"

    @property
    def get_due_date(self):
        due_date = self.approved_at + timedelta(days=365 * self.tenor)
        return due_date

    def save(self, *args, **kwargs):
        self.due_date = self.get_due_date
        super(IOU, self).save(*args, **kwargs)
