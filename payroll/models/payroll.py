from payroll.workflow_managers import HRWorkflowManager, HRWorkflowQuerySet, SalaryTermsQuerySet
from decimal import Decimal
import uuid
import logging

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.core.validators import MaxValueValidator

from django.utils import timezone  # Import timezone

from calendar import monthrange
from datetime import date, timedelta


from core import settings

logger = logging.getLogger(__name__)

from payroll import utils
from payroll import choices

from monthyear.models import MonthField
from company.tenancy import CompanyOwnedModel
from payroll.models.employee_profile import EmployeeProfile
from payroll.models.utils import SoftDeleteModel


class PayrollManager(models.Manager.from_queryset(SalaryTermsQuerySet)):
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
    health_basis = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("basic", "Basic salary (employee 5% / employer 10%)"),
            (
                "consolidated",
                "Consolidated salary (employee 1.75% / employer 3.25%)",
            ),
        ],
        default="basic",
        help_text=(
            "NHIA/NHIS contribution basis used when no health-insurance tier "
            "matches the employee's basic salary."
        ),
    )
    hmo_monthly_premium = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Negotiated HMO premium per employee per month. When set, the "
            "employer pays the premium minus the employee's statutory share."
        ),
    )
    nhia_applicable = models.BooleanField(
        default=False,
        help_text=(
            "NHIA Act 2022 mandates health insurance for employers with 5 or "
            "more employees; per-employee enrollment is the is_nhif flag."
        ),
    )
    itf_applicable = models.BooleanField(
        default=False,
        help_text=(
            "ITF training levy applies to employers with 5+ staff or annual "
            "turnover of NGN 50m or more (1% of annual payroll, employer-paid)."
        ),
    )
    nsitf_applicable = models.BooleanField(
        default=True,
        help_text=(
            "NSITF Employees' Compensation levy (1% of monthly payroll) is "
            "employer-paid under the ECA 2010."
        ),
    )
    deduct_unpaid_absence = models.BooleanField(
        default=False,
        help_text=(
            "When on, days recorded as absent in the pay period deduct one "
            "daily basic rate (monthly basic / 22) from the payslip."
        ),
    )
    require_timesheet_approval = models.BooleanField(
        default=False,
        help_text=(
            "When on, attendance hours are only payable once the employee's "
            "weekly timesheet has been approved (P2-14). Raw clock data stays "
            "reviewable but does not feed gross pay until certified."
        ),
    )
    leave_allowance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Percentage of annual basic salary paid as leave allowance.",
    )
    ewa_enabled = models.BooleanField(
        default=False,
        help_text="Enable self-service earned wage access (EWA) advances.",
    )
    ewa_advance_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("50.00"),
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("1")), MaxValueValidator(Decimal("100"))],
        help_text=(
            "Max single advance as % of the employee's earned-but-unpaid net "
            "pay in the current pay cycle. Blank uses the 50% rule default."
        ),
    )
    ewa_max_per_cycle = models.PositiveIntegerField(
        default=2,
        null=True,
        blank=True,
        help_text=(
            "Max EWA advances an employee may request per pay cycle. "
            "Blank uses the rule default of 2."
        ),
    )
    ewa_min_days_between = models.PositiveIntegerField(
        default=7,
        null=True,
        blank=True,
        help_text=(
            "Minimum days an employee must wait between EWA advances. "
            "Blank uses the rule default of 7."
        ),
    )
    ewa_min_take_home_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("50.00"),
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("1")), MaxValueValidator(Decimal("100"))],
        help_text=(
            "Take-home guardrail: outstanding advances may not exceed this % "
            "of net pay. Blank uses the 50% rule default."
        ),
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
    water_rate_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("75000.00"),
        help_text=(
            "Basic-salary threshold governing the water-rate deduction. "
            "At or below this, water_rate_low applies; above it, water_rate_high."
        ),
    )
    water_rate_low = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("150.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Monthly water-rate deduction when basic salary is at/below threshold.",
    )
    water_rate_high = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("200.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Monthly water-rate deduction when basic salary is above threshold.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Payroll Setting"
        verbose_name_plural = "Company Payroll Settings"

    def __str__(self):
        return f"{self.company} payroll settings"

    def clean(self):
        super().clean()

        total = (
            (self.basic_percentage or Decimal("0"))
            + (self.housing_percentage or Decimal("0"))
            + (self.transport_percentage or Decimal("0"))
        )
        if total <= Decimal("0"):
            raise ValidationError(
                "Basic, housing, and transport percentages must sum to more than 0."
            )
        if total > Decimal("100"):
            raise ValidationError(
                "Basic, housing, and transport percentages cannot exceed 100% in total."
            )

        # Nigeria-focused statutory guardrails (PRA/NHF baseline).
        if self.pension_employee_percentage < Decimal("8.00"):
            raise ValidationError(
                {
                    "pension_employee_percentage": (
                        "Employee pension contribution must be at least 8% "
                        "for Nigeria payroll baseline."
                    )
                }
            )
        if self.pension_employer_percentage < Decimal("10.00"):
            raise ValidationError(
                {
                    "pension_employer_percentage": (
                        "Employer pension contribution must be at least 10% "
                        "for Nigeria payroll baseline."
                    )
                }
            )
        if self.nhf_percentage < Decimal("2.50"):
            raise ValidationError(
                {
                    "nhf_percentage": (
                        "NHF contribution must be at least 2.5% for Nigeria payroll baseline."
                    )
                }
            )

        if not self.pays_thirteenth_month and self.thirteenth_month_percentage != Decimal(
            "0"
        ):
            self.thirteenth_month_percentage = Decimal("0")

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


class StatutoryRateVersion(models.Model):
    """
    Effective-dated national statutory rate schedule.

    Rates are resolved by effective_date so a payroll run is computed against
    the regime in force for its pay period. PayNest ships the pre-Nigeria Tax
    Act PITA bands (for retrospective runs) and the Nigeria Tax Act 2025
    regime, and admins can add future versions without code changes.
    """

    name = models.CharField(max_length=120)
    effective_date = models.DateField(unique=True, db_index=True)
    # JSON list of [upper_threshold_or_null, rate_percent] as integers, e.g.
    # [[300000, 7], [600000, 11], [None, 24]]. The final band is open-ended.
    paye_bands = models.JSONField(default=list)
    minimum_wage_monthly = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("70000.00"),
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Statutory Rate Version"
        verbose_name_plural = "Statutory Rate Versions"
        ordering = ("effective_date",)

    def __str__(self):
        return f"{self.name} ({self.effective_date})"

    @classmethod
    def for_date(cls, as_of=None):
        """Latest version effective on or before ``as_of`` (default: today)."""
        target = as_of or timezone.localdate()
        return (
            cls.objects.filter(effective_date__lte=target)
            .order_by("-effective_date")
            .first()
        )


class RemittanceRecord(CompanyOwnedModel):
    """
    Tracks whether a statutory remittance/filing for a pay period has been
    made. Rows are created on demand from the compliance calendar; the due
    dates and amounts themselves are computed from payroll runs by
    ``payroll.services.compliance``.
    """

    OBLIGATION_CHOICES = [
        ("paye", "PAYE"),
        ("pension", "Pension"),
        ("nhf", "NHF"),
        ("nhia", "NHIA"),
        ("paye_annual", "PAYE Annual Return"),
        ("itf", "ITF"),
        ("nsitf", "NSITF"),
    ]

    # ``company`` field is inherited-or-overridden from CompanyOwnedModel; the
    # explicit field keeps the reverse relation name.
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="remittance_records",
        db_index=True,
    )
    obligation = models.CharField(max_length=20, choices=OBLIGATION_CHOICES)
    period = MonthField(
        "Pay period",
        help_text="Pay period the remittance relates to (mirrors PayrollRun.paydays).",
        null=True,
    )
    remitted_on = models.DateField(
        null=True,
        blank=True,
        help_text="Date the remittance/filing was completed; empty means not yet done.",
    )
    reference = models.CharField(max_length=120, blank=True, help_text="Optional remittance reference.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("company", "obligation", "period"),)
        ordering = ("period", "obligation")
        verbose_name = "Remittance Record"
        verbose_name_plural = "Remittance Records"

    def __str__(self):
        return f"{self.company} {self.get_obligation_display()} {self.period}"

    @property
    def is_remitted(self) -> bool:
        return self.remitted_on is not None


class Payroll(models.Model):
    class Meta:
        base_manager_name = "all_objects"

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
    nhf_scheme = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("none", "Not contributing"),
            ("voluntary", "Voluntary (private sector)"),
            ("compulsory", "Compulsory (public sector)"),
        ],
        default="none",
        help_text=(
            "NHF classification after the 2023 amendment: compulsory for "
            "public-sector employees, voluntary for private-sector employees."
        ),
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
    itf = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        default=Decimal(0.0),
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=10,
        choices=choices.STATUS,
        default="active",
    )
    objects = PayrollManager()
    all_objects = SalaryTermsQuerySet.as_manager()

    def __str__(self):
        return str(self.basic_salary)

    @property
    def get_annual_gross(self):
        return self.basic_salary * 12

    @property
    def get_nsitf(self):
        # NSITF Employees' Compensation: 1% of monthly basic salary, employer-funded.
        return self.basic_salary * Decimal(1) / Decimal(100)

    @property
    def get_itf(self):
        """ITF training levy: 1% of annual gross, employer-funded, if applicable."""
        return self.gross_income * Decimal(1) / Decimal(100)

    def recompute_statutory(self, as_of=None):
        """
        Recompute the statutory fields against the rate version in force on
        ``as_of`` (e.g. a retroactive pay run's paydays month).

        This updates the in-memory values only; callers persist with
        ``save(update_fields=[...])`` so the salary structure (basic, housing,
        transport) configured for the current regime is left untouched.
        """
        cents = Decimal("0.01")
        self.pension_employee = utils.get_pension_employee(self, as_of=as_of).quantize(
            cents
        )
        self.pension_employer = utils.get_pension_employer(self, as_of=as_of).quantize(
            cents
        )
        self.pension = utils.get_pension(self, as_of=as_of).quantize(cents)
        self.nhf = utils.calc_housing(self, as_of=as_of).quantize(cents)
        self.taxable_income = utils.calculate_taxable_income(self).quantize(cents)
        self.payee = utils.get_payee(self, as_of=as_of).quantize(cents)
        return self

    def save(self, *args, **kwargs):
        from approvals.guards import approved_context
        if self.pk and not approved_context(self.company_id):
            previous = type(self)._base_manager.get(pk=self.pk)
            salary_inputs = ('basic_salary','is_housing','is_nhif','nhf_scheme')
            if any(getattr(previous,name) != getattr(self,name) for name in salary_inputs) and EmployeeProfile._base_manager.filter(employee_pay_id=self.pk).exists():
                raise ValidationError('Assigned salary terms cannot be changed directly. Submit a salary-change proposal.')
        # Keep the NHF scheme and the legacy is_housing switch in sync so both
        # existing rows and the new classification flag drive the deduction.
        if self.nhf_scheme == "none" and self.is_housing:
            self.nhf_scheme = "voluntary"
        elif self.nhf_scheme != "none":
            self.is_housing = True

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
        self.nsitf = utils.get_nsitf(self)
        self.itf = utils.get_itf(self)
        self.taxable_income = utils.calculate_taxable_income(self)
        self.payee = utils.get_payee(self)  # noqa: F405
        self.water_rate = utils.get_water_rate(self)  # noqa: F405

        super(Payroll, self).save(*args, **kwargs)


