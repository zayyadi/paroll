from django.db import models
from decimal import Decimal
from datetime import timedelta
from payroll.models.utils import SoftDeleteModel, path_and_rename
from payroll.fields import EncryptedCharField


from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import RegexValidator

from PIL import Image
from core import settings

from payroll.generator import emp_id, nin_no, tin_no
from payroll import utils
from payroll import choices

from monthyear.models import MonthField
from users.models import CustomUser


class Department(SoftDeleteModel):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="departments",
        null=True,
        blank=True,
        db_index=True,
    )
    name = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("company", "name")

    def __str__(self):
        return self.name


class EmployeeManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")

    # def search(self, query=None):
    #     return self.get_queryset().search(query=query)


PHONE_VALIDATOR = RegexValidator(
    regex=r"^(?:\+?[1-9]\d{7,14}|0\d{10})$",
    message="Enter a valid phone number (e.g. +2348012345678 or 08012345678).",
)


class EmployeeProfile(SoftDeleteModel):
    class ProbationStatus(models.TextChoices):
        NOT_APPLICABLE = "not_applicable", "Not applicable"
        ON_PROBATION = "on_probation", "On probation"
        CONFIRMED = "confirmed", "Confirmed"
        EXTENDED = "extended", "Extended"

    RENT_RELIEF_PERCENT = Decimal("20")
    RENT_RELIEF_CAP = Decimal("500000")

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="employees",
        null=True,
        blank=True,
        db_index=True,
    )
    emp_id = models.CharField(
        default=emp_id,
        unique=True,
        max_length=255,
        editable=False,
        db_index=True,
    )
    slug = models.CharField(
        # unique=True,
        max_length=50,
        verbose_name=_("Employee slug to identify and route the employee."),
        db_index=True,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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
        db_index=True,
    )

    employee_pay = models.ForeignKey(
        "Payroll",
        on_delete=models.CASCADE,
        related_name="employee_pay",
        null=True,
        blank=True,
    )
    rent_paid = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
        decimal_places=2,
        blank=True,
        help_text=(
            " Annual rent paid by employee. "
            "This is used to calculate the employee's "
            "rent relief. "
        ),
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
    nin = EncryptedCharField(
        default=nin_no,
        unique=True,
        max_length=255,
        editable=False,
    )
    tin_no = EncryptedCharField(
        default=tin_no,
        unique=True,
        max_length=255,
        editable=True,
    )
    pension_rsa = EncryptedCharField(
        # unique=True,
        max_length=255,
        null=True,
        blank=True,
    )
    hmo_provider = models.CharField(
        max_length=30,
        choices=choices.HMO_PROVIDERS,
        null=True,
        blank=True,
    )
    pension_fund_manager = models.CharField(
        max_length=30,
        choices=choices.PENSION_FUND_MANAGERS,
        null=True,
        blank=True,
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
    phone = models.CharField(
        validators=[PHONE_VALIDATOR],
        max_length=17,
        blank=True,
        # unique=True,
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

    # Emergency Contact Information
    emergency_contact_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Emergency Contact Name",
    )
    emergency_contact_relationship = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Emergency Contact Relationship",
    )
    emergency_contact_phone = EncryptedCharField(
        validators=[PHONE_VALIDATOR],
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Emergency Contact Phone Number",
    )

    # Next of Kin Information
    next_of_kin_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Next of Kin Name",
    )
    next_of_kin_relationship = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Next of Kin Relationship",
    )
    next_of_kin_phone = EncryptedCharField(
        validators=[PHONE_VALIDATOR],
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Next of Kin Phone Number",
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
    bank_account_name = EncryptedCharField(
        max_length=255,
        verbose_name="Bank Account Name",
        blank=True,
        null=True,
    )
    bank_account_number = EncryptedCharField(
        max_length=255,
        verbose_name="Bank Account Number",
        blank=True,
        null=True,
    )
    probation_start_date = models.DateField(null=True, blank=True)
    probation_end_date = models.DateField(null=True, blank=True)
    probation_status = models.CharField(
        max_length=20,
        choices=ProbationStatus.choices,
        default=ProbationStatus.NOT_APPLICABLE,
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_probation_employees",
    )
    net_pay = models.DecimalField(
        max_digits=12,
        default=Decimal(0.0),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_first_name = self.first_name
        self.__original_last_name = self.last_name
        self.__original_employee_pay_id = self.employee_pay_id

    def __str__(self):
        return self.display_first_name or "test"

    class Meta:
        ordering = ["-created"]

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("payroll:list-payslip", args=[str(self.slug)])

    @property
    def get_first_name(self):
        return self.display_first_name

    @property
    def display_first_name(self):
        return self.user.first_name if self.user and self.user.first_name else self.first_name

    @property
    def display_last_name(self):
        return self.user.last_name if self.user and self.user.last_name else self.last_name

    @property
    def display_email(self):
        return self.user.email if self.user and self.user.email else self.email

    @property
    def rent_relief_amount(self) -> Decimal:
        """
        Annual rent relief value derived from employee's declared annual rent.
        Capped to align with tax policy rules.
        """
        rent_paid = self.rent_paid or Decimal("0.00")
        relief = (rent_paid * self.RENT_RELIEF_PERCENT) / Decimal("100")
        return min(relief, self.RENT_RELIEF_CAP)

    def get_email(self):
        if self.display_email:
            return self.display_email
        return f"{self.display_first_name}.{self.display_last_name}@{settings.DEFAULT_EMAIL_DOMAIN or 'email.com'}"

    def clean(self):
        super().clean()
        if self.probation_start_date and not self.probation_end_date:
            self.probation_end_date = self.probation_start_date + timedelta(days=90)
        if (
            self.probation_start_date
            and self.probation_end_date
            and self.probation_end_date < self.probation_start_date
        ):
            raise ValidationError({"probation_end_date": "Probation end date cannot be before start date."})
        # if self.phone and not self.phone_regex.regex.match(self.phone):
        #     raise ValidationError({"phone": self.phone_regex.message})

    def confirm_probation(self, *, confirmed_by=None):
        self.probation_status = self.ProbationStatus.CONFIRMED
        self.confirmed_at = timezone.now()
        self.confirmed_by = confirmed_by
        self.status = "active"
        self.save(update_fields=["probation_status", "confirmed_at", "confirmed_by", "status"])

    def save(self, *args, **kwargs):
        self.net_pay = utils.get_net_pay(self)  # noqa: F405
        self.email = self.get_email()

        # if not self.pension_rsa.startswith("RSA-"):
        #     self.pension_rsa = f"RSA-{self.pension_rsa}"

        if self.pk is None or (
            self.first_name != self.__original_first_name
            or self.last_name != self.__original_last_name
        ):
            self.slug = slugify(f"{self.first_name}-{self.last_name}")

        from django.core.files.storage import default_storage

        if self.photo:
            try:
                img = Image.open(default_storage.path(self.photo.name))
                if img.height > 300 or img.width > 300:
                    output_size = (300, 300)
                    img.thumbnail(output_size)
                    img.save(default_storage.path(self.photo.name))
            except FileNotFoundError:
                pass

        old_employee_pay_id = self.__original_employee_pay_id
        super(EmployeeProfile, self).save(*args, **kwargs)
        if self.employee_pay_id and self.employee_pay_id != old_employee_pay_id:
            from payroll.models.payroll import SalaryHistory

            SalaryHistory.objects.get_or_create(
                employee=self,
                salary_config_id=self.employee_pay_id,
                effective_date=timezone.localdate(),
                defaults={"changed_by": kwargs.get("user")},
            )
            self.__original_employee_pay_id = self.employee_pay_id


@receiver(post_save, sender=CustomUser)
def create_employee_profile(sender, instance, created, **kwargs):
    if kwargs.get("raw", False):
        return

    if created:
        company = instance.active_company or instance.company
        if company is None:
            if not getattr(settings, "ALLOW_DEFAULT_COMPANY_FALLBACK", False):
                return
            from company.models import Company

            company, _ = Company.objects.get_or_create(name="Default Company")
        EmployeeProfile.objects.create(
            company=company,
            user=instance,
            email=instance.email,
            first_name=instance.first_name,
            last_name=instance.last_name,
        )


@receiver(post_save, sender=EmployeeProfile)
def sync_payroll_values_from_employee(sender, instance, **kwargs):
    """
    Ensure payroll tax figures include employee-side reliefs (e.g. rent relief)
    after employee/payroll linkage or employee rent updates are persisted.
    """
    payroll = instance.employee_pay
    if not payroll:
        return

    payroll.save()

    net_pay = utils.get_net_pay(instance)
    if instance.net_pay != net_pay:
        EmployeeProfile.objects.filter(pk=instance.pk).update(net_pay=net_pay)


class Appraisal(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="appraisals",
        null=True,
        blank=True,
        db_index=True,
    )
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ("-start_date", "-id")

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before start date."})

    def __str__(self):
        return self.name


class AppraisalAssignment(models.Model):
    appraisal = models.ForeignKey(Appraisal, on_delete=models.CASCADE)
    appraisee = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="appraisee_assignments"
    )
    appraiser = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="appraiser_assignments"
    )

    class Meta:
        unique_together = ("appraisal", "appraisee", "appraiser")

    def clean(self):
        super().clean()
        if self.appraisee_id and self.appraiser_id and self.appraisee_id == self.appraiser_id:
            raise ValidationError(
                {"appraiser": "Appraiser and appraisee must be different employees."}
            )
        appraisal_company = getattr(self.appraisal, "company_id", None)
        if appraisal_company:
            if self.appraisee and self.appraisee.company_id != appraisal_company:
                raise ValidationError(
                    {"appraisee": "Appraisee must belong to the same company as appraisal."}
                )
            if self.appraiser and self.appraiser.company_id != appraisal_company:
                raise ValidationError(
                    {"appraiser": "Appraiser must belong to the same company as appraisal."}
                )

    def __str__(self):
        return f"{self.appraiser} to appraise {self.appraisee} for {self.appraisal}"


