from decimal import Decimal
import uuid
import logging

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.core.validators import MaxValueValidator

from django.utils import timezone  # Import timezone

# from autoslug import AutoSlugField  # Temporarily commented out for testing

from calendar import monthrange
from datetime import date, timedelta


from core import settings

logger = logging.getLogger(__name__)

from payroll import utils
from payroll import choices

from monthyear.models import MonthField
from payroll.models.employee_profile import EmployeeProfile
from payroll.models.utils import SoftDeleteModel


class PayrollManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")


def _deduction_debug_print(message: str) -> None:
    logger.debug("[DEDUCTION_DEBUG] %s", message)


class CompanyPayrollSetting(models.Model):
    company = models.OneToOneField(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="payroll_setting",
    )
    basic_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("40.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    housing_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    transport_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    pension_employee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("8.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    pension_employer_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    nhf_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.50"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    leave_allowance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Percentage of monthly basic salary paid as leave allowance.",
    )
    pays_thirteenth_month = models.BooleanField(
        default=True,
        help_text="When enabled, employees receive 13th month in December.",
    )
    thirteenth_month_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Percentage of annual basic salary paid as 13th month.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Payroll Setting"
        verbose_name_plural = "Company Payroll Settings"

    def __str__(self):
        return f"{self.company} payroll settings"

    def get_health_tier_for_salary(self, basic_salary: Decimal):
        salary = Decimal(basic_salary or Decimal("0"))
        for tier in self.health_insurance_tiers.all().order_by(
            "sort_order", "min_salary"
        ):
            if tier.matches_salary(salary):
                return tier
        return None

    def create_default_health_tiers(self):
        if self.health_insurance_tiers.exists():
            return
        CompanyHealthInsuranceTier.objects.bulk_create(
            [
                CompanyHealthInsuranceTier(
                    setting=self,
                    min_salary=Decimal("0.00"),
                    max_salary=Decimal("499999.99"),
                    employee_percentage=Decimal("5.00"),
                    employer_percentage=Decimal("10.00"),
                    sort_order=1,
                ),
                CompanyHealthInsuranceTier(
                    setting=self,
                    min_salary=Decimal("500000.00"),
                    max_salary=Decimal("999999.99"),
                    employee_percentage=Decimal("10.00"),
                    employer_percentage=Decimal("5.00"),
                    sort_order=2,
                ),
                CompanyHealthInsuranceTier(
                    setting=self,
                    min_salary=Decimal("1000000.00"),
                    max_salary=None,
                    employee_percentage=Decimal("15.00"),
                    employer_percentage=Decimal("0.00"),
                    sort_order=3,
                ),
            ]
        )


class CompanyHealthInsuranceTier(models.Model):
    setting = models.ForeignKey(
        CompanyPayrollSetting,
        on_delete=models.CASCADE,
        related_name="health_insurance_tiers",
    )
    min_salary = models.DecimalField(max_digits=12, decimal_places=2)
    max_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leave empty for no upper limit.",
    )
    employee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    employer_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    sort_order = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Health Insurance Tier"
        verbose_name_plural = "Health Insurance Tiers"
        ordering = ("sort_order", "min_salary")

    def __str__(self):
        max_salary = self.max_salary if self.max_salary is not None else "and above"
        return (
            f"{self.setting.company}: {self.min_salary} - {max_salary} "
            f"(E:{self.employee_percentage}% / ER:{self.employer_percentage}%)"
        )

    def clean(self):
        super().clean()
        if self.max_salary is not None and self.max_salary < self.min_salary:
            raise ValidationError(
                {
                    "max_salary": "Max salary must be greater than or equal to min salary."
                }
            )

    def matches_salary(self, salary: Decimal) -> bool:
        if salary < self.min_salary:
            return False
        if self.max_salary is None:
            return True
        return salary <= self.max_salary