class SalaryHistory(models.Model):
    employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="salary_history",
    )
    salary_config = models.ForeignKey(
        Payroll,
        on_delete=models.PROTECT,
        related_name="employee_history",
    )
    effective_date = models.DateField(default=timezone.localdate)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="salary_changes",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_salary_changes",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-id"]
        unique_together = ("employee", "salary_config", "effective_date")

    def __str__(self):
        return f"{self.employee} salary from {self.effective_date}"


class RetroPayDelta(models.Model):
    """Audit trail for a backdated salary change caught up in a later period.

    When a salary change is approved with an effective date in a past, already
    paid period, the employee is owed the difference between what they were
    paid under the old config and what the new config would have paid, for
    each month between the effective date and the current period. This model
    records that catch-up as an explicit, reversible adjustment rather than
    silently mutating history.

    ``monthly_delta`` is the canonical net-pay difference (``payroll_calc``)
    between the new and old configs; ``total_delta`` is that times
    ``months_owed``. Reversal creates a matching negative adjustment.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPLIED = "applied", "Applied"
        REVERSED = "reversed", "Reversed"

    employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="retro_pay_deltas",
    )
    from_config = models.ForeignKey(
        Payroll,
        on_delete=models.PROTECT,
        related_name="+",
    )
    to_config = models.ForeignKey(
        Payroll,
        on_delete=models.PROTECT,
        related_name="+",
    )
    effective_date = models.DateField(
        help_text="Date the new salary takes effect (may be backdated)."
    )
    period = MonthField(
        "Catch-up pay period",
        help_text="Pay period the delta is paid in (the current run's month).",
    )
    months_owed = models.PositiveIntegerField(
        help_text="Whole months between the effective date and the catch-up period."
    )
    monthly_delta = models.DecimalField(max_digits=12, decimal_places=2)
    total_delta = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    allowance = models.ForeignKey(
        "Allowance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retro_pay_deltas",
        help_text="The allowance created to pay this delta (reversal negates it).",
    )
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retro_pay_deltas_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Retro Pay Delta"
        verbose_name_plural = "Retro Pay Deltas"

    def __str__(self):
        return f"Retro {self.employee} {self.period} ({self.total_delta})"


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
    source_leave_request = models.OneToOneField(
        "LeaveRequest",
        on_delete=models.SET_NULL,
        related_name="processed_leave_allowance",
        null=True,
        blank=True,
        help_text="Leave request that generated this automatic leave allowance.",
    )

    class Meta:
        verbose_name_plural = "Allowances"


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


class PayrollEntryQuerySet(models.QuerySet):
    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValidationError("Payroll records cannot be replaced through bulk conflict updates.")
        return super().bulk_create(objs, **kwargs)

    def _assert_editable(self):
        entry_ids = list(self.values_list("pk", flat=True))
        run_ids = PayrollRunEntry.objects.filter(
            payroll_entry_id__in=entry_ids
        ).values_list("payroll_run_id", flat=True)
        runs = PayrollRun.all_objects.select_for_update().filter(
            pk__in=run_ids
        ).order_by("pk")
        if any(run.is_locked for run in runs):
            raise ValidationError("Locked payroll amounts cannot be changed or deleted.")

    @transaction.atomic
    def update(self, **kwargs):
        self._assert_editable()
        return super().update(**kwargs)

    @transaction.atomic
    def delete(self):
        self._assert_editable()
        return super().delete()


class PayrollEntryManager(models.Manager.from_queryset(PayrollEntryQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")


class PayrollEntry(models.Model):
    class Meta:
        base_manager_name = "all_objects"

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
    all_objects = PayrollEntryQuerySet.as_manager()

    def __str__(self):
        return self.pays.first_name

    @property
    def calc_allowance(self):
        if not self.pk:
            return Decimal(0)

        # New implementation: Sum allowances for the employee within the payroll period
        payroll_run_entry = self.payroll_run_entries.select_related(
            "payroll_run"
        ).first()
        if not payroll_run_entry:
            return Decimal(0)

        payroll_month = payroll_run_entry.payroll_run.paydays.month
        payroll_year = payroll_run_entry.payroll_run.paydays.year
        month_start = date(payroll_year, payroll_month, 1)
        month_end = date(
            payroll_year,
            payroll_month,
            monthrange(payroll_year, payroll_month)[1],
        )

        total_allowance = Decimal(0)
        period_allowances = self.pays.allowances.filter(
            models.Q(
                source_leave_request__isnull=True,
                created_at__month=payroll_month,
                created_at__year=payroll_year,
            )
            | models.Q(
                source_leave_request__isnull=False,
                source_leave_request__start_date__lte=month_end,
                source_leave_request__end_date__gte=month_start,
            )
        )
        # Automatic LV is annual-leave only; ordinary manually entered LV
        # remains an independent payroll allowance.
        period_allowances=period_allowances.exclude(
            models.Q(allowance_type='LV',source_leave_request__isnull=False)
            & ~models.Q(source_leave_request__leave_type='ANNUAL')
        )
        # Leave approval pays its source-backed LV separately. Keeping that
        # allowance record is audit history, not another payroll entitlement.
        from django.contrib.contenttypes.models import ContentType
        from accounting.models import Journal
        paid_leave_ids = set(Journal.objects.filter(
            company=self.pays.company,
            content_type=ContentType.objects.get_for_model(Allowance),
            object_id__in=period_allowances.filter(allowance_type='LV',source_leave_request__isnull=False).values_list('pk',flat=True),
            status=Journal.JournalStatus.POSTED,
            description__startswith='Leave allowance paid to',
        ).values_list('object_id',flat=True))
        for allowance in period_allowances:
            if allowance.pk in paid_leave_ids:
                continue
            total_allowance += allowance.amount

        total_allowance += self._get_auto_leave_allowance(
            month_start=month_start,
            month_end=month_end,
        )
        total_allowance += self._get_auto_thirteenth_month_allowance(payroll_month)
        # Approved overtime for the period feeds gross pay (P1-7).
        total_allowance += self._get_auto_overtime_allowance(
            month_start=month_start,
            month_end=month_end,
        )

        return total_allowance

    def _get_auto_overtime_allowance(self, month_start: date, month_end: date) -> Decimal:
        """Approved ``OvertimeEntry`` pay for the pay period.

        Attendance previously fed no payroll figures at all; this pulls the
        already-computed ``overtime_service.get_overtime_allowance`` (weighted
        hours x hourly basic rate) into the payslip. Pending/rejected entries
        and entries dated outside the period are excluded.
        """
        if not self.pays or not self.pays.employee_pay_id:
            return Decimal("0.00")
        from payroll.services.overtime_service import get_overtime_allowance

        return get_overtime_allowance(self.pays, month_start, month_end)

    def _get_company_payroll_setting(self):
        company = self.company or self.pays.company
        if not company:
            return None
        return CompanyPayrollSetting.objects.filter(company=company).first()

    def _get_auto_leave_allowance(self, month_start: date, month_end: date) -> Decimal:
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

        is_on_approved_leave = self.pays.leave_requests.filter(
            status="APPROVED",
            leave_type="ANNUAL",
            start_date__lte=month_end,
            end_date__gte=month_start,
            processed_leave_allowance__isnull=True,
        ).exists()
        if not is_on_approved_leave:
            return Decimal("0.00")

        annual_basic_salary = Decimal(payroll.basic_salary or Decimal("0.00")) * Decimal(
            "12"
        )
        return (annual_basic_salary * leave_allowance_percentage) / Decimal("100")

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
    def calc_standard_deduction(self):
        if not self.pk:
            _deduction_debug_print(
                f"PayrollEntry has no PK yet for employee={getattr(self.pays, 'id', None)}; returning 0."
            )
            return Decimal(0)

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
        return total_deduction

    @property
    def calc_iou_deduction(self):
        if not self.pk:
            return Decimal(0)

        payroll_run_entry = self.payroll_run_entries.select_related(
            "payroll_run"
        ).first()
        if not payroll_run_entry:
            return Decimal(0)

        payroll_month = payroll_run_entry.payroll_run.paydays.month
        payroll_year = payroll_run_entry.payroll_run.paydays.year
        total_iou_deduction = Decimal(0)

        for iou_deduction in self.pays.iou_deductions.filter(
            payday__paydays__month=payroll_month, payday__paydays__year=payroll_year
        ):
            _deduction_debug_print(
                f"IOU deduction included: id={iou_deduction.id}, iou_id={iou_deduction.iou_id}, amount={iou_deduction.amount}."
            )
            total_iou_deduction += iou_deduction.amount
        return total_iou_deduction

    @property
    def calc_deduction(self):
        total_deduction = (
            self.calc_standard_deduction
            + self.calc_iou_deduction
            + self.calc_absence_deduction
        )
        _deduction_debug_print(
            f"Total calculated deductions for payroll_entry_id={self.pk}: {total_deduction}."
        )
        return total_deduction

    @property
    def calc_absence_deduction(self) -> Decimal:
        """Unpaid-absence days in the run period (company opt-in, P1-7).

        Attendance previously never reached the payroll path; when the company
        enables ``deduct_unpaid_absence``, each absent day in the pay period
        deducts one daily basic rate (monthly basic / 22).
        """
        setting = self._get_company_payroll_setting()
        if setting is None or not setting.deduct_unpaid_absence:
            return Decimal("0.00")
        payroll_run_entry = self.payroll_run_entries.select_related(
            "payroll_run"
        ).first()
        if not payroll_run_entry:
            return Decimal("0.00")
        run = payroll_run_entry.payroll_run
        from calendar import monthrange

        from payroll.services.attendance_pay import absence_deduction_for

        month_start = date(run.paydays.year, run.paydays.month, 1)
        month_end = date(
            run.paydays.year,
            run.paydays.month,
            monthrange(run.paydays.year, run.paydays.month)[1],
        )
        return absence_deduction_for(self.pays, month_start, month_end)

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
        from payroll.services.payroll_calc import entry_net_pay

        return entry_net_pay(
            self.pays.net_pay,
            allowances_monthly=self.calc_allowance,
            deductions_monthly=self.calc_deduction,
        )

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.pk:
            type(self).all_objects.filter(pk=self.pk)._assert_editable()
        if self.pays and self.pays.company_id and not self.company_id:
            self.company_id = self.pays.company_id
        self.netpay = self.get_netpay
        super(PayrollEntry, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return type(self).all_objects.filter(pk=self.pk).delete()


class PayrollRunQuerySet(models.QuerySet):
    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValidationError("Payroll records cannot be replaced through bulk conflict updates.")
        from approvals.guards import guard_source_save
        objs = list(objs)
        for obj in objs:
            guard_source_save(obj)
        return super().bulk_create(objs, **kwargs)

    def _assert_unlocked(self):
        if any(run.is_locked for run in self.select_for_update().order_by("pk")):
            raise ValidationError("Locked payroll runs cannot be changed or deleted.")

    @transaction.atomic
    def update(self, **kwargs):
        if {"status", "closed"} & set(kwargs):
            raise ValidationError("Payroll lifecycle changes must use save().")
        self._assert_unlocked()
        return super().update(**kwargs)

    @transaction.atomic
    def delete(self):
        self._assert_unlocked()
        return super().delete()


class PayManager(models.Manager.from_queryset(PayrollRunQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class PayrollRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CALCULATED = "calculated", "Calculated"
        REVIEWED = "reviewed", "Reviewed"
        APPROVED = "approved", "Approved"
        LOCKED = "locked", "Locked"
        PAID = "paid", "Paid"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="payroll_runs",
        null=True,
        blank=True,
        db_index=True,
    )
    requested_by = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='requested_payroll_runs')
    currency = models.CharField(max_length=3, default='NGN')
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
    payment_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Actual date salaries were paid for this run. When set, statutory "
            "deadlines that run from payment (e.g. pension remittance, due "
            "within 7 working days) anchor to this date instead of the period start."
        ),
    )
    # month = MonthField()
    payroll_payday = models.ManyToManyField(
        PayrollEntry, related_name="payroll_payday", through="PayrollRunEntry"
    )
    is_active = models.BooleanField(default=False)
    closed = models.BooleanField(
        default=False,
        help_text="Legacy lock flag. Derived from status (LOCKED/PAID). Use status transitions instead.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        help_text="Payroll lifecycle: Draft → Calculated → Reviewed → Approved → Locked → Paid.",
    )

    class RunType(models.TextChoices):
        REGULAR = "regular", "Regular"
        OFF_CYCLE = "off_cycle", "Off-cycle"
        TERMINATION = "termination", "Termination"

    run_type = models.CharField(
        max_length=20,
        choices=RunType.choices,
        default=RunType.REGULAR,
        db_index=True,
        help_text=(
            "Regular runs are the monthly cycle and may not overlap another "
            "regular run for the same period. Off-cycle and termination runs "
            "pay corrections or final settlements outside the cycle."
        ),
    )
    reason_code = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text=(
            "Reason for an off-cycle or termination run (e.g. correction, "
            "bonus, final_settlement). Empty for regular runs."
        ),
    )
    objects = PayManager()
    all_objects = PayrollRunQuerySet.as_manager()

    class Meta:
        base_manager_name = "all_objects"
        verbose_name_plural = "Payroll Runs"
        unique_together = (("company", "name"), ("company", "slug"))

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("payroll:pay_period_detail", args=[self.slug])

    def __str__(self):
        return str(self.paydays)

    @property
    def is_locked(self):
        return self.status in (self.Status.LOCKED, self.Status.PAID) or self.closed

    _ALLOWED_TRANSITIONS = {
        Status.DRAFT: (Status.CALCULATED,),
        Status.CALCULATED: (Status.REVIEWED, Status.DRAFT),
        Status.REVIEWED: (Status.APPROVED, Status.CALCULATED),
        Status.APPROVED: (Status.LOCKED, Status.REVIEWED),
        Status.LOCKED: (Status.PAID,),
        Status.PAID: (),
    }

    def transition_to(self, new_status, **save_kwargs):
        allowed = self._ALLOWED_TRANSITIONS.get(self.status, ())
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot transition payroll run from {self.status} to {new_status}."
            )
        if new_status == self.Status.REVIEWED:
            # Pre-flight readiness gate (Gusto blockers analogue): block the
            # CALCULATED -> REVIEWED step until every typed blocker is cleared.
            from payroll.services.preflight import run_preflight

            run_preflight(self).raise_if_blocked()
        previous_status = self.status
        self.status = new_status
        if new_status in (self.Status.LOCKED, self.Status.PAID):
            self.closed = True
        save_kwargs.setdefault("update_fields", ["status", "closed"])
        self.save(**save_kwargs)
        # Fan out a signed webhook so integrators see run state live (P1-9).
        from webhooks.services import emit_event

        emit_event(
            self.company,
            "payroll.run.state_changed",
            {
                "run_id": str(self.pk),
                "slug": self.slug,
                "name": self.name,
                "from_status": previous_status,
                "to_status": self.status,
                "paydays": self.paydays.isoformat() if self.paydays else None,
            },
        )

    def mark_calculated(self, **kw):
        return self.transition_to(self.Status.CALCULATED, **kw)

    def mark_reviewed(self, **kw):
        return self.transition_to(self.Status.REVIEWED, **kw)

    def approve(self, **kw):
        return self.transition_to(self.Status.APPROVED, **kw)

    def lock(self, **kw):
        return self.transition_to(self.Status.LOCKED, **kw)

    def mark_paid(self, **kw):
        return self.transition_to(self.Status.PAID, **kw)

    @property
    def save_month_str(self):

        return utils.convert_month_to_word(str(self.paydays))

    def _validate_run_type(self):
        """Enforce run-type rules for off-cycle and correction payrolls.

        A non-regular run must carry a reason code. Same-period re-runs of a
        *regular* run are deliberately still allowed: the product treats a
        re-run as a supported flow (report period lists dedupe repeated
        paydays — see ``payroll.tests_tax``). Off-cycle and termination runs
        add reason-coded corrections without touching the regular cycle.
        """
        if self.run_type != self.RunType.REGULAR and not self.reason_code.strip():
            raise ValidationError(
                "An off-cycle or termination run needs a reason code."
            )

    @transaction.atomic
    def save(self, *args, **kwargs):
        from django.utils.text import slugify

        self._validate_run_type()
        first_entry = self.payroll_payday.first() if self.pk else None
        if first_entry and first_entry.company_id and not self.company_id:
            self.company_id = first_entry.company_id

        if not self.slug:
            # Generate slug from paydays field (YYYY-MM format). Non-regular
            # runs share the period with the cycle, so their slug carries the
            # run type and a short unique suffix to satisfy (company, slug).
            if self.paydays:
                base = f"pay-period-{self.paydays.strftime('%Y-%m')}"
                if self.run_type != self.RunType.REGULAR:
                    base = f"{base}-{self.run_type}-{uuid.uuid4().hex[:8]}"
                self.slug = slugify(base)
            else:
                self.slug = slugify(f"pay-period-{uuid.uuid4().hex[:8]}")

        # Keep legacy `closed` flag in sync with lifecycle status.
        if self.status in (self.Status.LOCKED, self.Status.PAID):
            self.closed = True
        elif self.closed and self.status == self.Status.DRAFT:
            # Old UI flips `closed` directly; map it to LOCKED for auditability.
            self.status = self.Status.LOCKED

        update_fields = kwargs.get("update_fields")
        if self.pk:
            persisted = PayrollRun.all_objects.select_for_update().get(pk=self.pk)
            if persisted.is_locked:
                if not (
                    update_fields
                    and set(update_fields) <= {"status", "closed", "payment_date"}
                ):
                    raise ValidationError("This entry is closed and cannot be edited.")
                allowed_statuses = {persisted.status}
                if persisted.status == self.Status.LOCKED:
                    allowed_statuses.add(self.Status.PAID)
                if not self.closed or self.status not in allowed_statuses:
                    raise ValidationError("A locked or paid payroll run cannot be reopened.")
        if update_fields and {"status", "closed"} & set(update_fields):
            kwargs["update_fields"] = set(update_fields) | {"status", "closed"}

        from approvals.guards import guard_source_save
        guard_source_save(self, update_fields=kwargs.get("update_fields"))
        super(PayrollRun, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return type(self).all_objects.filter(pk=self.pk).delete()


class PayrollRunEntryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Payroll membership changes must use save().")

    @transaction.atomic
    def delete(self):
        run_ids = list(self.values_list("payroll_run_id", flat=True))
        runs = PayrollRun.all_objects.select_for_update().filter(pk__in=run_ids)
        if any(run.is_locked for run in runs):
            raise ValidationError("Locked payroll membership cannot be deleted.")
        return super().delete()

    @transaction.atomic
    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValidationError("Workflow records cannot be replaced through bulk conflict updates.")
        objs = list(objs)
        run_ids = {obj.payroll_run_id for obj in objs}
        list(PayrollRun.all_objects.select_for_update().filter(pk__in=run_ids).order_by("pk"))
        members = set()
        for obj in objs:
            obj.full_clean()
            key = (obj.payroll_run_id, obj.payroll_entry.pays_id)
            if key in members:
                raise ValidationError("An employee can only appear once in a payroll run.")
            members.add(key)
        return super().bulk_create(objs, **kwargs)


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

    objects = PayrollRunEntryQuerySet.as_manager()

    class Meta:
        base_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "payroll_entry"],
                name="unique_payroll_run_entry",
            )
        ]

    def clean(self):
        super().clean()
        run = PayrollRun.all_objects.get(pk=self.payroll_run_id)
        entry = self.payroll_entry
        if not run.company_id or entry.company_id != run.company_id or entry.pays.company_id != run.company_id:
            raise ValidationError("Payroll run and employee must belong to the same company.")
        run_ids = {run.pk}
        if self.pk:
            previous_run = type(self).objects.filter(pk=self.pk).values_list("payroll_run_id", flat=True).first()
            if previous_run:
                run_ids.add(previous_run)
        if any(item.is_locked for item in PayrollRun.all_objects.filter(pk__in=run_ids)):
            raise ValidationError("Locked payroll membership cannot be changed.")
        if type(self).objects.filter(
            payroll_run_id=run.pk, payroll_entry__pays_id=entry.pays_id
        ).exclude(pk=self.pk).exists():
            raise ValidationError("An employee can only appear once in a payroll run.")

    @transaction.atomic
    def save(self, *args, **kwargs):
        run_ids = {self.payroll_run_id}
        if self.pk:
            previous_run = type(self).objects.filter(pk=self.pk).values_list("payroll_run_id", flat=True).first()
            if previous_run:
                run_ids.add(previous_run)
        list(PayrollRun.all_objects.select_for_update().filter(pk__in=run_ids).order_by("pk"))
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return type(self).objects.filter(pk=self.pk).delete()


class PayslipEmailJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SENT = "sent", "Sent"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="payslip_email_jobs",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    celery_task_id = models.CharField(max_length=255, blank=True)
    sent_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    skipped_details = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    queued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-queued_at",)
        indexes = [
            models.Index(fields=["status", "queued_at"]),
            models.Index(fields=["payroll_run", "status"]),
        ]

    def __str__(self):
        return f"Payslip emails for {self.payroll_run} ({self.get_status_display()})"

    def enqueue(self):
        from payroll.tasks.payslip_tasks import send_payslips_for_payroll_run_task

        result = send_payslips_for_payroll_run_task.apply_async(
            args=[self.payroll_run_id, self.id],
            queue="notifications_normal",
        )
        self.status = self.Status.QUEUED
        self.celery_task_id = result.id or ""
        self.error_message = ""
        self.save(update_fields=["status", "celery_task_id", "error_message", "updated_at"])
        return result


class LeaveAllowanceEmailJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    leave_request = models.OneToOneField(
        "LeaveRequest",
        on_delete=models.CASCADE,
        related_name="allowance_email_job",
    )
    allowance = models.OneToOneField(
        Allowance,
        on_delete=models.CASCADE,
        related_name="leave_allowance_email_job",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    queued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-queued_at",)
        indexes = [
            models.Index(fields=["status", "queued_at"]),
            models.Index(fields=["leave_request", "status"]),
        ]

    def __str__(self):
        return f"Leave allowance slip for leave #{self.leave_request_id} ({self.get_status_display()})"

    def enqueue(self):
        from payroll.tasks.leave_allowance_tasks import send_leave_allowance_slip_task

        result = send_leave_allowance_slip_task.apply_async(
            args=[self.leave_request_id, self.id],
            queue="notifications_normal",
        )
        self.status = self.Status.QUEUED
        self.celery_task_id = result.id or ""
        self.error_message = ""
        self.save(update_fields=["status", "celery_task_id", "error_message", "updated_at"])
        return result


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
    class Meta:
        base_manager_name = "all_objects"

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="created_iou_requests")

    objects = HRWorkflowManager()
    all_objects = HRWorkflowQuerySet.as_manager()

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
    repayment_deduction_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("30.00"),
        validators=[MinValueValidator(Decimal("1.00")), MaxValueValidator(Decimal("100.00"))],
        help_text="Percentage of monthly salary to deduct for IOU repayment.",
    )
    is_ewa = models.BooleanField(
        default=False,
        help_text=(
            "True for earned-wage-access advances, which are repaid from the "
            "next pay cycle and governed by the company EWA policy."
        ),
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
    def repaid_amount(self):
        if self.status == 'PAID' and self.payment_method == 'DIRECT_PAYMENT':
            return self.total_amount
        paid = self.deductions.filter(models.Q(payday__closed=True) | models.Q(payday__status__in=['locked','paid'])).aggregate(total=models.Sum('amount')).get('total')
        return paid or Decimal('0.00')

    @property
    def outstanding_amount(self):
        return max(self.total_amount - self.repaid_amount, Decimal("0.00"))

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
        if self.interest_rate is not None and self.interest_rate < 0:
            raise ValidationError({"interest_rate": "Interest cannot be negative."})

    def delete(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_delete
        guard_delete(self)
        return super().delete(*args, **kwargs)

    @transaction.atomic
    def save(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_requester
        guard_requester(self, kwargs.get("update_fields"))
        from payroll.services.hr_workflow import guard_state
        action = "iou.settle" if self.status == "PAID" else "iou.approve"
        guard_state(self, action, {"APPROVED", "REJECTED", "PAID"}, ("approved_at",), update_fields=kwargs.get("update_fields"))
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if previous and previous.status in {"APPROVED", "PAID"}:
            guard_state(self, action, set(), ("amount", "tenor", "interest_rate", "repayment_deduction_percentage", "payment_method", "employee_id_id", "approved_at", "due_date"), update_fields=kwargs.get("update_fields"))
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


class PublicHoliday(CompanyOwnedModel):
    # ``company`` field is inherited-or-overridden from CompanyOwnedModel; the
    # explicit field keeps the reverse relation name and the nullable legacy
    # semantics.
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
    # Fallback catalogue for company-less (default) policies. Active policies
    # resolve their types through ``LeaveType`` (see below); this list remains
    # only so legacy rows and the ``LeaveLedgerEntry``/``LeaveRequest`` choice
    # fields keep validating when no ``LeaveType`` row exists yet.
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
    statutory_min_days = models.PositiveIntegerField(default=6)
    carryover_days = models.PositiveIntegerField(default=0)
    carryover_expires_after_days = models.PositiveIntegerField(default=90)

    class Meta:
        unique_together = (("company", "leave_type"),)

    def __str__(self):
        return f"{self.leave_type} - {self.max_days} days"

    def clean(self):
        super().clean()
        if self.leave_type == "ANNUAL" and self.max_days < self.statutory_min_days:
            raise ValidationError("Annual leave cannot be below the statutory minimum.")


class LeaveType(models.Model):
    """Company-configurable leave catalogue (P2-12, gap #12).

    Replaces the fixed five-type set that was hard-coded in two places. Each
    company owns its own ``LeaveType`` rows; the Nigerian statutory defaults
    (annual/sick/casual/maternity/paternity) are seeded per company on first
    use via :func:`payroll.services.leave_type_service.ensure_default_leave_types`.

    ``code`` is the stable identifier used in ``LeaveRequest.leave_type`` and
    ``LeaveLedgerEntry.leave_type``; ``name`` is the human label.
    """

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="leave_types",
        null=True,
        blank=True,
        db_index=True,
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=60)
    # Entitlement granted per year, in days. This is the source of truth that
    # ``get_leave_balance`` seeds ``LeaveBalance`` from (reconciles the old
    # 10/5/3/40/14 vs 20/10/7/90/14 conflict in favour of the latter).
    default_days = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0")
    )
    is_paid = models.BooleanField(default=True)
    # Whether requests of this type may be taken in half-day increments.
    allows_half_day = models.BooleanField(default=False)
    # Whether unused days of this type can be encashed (paid out) at settlement.
    encashable = models.BooleanField(default=False)
    # Encashment values one unused day at settlement, as a fraction of a daily
    # wage (1.0 == a full day's pay). Only meaningful when ``encashable``.
    encashment_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.00")
    )
    # Carry-over of unused days into the next year, as a fraction of the
    # entitlement (0 == no carry-over). Applied by the annual carry-over job.
    carryover_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0")
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("company", "code"),)
        ordering = ["code"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        super().clean()
        if self.default_days < 0:
            raise ValidationError("Default days cannot be negative.")
        if self.encashable and self.encashment_rate < 0:
            raise ValidationError("Encashment rate cannot be negative.")
        if not (Decimal("0") <= self.carryover_rate <= Decimal("1")):
            raise ValidationError("Carry-over rate must be between 0 and 1.")


def leave_type_choices(company=None):
    """Choice tuples for the fixed ``leave_type`` fields.

    Prefers the company's active ``LeaveType`` rows; falls back to the legacy
    five-type catalogue for company-less contexts and pre-migration data.
    """
    qs = LeaveType.objects.filter(is_active=True)
    if company is not None:
        company_types = list(qs.filter(company=company).values_list("code", "name"))
        if company_types:
            return company_types
    global_types = list(qs.filter(company__isnull=True).values_list("code", "name"))
    if global_types:
        return global_types
    return LeavePolicy.LEAVE_TYPES


class LeaveBlackoutPeriod(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="leave_blackout_periods",
    )
    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    department = models.ForeignKey(
        "payroll.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="leave_blackout_periods",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date", "name"]

    def clean(self):
        super().clean()
        if self.end_date < self.start_date:
            raise ValidationError("Blackout end date cannot be before start date.")

    def __str__(self):
        return self.name


class LeaveLedgerEntry(models.Model):
    """Append-only leave event, summed at read time (Frappe/BambooHR ledger).

    Gap #6: balances are derived by summing these events rather than trusting a
    mutable counter. ``LeaveBalance`` is retained as a read model materialised
    from the ledger, but the ledger is the source of truth.

    Event types:
        ACCRUAL       — the annual entitlement granted for a year.
        USAGE         — days consumed by an approved leave request.
        CARRY_FORWARD — days carried from the previous year.
        EXPIRY        — carried-forward days that lapsed.
        ADJUSTMENT    — manual correction (positive or negative).

    ``days`` is signed: accruals/carry-forward/positive adjustments are +,
    usage and expiry are recorded negative so a balance is a plain ``Sum``.
    """

    class EventType(models.TextChoices):
        ACCRUAL = "accrual", "Accrual"
        USAGE = "usage", "Usage"
        CARRY_FORWARD = "carry_forward", "Carry Forward"
        EXPIRY = "expiry", "Expiry"
        ADJUSTMENT = "adjustment", "Adjustment"

    employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="leave_ledger_entries",
    )
    leave_type = models.CharField(max_length=20)
    event_type = models.CharField(
        max_length=20, choices=EventType.choices, db_index=True
    )
    days = models.DecimalField(max_digits=6, decimal_places=2)
    year = models.PositiveIntegerField(db_index=True)
    leave_request = models.ForeignKey(
        "LeaveRequest",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leave_ledger_entries_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Leave Ledger Entry"
        verbose_name_plural = "Leave Ledger Entries"
        indexes = [
            models.Index(
                fields=["employee", "leave_type", "year"],
                name="leave_ledger_balance_idx",
            )
        ]

    def __str__(self):
        return (
            f"{self.employee} {self.leave_type} {self.event_type} "
            f"{self.days:+} ({self.year})"
        )


class LeaveBalance(models.Model):
    employee = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="leave_balance"
    )

    year = models.PositiveIntegerField()

    annual_leave = models.PositiveIntegerField(default=10)
    sick_leave = models.PositiveIntegerField(default=5)
    casual_leave = models.PositiveIntegerField(default=3)
    maternity_leave = models.PositiveIntegerField(default=40)
    paternity_leave = models.PositiveIntegerField(default=14)
    carried_over_annual_leave = models.PositiveIntegerField(default=0)
    carryover_expires_at = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("employee", "year")


class LeaveCarryover(models.Model):
    employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="leave_carryovers",
    )
    from_year = models.PositiveIntegerField()
    to_year = models.PositiveIntegerField()
    days = models.DecimalField(max_digits=5, decimal_places=2)
    expires_at = models.DateField(null=True, blank=True)
    source_balance = models.ForeignKey(
        LeaveBalance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_carryovers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("employee", "from_year", "to_year")
        ordering = ["-to_year", "employee_id"]

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at < timezone.localdate())

    def __str__(self):
        return f"{self.employee} {self.from_year}->{self.to_year}: {self.days}"


class LeaveRequest(models.Model):
    class Meta:
        base_manager_name = "all_objects"

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="created_leaverequest_requests")

    objects = HRWorkflowManager()
    all_objects = HRWorkflowQuerySet.as_manager()

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PENDING_HR", "Pending HR"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("WITHDRAWN", "Withdrawn"),
        ("CANCELLED", "Cancelled"),
    ]

    # States a request may still leave (be withdrawn/cancelled from) vs. those
    # that are terminal. Used by the withdraw/cancel service (P2-12).
    LIVE_STATES = ("PENDING", "PENDING_HR")
    TERMINAL_STATES = ("APPROVED", "REJECTED", "WITHDRAWN", "CANCELLED")

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

    leave_type = models.CharField(max_length=20)
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
    manager_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="manager_approved_leaves",
    )
    manager_approved_at = models.DateTimeField(null=True, blank=True)
    hr_approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_leave_type_display(self):
        row = LeaveType.objects.filter(company=self.employee.company, code=self.leave_type).first()
        return row.name if row else dict(self.LEAVE_CHOICES).get(self.leave_type, self.leave_type)

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

        if not self.start_date or not self.end_date or not self.employee_id:
            return
        from payroll.services.leave_type_service import ensure_default_leave_types
        ensure_default_leave_types(self.employee.company)
        if not LeaveType.objects.filter(company=self.employee.company, code=self.leave_type, is_active=True).exists():
            raise ValidationError({"leave_type": "Select an active company leave type."})
        if self.start_date > self.end_date:
            raise ValidationError("End date cannot be before start date.")

        blackout_qs = LeaveBlackoutPeriod.objects.filter(
            company=self.employee.company,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).filter(
            models.Q(department__isnull=True)
            | models.Q(department=self.employee.department)
        )
        if not self.hr_override and blackout_qs.exists():
            raise ValidationError("Leave request falls within a blackout period.")

        if self.status == "APPROVED" and not self.hr_override:
            days = self.duration

            from payroll.services.leave_type_service import available_leave_balances
            available = available_leave_balances(self.employee, self.start_date.year)
            if available.get(self.leave_type, Decimal("0")) < Decimal(str(days)):
                raise ValidationError(
                    f"Insufficient {self.leave_type.lower()} leave balance."
                )

        # Half-day requests are only valid for types that allow them (P2-12).
        if self.is_half_day and not self.hr_override:
            from payroll.services.leave_type_service import validate_half_day

            validate_half_day(
                self.leave_type, True, company=self.employee.company
            )

        overlap_qs = LeaveRequest.objects.filter(
            employee=self.employee,
            status__in=["PENDING", "PENDING_HR", "APPROVED"],
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        )
        if self.pk:
            overlap_qs = overlap_qs.exclude(pk=self.pk)
        if overlap_qs.exists():
            raise ValidationError(
                "Leave dates overlap with an existing pending/approved leave request."
            )

    def delete(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_delete
        guard_delete(self)
        return super().delete(*args, **kwargs)

    @transaction.atomic
    def save(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_requester
        guard_requester(self, kwargs.get("update_fields"))
        from payroll.services.hr_workflow import guard_state
        guard_state(self, "leave.approve", {"APPROVED", "REJECTED"}, ("approved_by_id", "manager_approved_by_id", "manager_approved_at", "hr_approved_at"), update_fields=kwargs.get("update_fields"))
        old = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if old and old.status == "APPROVED":
            guard_state(self, "leave.approve", set(), ("employee_id", "leave_type", "start_date", "end_date", "is_half_day", "hr_override", "override_reason"), update_fields=kwargs.get("update_fields"))
        user = kwargs.pop("user", None)

        is_new = self.pk is None
        previous_status = None

        if not is_new:
            previous_status = LeaveRequest.objects.get(pk=self.pk).status

        self.full_clean()
        super().save(*args, **kwargs)

        # Deduct leave only once
        status_written = kwargs.get("update_fields") is None or "status" in kwargs["update_fields"]
        if status_written and self.status == "APPROVED" and previous_status != "APPROVED":
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

                # Append the same consumption to the leave ledger so balances
                # can be derived from append-only events (P1-6); the counter
                # above stays as the read model.
                from payroll.services.leave_ledger import record_usage

                record_usage(self, days=days)

                # Fan out a signed webhook on approval (P1-9).
                from webhooks.services import emit_event

                emit_event(
                    self.employee.company,
                    "leave.request.approved",
                    {
                        "leave_request_id": str(self.pk),
                        "employee_id": str(self.employee_id),
                        "leave_type": self.leave_type,
                        "start_date": self.start_date.isoformat(),
                        "end_date": self.end_date.isoformat(),
                        "days": str(days),
                    },
                )

            from payroll.services.leave_allowance import process_leave_allowance_for_request

            process_leave_allowance_for_request(self)

            from payroll.services.attendance import populate_attendance_for_leave

            populate_attendance_for_leave(self)

        # Audit logging
        persisted_status = self.status if status_written else previous_status
        action = "CREATED" if is_new else f"STATUS_CHANGED_TO_{persisted_status}"
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


class LeaveApproval(models.Model):
    leave_request = models.ForeignKey(
        LeaveRequest,
        on_delete=models.CASCADE,
        related_name="approvals",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leave_approval_steps",
    )
    step = models.CharField(
        max_length=20,
        choices=(("manager", "Manager"), ("hr", "HR"), ("director", "Director")),
    )
    approved_at = models.DateTimeField(default=timezone.now)
    note = models.TextField(blank=True)
    is_escalated = models.BooleanField(default=False)
    escalated_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_approvals",
    )

    class Meta:
        unique_together = ("leave_request", "step")
        ordering = ["approved_at"]


class HRRetentionPolicy(models.Model):
    company = models.OneToOneField(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="hr_retention_policy",
        null=True,
        blank=True,
    )
    candidate_retention_days = models.PositiveIntegerField(default=365)
    survey_retention_days = models.PositiveIntegerField(default=730)
    disciplinary_retention_days = models.PositiveIntegerField(default=1095)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "HR Retention Policy"
        verbose_name_plural = "HR Retention Policies"

    @classmethod
    def get_for_company(cls, company):
        policy = cls.objects.filter(company=company, is_active=True).first()
        if policy:
            return policy
        policy = cls.objects.filter(company__isnull=True, is_active=True).first()
        if policy:
            return policy
        return cls(
            company=company,
            candidate_retention_days=365,
            survey_retention_days=730,
            disciplinary_retention_days=1095,
            is_active=True,
        )

    def __str__(self):
        return f"HR retention policy for {self.company or 'default'}"


def get_leave_balance(employee, year=None):
    if not year:
        year = date.today().year

    # Make sure the company's leave catalogue exists before deriving
    # entitlements from it (idempotent no-op once seeded).
    from payroll.services.leave_type_service import (
        ensure_default_leave_types,
        entitlement_days,
    )

    ensure_default_leave_types(employee.company)
    defaults = {
        "annual_leave": int(entitlement_days("ANNUAL", employee.company)),
        "sick_leave": int(entitlement_days("SICK", employee.company)),
        "casual_leave": int(entitlement_days("CASUAL", employee.company)),
        "maternity_leave": int(entitlement_days("MATERNITY", employee.company)),
        "paternity_leave": int(entitlement_days("PATERNITY", employee.company)),
    }
    carryover = 0
    previous = LeaveBalance.objects.filter(employee=employee, year=year - 1).first()
    if previous:
        carryover = Decimal(previous.annual_leave or 0)
        policy = LeavePolicy.objects.filter(
            company=employee.company,
            leave_type="ANNUAL",
        ).first()
        expires_at = None
        if policy:
            carryover = min(carryover, policy.carryover_days or carryover)
            expires_at = date(year, 1, 1) + timedelta(
                days=policy.carryover_expires_after_days
            )
            defaults["carryover_expires_at"] = expires_at
        defaults["annual_leave"] += int(carryover)
        defaults["carried_over_annual_leave"] = int(carryover)
        if carryover > 0:
            LeaveCarryover.objects.get_or_create(
                employee=employee,
                from_year=year - 1,
                to_year=year,
                defaults={
                    "days": carryover,
                    "expires_at": expires_at,
                    "source_balance": previous,
                },
            )

    balance, created = LeaveBalance.objects.get_or_create(
        employee=employee,
        year=year,
        defaults=defaults,
    )
    if created:
        # Mirror the seeded entitlement into the leave ledger so balances stay
        # derivable from append-only events (P1-6). Local import: the ledger
        # service imports payroll.models.
        from payroll.services.leave_ledger import seed_balance_accruals

        seed_balance_accruals(employee, balance)
    return balance


class BankPaymentFileQuerySet(models.QuerySet):
    @transaction.atomic
    def update(self, **kwargs):
        if "status" in kwargs:
            raise ValidationError("Payment status changes must use the bank payment service.")
        if any(item.status in ("SUBMITTED", "CONFIRMED") for item in self.select_for_update()):
            raise ValidationError("Submitted payment files cannot be changed.")
        return super().update(**kwargs)

    @transaction.atomic
    def delete(self):
        if any(item.status in ("SUBMITTED", "CONFIRMED") for item in self.select_for_update()):
            raise ValidationError("Submitted payment files cannot be deleted.")
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValidationError("Workflow records cannot be replaced through bulk conflict updates.")
        objs = list(objs)
        if any(item.status != "GENERATED" for item in objs):
            raise ValidationError("Payment files must start in generated status.")
        return super().bulk_create(objs, **kwargs)


class BankPaymentFileManager(models.Manager.from_queryset(BankPaymentFileQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class BankPaymentFile(SoftDeleteModel):
    objects = BankPaymentFileManager()
    all_objects = BankPaymentFileQuerySet.as_manager()

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="bank_payment_files",
    )
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="payment_files",
    )
    bank_code = models.CharField(max_length=10)
    bank_name = models.CharField(max_length=100)
    file_name = models.CharField(max_length=255)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    total_records = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=[
            ("GENERATED", "Generated"),
            ("SUBMITTED", "Submitted"),
            ("CONFIRMED", "Confirmed"),
            ("FAILED", "Failed"),
        ],
        default="GENERATED",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    file = models.FileField(upload_to="bank_payment_files/", blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        base_manager_name = "all_objects"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.bank_name} - {self.payroll_run} ({self.total_records} records)"

    @transaction.atomic
    def save(self, *args, **kwargs):
        validated_transition = kwargs.pop("_validated_transition", False)
        if not self.pk and self.status != "GENERATED":
            raise ValidationError("Payment files must start in generated status.")
        if self.payroll_run.company_id != self.company_id:
            raise ValidationError("Payment file and payroll must belong to the same company.")
        if self.pk:
            persisted = type(self).all_objects.select_for_update().filter(pk=self.pk).first()
            if persisted and persisted.status != self.status and not validated_transition:
                raise ValidationError("Payment status changes must use the bank payment service.")
            if persisted and persisted.status == "GENERATED" and self.status not in (
                "GENERATED", "SUBMITTED", "FAILED"
            ):
                raise ValidationError("Payment files must be submitted before confirmation.")
            if persisted and persisted.status in ("SUBMITTED", "CONFIRMED"):
                update_fields = set(kwargs.get("update_fields") or ())
                confirming = (
                    persisted.status == "SUBMITTED"
                    and self.status == "CONFIRMED"
                    and update_fields == {"status", "confirmed_at"}
                )
                if not confirming:
                    raise ValidationError("Submitted payment files cannot be changed.")
        from approvals.guards import guard_source_save
        guard_source_save(self, update_fields=kwargs.get("update_fields"))
        super().save(*args, **kwargs)