class Metric(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.name


class Review(models.Model):
    appraisal = models.ForeignKey(Appraisal, on_delete=models.CASCADE)
    employee = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="reviews_received"
    )
    reviewer = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="reviews_given"
    )
    self_assessment = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["appraisal", "employee", "reviewer"],
                name="unique_review_per_assignment",
            )
        ]

    def clean(self):
        super().clean()
        if self.employee_id and self.reviewer_id and self.employee_id == self.reviewer_id:
            raise ValidationError({"reviewer": "Reviewer cannot review themselves."})

        appraisal_company = getattr(self.appraisal, "company_id", None)
        if appraisal_company:
            if self.employee and self.employee.company_id != appraisal_company:
                raise ValidationError(
                    {"employee": "Employee must belong to the same company as appraisal."}
                )
            if self.reviewer and self.reviewer.company_id != appraisal_company:
                raise ValidationError(
                    {"reviewer": "Reviewer must belong to the same company as appraisal."}
                )

        if self.appraisal_id and self.employee_id and self.reviewer_id:
            is_assigned = AppraisalAssignment.objects.filter(
                appraisal_id=self.appraisal_id,
                appraisee_id=self.employee_id,
                appraiser_id=self.reviewer_id,
            ).exists()
            if not is_assigned:
                raise ValidationError("No appraisal assignment found for this review.")

    def __str__(self):
        return f"Review of {self.employee} by {self.reviewer} for {self.appraisal}"


class Rating(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE)
    metric = models.ForeignKey(Metric, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    comments = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["review", "metric"],
                name="unique_metric_rating_per_review",
            )
        ]

    def __str__(self):
        return f"{self.metric}: {self.rating}"