class Payroll(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="payroll_configs",
        null=True,
        blank=True,
        db_index=True,
    )
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
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )
    pension_employer = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )
    pension = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )
    gross_income = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
        help_text=(" Annual gross income of employee. "),
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
        default=Decimal(0.0),
    )
    employee_health = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        default=Decimal(0.0),
    )
    nhif = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        default=Decimal(0.0),
    )
    emplyr_health = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        default=Decimal(0.0),
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
        return self.basic_salary * Decimal(1) / Decimal(100)

    # @property
    # def get_gross_income(self):
    #     gross = self.get_annual_gross - utils.get_pension_employee(self)
    #     print(f" gross : {gross}")
    #     return gross

    def save(self, *args, **kwargs):
        # employee = self.employee_pay.first()
        # self.name = self.get_name
        self.basic = utils.get_basic(self)  # noqa: F405
        self.housing = utils.get_housing(self)  # noqa: F405
        self.transport = utils.get_transport(self)  # noqa: F405
        self.bht = utils.gross_income(self)  # noqa: F405
        self.pension_employee = utils.get_pension_employee(self)  # noqa: F405
        self.pension_employer = utils.get_pension_employer(self)  # noqa: F405
        self.pension = utils.get_pension(self)  # noqa: F405
        self.gross_income = utils.gross_income(self)  # noqa: F405
        self.nhf = utils.calc_housing(self)
        self.employee_health = utils.calc_employee_health_contrib(self)
        self.emplyr_health = utils.calc_employer_health_contrib(self)
        self.nhif = utils.calc_health_contrib(self)
        self.nsitf = self.get_nsitf
        self.taxable_income = utils.calculate_taxable_income(self)
        self.payee = utils.get_payee(self)  # noqa: F405
        self.water_rate = utils.get_water_rate(self)  # noqa: F405

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
        default=Decimal(0.0),
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
    iou = models.ForeignKey(
        "IOU",
        on_delete=models.SET_NULL,
        # --- CHANGE THIS LINE ---
        related_name="repayment_installments",  # Give it a unique name
        # ----------------------
        null=True,
        blank=True,
        help_text="The IOU this deduction is repaying, if any.",
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
        default=Decimal(0.0),
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


class PayrollEntryManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")


class PayrollEntry(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="payroll_entries",
        null=True,
        blank=True,
        db_index=True,
    )
    pays = models.ForeignKey(
        EmployeeProfile, related_name="pays", on_delete=models.CASCADE
    )
    status = models.CharField(
        max_length=10,
        choices=choices.STATUS,
        default="pending",
    )
    netpay = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
    )

    objects = PayrollEntryManager()

    def __str__(self):
        return self.pays.first_name

    @property
    def calc_allowance(self):
        if not self.pk:
            return Decimal(0)

        # Old implementation (commented out):
        # if self.allowance_id and self.allowance_id.percentage:
        #     return self.pays.net_pay * self.allowance_id.percentage / 100
        # return Decimal(0)

        # New implementation: Sum allowances for the employee within the payroll period
        payroll_run_entry = self.payroll_run_entries.select_related(
            "payroll_run"
        ).first()
        if not payroll_run_entry:
            return Decimal(0)

        payroll_month = payroll_run_entry.payroll_run.paydays.month
        payroll_year = payroll_run_entry.payroll_run.paydays.year

        total_allowance = Decimal(0)
        for allowance in self.pays.allowances.filter(
            created_at__month=payroll_month, created_at__year=payroll_year
        ):
            total_allowance += allowance.amount

        total_allowance += self._get_auto_leave_allowance(
            payroll_month=payroll_month,
            payroll_year=payroll_year,
        )
        total_allowance += self._get_auto_thirteenth_month_allowance(payroll_month)

        return total_allowance

    def _get_company_payroll_setting(self):
        company = self.company or self.pays.company
        if not company:
            return None
        return CompanyPayrollSetting.objects.filter(company=company).first()

    def _get_auto_leave_allowance(self, payroll_month: int, payroll_year: int) -> Decimal:
        payroll = self.pays.employee_pay
        if not payroll:
            return Decimal("0.00")

        setting = self._get_company_payroll_setting()
        if not setting:
            return Decimal("0.00")

        leave_allowance_percentage = Decimal(
            setting.leave_allowance_percentage or Decimal("0.00")
        )
        if leave_allowance_percentage <= 0:
            return Decimal("0.00")

        month_start = date(payroll_year, payroll_month, 1)
        month_end = date(
            payroll_year,
            payroll_month,
            monthrange(payroll_year, payroll_month)[1],
        )
        is_on_approved_leave = self.pays.leave_requests.filter(
            status="APPROVED",
            start_date__lte=month_end,
            end_date__gte=month_start,
        ).exists()
        if not is_on_approved_leave:
            return Decimal("0.00")

        monthly_basic_salary = Decimal(payroll.basic_salary or Decimal("0.00"))
        return (monthly_basic_salary * leave_allowance_percentage) / Decimal("100")

    def _get_auto_thirteenth_month_allowance(self, payroll_month: int) -> Decimal:
        if payroll_month != 12:
            return Decimal("0.00")

        payroll = self.pays.employee_pay
        if not payroll:
            return Decimal("0.00")

        setting = self._get_company_payroll_setting()
        pays_thirteenth_month = True
        thirteenth_month_percentage = Decimal("20.00")

        if setting:
            pays_thirteenth_month = bool(setting.pays_thirteenth_month)
            thirteenth_month_percentage = Decimal(
                setting.thirteenth_month_percentage or Decimal("20.00")
            )

        if not pays_thirteenth_month or thirteenth_month_percentage <= 0:
            return Decimal("0.00")

        annual_basic_salary = Decimal(payroll.basic_salary or Decimal("0.00")) * Decimal("12")
        return (annual_basic_salary * thirteenth_month_percentage) / Decimal("100")

    @property
    def calc_deduction(self):
        if not self.pk:
            _deduction_debug_print(
                f"PayrollEntry has no PK yet for employee={getattr(self.pays, 'id', None)}; returning 0."
            )
            return Decimal(0)

        # Old implementation (commented out):
        # if self.deduction_id and self.deduction_id.percentage:
        #     return self.pays.net_pay * self.deduction_id.percentage / 100
        # return Decimal(0)

        # New implementation: Sum deductions for the employee within the payroll period
        payroll_run_entry = self.payroll_run_entries.select_related(
            "payroll_run"
        ).first()
        if not payroll_run_entry:
            _deduction_debug_print(
                f"No payroll run entry linked for payroll_entry_id={self.pk}; returning 0."
            )
            return Decimal(0)

        payroll_month = payroll_run_entry.payroll_run.paydays.month
        payroll_year = payroll_run_entry.payroll_run.paydays.year
        employee_name = f"{self.pays.first_name} {self.pays.last_name}".strip()
        _deduction_debug_print(
            f"Starting deduction calc for payroll_entry_id={self.pk}, employee={employee_name}, period={payroll_year}-{payroll_month:02d}."
        )

        total_deduction = Decimal(0)
        for deduction in self.pays.deductions.filter(
            created_at__month=payroll_month, created_at__year=payroll_year
        ):
            _deduction_debug_print(
                f"Standard deduction included: id={deduction.id}, type={deduction.deduction_type}, amount={deduction.amount}."
            )
            total_deduction += deduction.amount

        for iou_deduction in self.pays.iou_deductions.filter(
            payday__paydays__month=payroll_month, payday__paydays__year=payroll_year
        ):
            _deduction_debug_print(
                f"IOU deduction included: id={iou_deduction.id}, iou_id={iou_deduction.iou_id}, amount={iou_deduction.amount}."
            )
            total_deduction += iou_deduction.amount
        _deduction_debug_print(
            f"Total calculated deductions for payroll_entry_id={self.pk}: {total_deduction}."
        )
        return total_deduction

    @property
    def total_deductions(self) -> Decimal:
        total = self.calc_deduction + self.employee_health + self.nhf
        _deduction_debug_print(
            f"Total deductions rollup for payroll_entry_id={self.pk}: "
            f"calc_deduction={self.calc_deduction}, employee_health={self.employee_health}, nhf={self.nhf}, total={total}."
        )
        return total

    @property
    def get_netpay(self):
        if not self.pays.net_pay:
            return Decimal(0.0)
        return (
            self.pays.net_pay
            + self.calc_allowance
            - self.calc_deduction
            # - self.employee_health
            # - self.nhf
            # - self.pays.employee_pay.nsitf
        )

    def save(self, *args, **kwargs):
        if self.pays and self.pays.company_id and not self.company_id:
            self.company_id = self.pays.company_id
        self.netpay = self.get_netpay
        super(PayrollEntry, self).save(*args, **kwargs)


class PayManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class PayrollRun(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="payroll_runs",
        null=True,
        blank=True,
        db_index=True,
    )
    name = models.CharField(
        max_length=50,
        default="test",
    )
    slug = models.SlugField(
        max_length=255,
        editable=False,
        db_index=True,
    )  # type: ignore
    paydays = MonthField(
        "Month Value",
        help_text="some help...",
        null=True,
    )
    # month = MonthField()
    payroll_payday = models.ManyToManyField(
        PayrollEntry, related_name="payroll_payday", through="PayrollRunEntry"
    )
    is_active = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)
    objects = PayManager()

    class Meta:
        verbose_name_plural = "Payroll Runs"
        unique_together = (("company", "name"), ("company", "slug"))

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("payroll:pay_period_detail", args=[self.slug])

    def __str__(self):
        return str(self.paydays)

    @property
    def save_month_str(self):

        return utils.convert_month_to_word(str(self.paydays))

    def save(self, *args, **kwargs):
        from django.utils.text import slugify

        first_entry = self.payroll_payday.first() if self.pk else None
        if first_entry and first_entry.company_id and not self.company_id:
            self.company_id = first_entry.company_id

        if not self.slug:
            # Generate slug from paydays field (YYYY-MM format)
            if self.paydays:
                self.slug = slugify(f"pay-period-{self.paydays.strftime('%Y-%m')}")
            else:
                self.slug = slugify(f"pay-period-{uuid.uuid4().hex[:8]}")

        if self.pk and PayrollRun.objects.filter(pk=self.pk, closed=True).exists():
            raise ValidationError("This entry is closed and cannot be edited.")
        # self.paydays_str = self.save_month_str

        super(PayrollRun, self).save(*args, **kwargs)


