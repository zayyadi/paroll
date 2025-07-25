from decimal import Decimal


from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

from django.utils import timezone  # Import timezone

from autoslug import AutoSlugField

from datetime import timedelta


from core import settings

from payroll import utils
from payroll import choices

from monthyear.models import MonthField
from payroll.models.employee_profile import EmployeeProfile
from payroll.models.utils import SoftDeleteModel


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
    employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="allowances",
        null=True,
        blank=True,
    )
    allowance_type = models.CharField(
        max_length=50,
        choices=choices.ALLOWANCES,
        verbose_name=(_("Type of allowance")),
        default="OTHER",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.0,
        verbose_name=(_("Amount of allowance earned")),
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "Allowances"

    # def __str__(self):
    #     # return f"{self.employee.first_name} {self.employee.last_name} - {self.allowance_type} ({self.amount})"
    #     pass


class Deduction(models.Model):
    employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="deductions",
        null=True,
        blank=True,
    )
    deduction_type = models.CharField(
        max_length=50,
        choices=choices.DEDUCTIONS,
        verbose_name=(_("Type of deduction")),
        default="OTHER",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.0,
        verbose_name=(_("Amount of deduction")),
    )
    reason = models.TextField(
        blank=True, null=True, verbose_name=(_("Reason for disciplinary deduction"))
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "Deductions"

    def __str__(self):
        return f"{self.employee.first_name} {self.employee.last_name} - {self.deduction_type} ({self.amount})"


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
        # Old implementation (commented out):
        # if self.allowance_id and self.allowance_id.percentage:
        #     return self.pays.net_pay * self.allowance_id.percentage / 100
        # return Decimal(0)

        # New implementation: Sum allowances for the employee within the payroll period
        # Assuming 'self.paydays_id.paydays' gives the month/year for this payroll
        if not hasattr(self, "paydays_id") or not self.paydays_id:
            return Decimal(0)

        payroll_month = self.paydays_id.paydays.month
        payroll_year = self.paydays_id.paydays.year

        total_allowance = Decimal(0)
        for allowance in self.pays.allowances.filter(
            created_at__month=payroll_month, created_at__year=payroll_year
        ):
            total_allowance += allowance.amount
        return total_allowance

    @property
    def calc_deduction(self):
        # Old implementation (commented out):
        # if self.deduction_id and self.deduction_id.percentage:
        #     return self.pays.net_pay * self.deduction_id.percentage / 100
        # return Decimal(0)

        # New implementation: Sum deductions for the employee within the payroll period
        if not hasattr(self, "paydays_id") or not self.paydays_id:
            return Decimal(0)

        payroll_month = self.paydays_id.paydays.month
        payroll_year = self.paydays_id.paydays.year

        total_deduction = Decimal(0)
        for deduction in self.pays.deductions.filter(
            created_at__month=payroll_month, created_at__year=payroll_year
        ):
            total_deduction += deduction.amount
        return total_deduction

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
        total = (
            self.calc_deduction
            + self.employee_health
            + self.nhf
            + self.pays.employee_pay.nsitf
        )
        return total

    @property
    def get_netpay(self):
        if not self.pays.net_pay:
            return Decimal(0.0)
        print(f"pays: {self.pays.net_pay}")
        return (
            self.pays.net_pay
            + self.calc_allowance
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

        return reverse("payroll:pay_period_detail", args=[self.slug])

    def __str__(self):
        return str(self.paydays)

    @property
    def save_month_str(self):

        return utils.convert_month_to_word(str(self.paydays))

    def save(self, *args, **kwargs):
        if self.pk and PayT.objects.filter(pk=self.pk, closed=True).exists():
            raise ValidationError("This entry is closed and cannot be edited.")
        # self.paydays_str = self.save_month_str

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


class IOU(SoftDeleteModel):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("PAID", "Paid"),
    ]
    PAYMENT_METHOD_CHOICES = [
        ("SALARY_DEDUCTION", "Salary Deduction"),
        ("DIRECT_PAYMENT", "Direct Payment"),
    ]

    employee_id = models.ForeignKey(
        "EmployeeProfile",
        on_delete=models.PROTECT,
        related_name="employee_iou",
    )
    amount = models.DecimalField(
        decimal_places=2,
        max_digits=12,
        validators=[MinValueValidator(0.01)],  # Ensure amount is positive
    )
    tenor = models.IntegerField(
        help_text="Tenor of the IOU (in months)",
        validators=[MinValueValidator(1)],  # Ensure tenor is at least 1 month
    )
    reason = models.TextField(
        help_text="Reason for the IOU request",
        blank=True,
        null=True,
    )
    interest_rate = models.DecimalField(
        decimal_places=2,
        max_digits=5,
        default=0.0,
        help_text="Interest rate (e.g., 5.0 for 5%)",
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="SALARY_DEDUCTION",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="PENDING",
    )
    created_at = models.DateField(
        auto_now_add=True,
        help_text="Date the record of IOU is created",
    )
    approved_at = models.DateField(
        help_text="Date the IOU is approved",
        null=True,
        blank=True,
    )
    due_date = models.DateField(
        help_text="Due date of IOU repayment",
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.employee_id.first_name} - IOU of {self.amount}"

    @property
    def total_amount(self):
        return self.amount + (self.amount * self.interest_rate / 100)

    @property
    def get_due_date(self):
        # Calculate due date based on tenor in months
        if self.approved_at is not None:
            due_date = self.approved_at + timedelta(days=(365 / 12) * self.tenor)
        else:
            due_date = self.created_at + timedelta(days=(365 / 12) * self.tenor)
        return due_date

    def clean(self):
        super().clean()
        if self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})
        if self.tenor <= 0:
            raise ValidationError({"tenor": "Tenor must be at least 1 month."})

    def save(self, *args, **kwargs):
        # Ensure created_at is set if this is a new instance and it's not already set
        if not self.pk and not self.created_at:  # self.pk is None for new instances
            self.created_at = timezone.now().date()

        if (
            not self.due_date and self.tenor
        ):  # Only calculate if due_date is not set and tenor is available
            base_date_for_due_calc = self.approved_at  # Prioritize approved_at
            if not base_date_for_due_calc:
                base_date_for_due_calc = self.created_at  # Fallback to created_at

            if base_date_for_due_calc:  # Ensure we have a base date
                self.due_date = base_date_for_due_calc + timedelta(
                    days=(365 / 12) * self.tenor
                )  # Consider using dateutil.relativedelta for more accuracy
        super().save(*args, **kwargs)


class LeavePolicy(models.Model):
    LEAVE_TYPES = [
        ("CASUAL", "Casual Leave"),
        ("SICK", "Sick Leave"),
        ("ANNUAL", "Annual Leave"),
        ("MATERNITY", "Maternity Leave"),
        ("PATERNITY", "Paternity Leave"),
    ]
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES, unique=True)
    max_days = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.leave_type} - {self.max_days} days"


class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]
    employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="leave_requests",
    )
    LEAVE_CHOICES = [
        ("CASUAL", "Casual Leave"),
        ("SICK", "Sick Leave"),
        ("ANNUAL", "Annual Leave"),
        ("MATERNITY", "Maternity Leave"),
        ("PATERNITY", "Paternity Leave"),
    ]
    leave_type = models.CharField(
        max_length=20,
        choices=LEAVE_CHOICES,
        default="ANNUAL",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.employee.first_name} - {self.leave_type} ({self.status})"