class PayrollRunEntry(models.Model):
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="payroll_run_entries",
    )
    payroll_entry = models.ForeignKey(
        PayrollEntry,
        on_delete=models.CASCADE,
        related_name="payroll_run_entries",
    )


class IOUDeduction(models.Model):
    iou = models.ForeignKey("IOU", on_delete=models.CASCADE, related_name="deductions")
    employee = models.ForeignKey(
        "EmployeeProfile", on_delete=models.CASCADE, related_name="iou_deductions"
    )
    payday = models.ForeignKey(
        "PayrollRun", on_delete=models.CASCADE, related_name="iou_deductions"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("iou", "payday")

    def __str__(self):
        return f"Deduction of {self.amount} for {self.employee} in {self.payday}"


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
        default=Decimal(0.0),
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
        if self.amount is None or self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})
        if self.tenor is None or self.tenor <= 0:
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


class PublicHoliday(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="public_holidays",
        null=True,
        blank=True,
        db_index=True,
    )
    name = models.CharField(max_length=255)
    date = models.DateField()

    class Meta:
        unique_together = (("company", "date"),)

    def __str__(self):
        return f"{self.name} ({self.date})"


class LeavePolicy(models.Model):
    LEAVE_TYPES = [
        ("CASUAL", "Casual Leave"),
        ("SICK", "Sick Leave"),
        ("ANNUAL", "Annual Leave"),
        ("MATERNITY", "Maternity Leave"),
        ("PATERNITY", "Paternity Leave"),
    ]
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="leave_policies",
        null=True,
        blank=True,
        db_index=True,
    )
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    max_days = models.PositiveIntegerField()

    class Meta:
        unique_together = (("company", "leave_type"),)

    def __str__(self):
        return f"{self.leave_type} - {self.max_days} days"


class LeaveBalance(models.Model):
    employee = models.OneToOneField(
        EmployeeProfile, on_delete=models.CASCADE, related_name="leave_balance"
    )

    year = models.PositiveIntegerField()

    annual_leave = models.PositiveIntegerField(default=10)
    sick_leave = models.PositiveIntegerField(default=5)
    casual_leave = models.PositiveIntegerField(default=3)
    maternity_leave = models.PositiveIntegerField(default=40)
    paternity_leave = models.PositiveIntegerField(default=14)

    class Meta:
        unique_together = ("employee", "year")


class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]

    LEAVE_CHOICES = [
        ("CASUAL", "Casual Leave"),
        ("SICK", "Sick Leave"),
        ("ANNUAL", "Annual Leave"),
        ("MATERNITY", "Maternity Leave"),
        ("PATERNITY", "Paternity Leave"),
    ]

    employee = models.ForeignKey(
        "EmployeeProfile", on_delete=models.CASCADE, related_name="leave_requests"
    )

    leave_type = models.CharField(max_length=20, choices=LEAVE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()

    is_half_day = models.BooleanField(default=False)

    reason = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")

    # HR / Manager controls
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_leaves",
    )

    hr_override = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def calculate_days(self) -> int:
        """
        Returns number of days between two dates (inclusive).
        """
        if self.start_date > self.end_date:
            raise ValueError("Start date cannot be after end date")

        return (self.end_date - self.start_date).days + 1

    @property
    def duration(self):
        if self.start_date > self.end_date:
            return 0

        total_days = 0
        current = self.start_date

        holidays = set(
            PublicHoliday.objects.filter(
                company=self.employee.company,
                date__range=(self.start_date, self.end_date),
            ).values_list("date", flat=True)
        )

        while current <= self.end_date:
            if current.weekday() < 5:
                # and current not in holidays:
                total_days += 1
            current += timedelta(days=1)

        if self.is_half_day:
            return 0.5

        return total_days

    def clean(self):
        super().clean()

        if self.start_date > self.end_date:
            raise ValidationError("End date cannot be before start date.")

        if self.status == "APPROVED" and not self.hr_override:
            balance = get_leave_balance(self.employee, self.start_date.year)
            days = self.duration

            leave_map = {
                "ANNUAL": balance.annual_leave,
                "SICK": balance.sick_leave,
                "CASUAL": balance.casual_leave,
                "MATERNITY": balance.maternity_leave,
                "PATERNITY": balance.paternity_leave,
            }

            if leave_map[self.leave_type] < days:
                raise ValidationError(
                    f"Insufficient {self.leave_type.lower()} leave balance."
                )

    def save(self, *args, **kwargs):
        user = kwargs.pop("user", None)

        is_new = self.pk is None
        previous_status = None

        if not is_new:
            previous_status = LeaveRequest.objects.get(pk=self.pk).status

        self.full_clean()
        super().save(*args, **kwargs)

        # Deduct leave only once
        if self.status == "APPROVED" and previous_status != "APPROVED":
            balance = get_leave_balance(self.employee, self.start_date.year)
            days = self.duration

            if not self.hr_override:
                if self.leave_type == "ANNUAL":
                    balance.annual_leave -= days
                elif self.leave_type == "SICK":
                    balance.sick_leave -= days
                elif self.leave_type == "CASUAL":
                    balance.casual_leave -= days
                elif self.leave_type == "MATERNITY":
                    balance.maternity_leave -= days
                elif self.leave_type == "PATERNITY":
                    balance.paternity_leave -= days

                balance.save()

        # Audit logging
        action = "CREATED" if is_new else f"STATUS_CHANGED_TO_{self.status}"
        LeaveAuditLog.objects.create(
            leave_request=self, action=action, performed_by=user
        )


class LeaveAuditLog(models.Model):
    leave_request = models.ForeignKey(
        LeaveRequest, on_delete=models.CASCADE, related_name="audit_logs"
    )

    action = models.CharField(max_length=100)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )

    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.action} - {self.leave_request}"


def get_leave_balance(employee, year=None):
    if not year:
        year = date.today().year

    balance, _ = LeaveBalance.objects.get_or_create(
        employee=employee,
        year=year,
        defaults={
            "annual_leave": 20,
            "sick_leave": 10,
            "casual_leave": 7,
            "maternity_leave": 90,
            "paternity_leave": 14,
        },
    )
    return balance
