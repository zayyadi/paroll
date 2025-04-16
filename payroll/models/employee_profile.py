from django.db import models
from payroll.models.utils import SoftDeleteModel, path_and_rename


from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError

from django.db.models.signals import post_save
from django.dispatch import receiver

from PIL import Image
from core import settings

from payroll.generator import emp_id, nin_no, tin_no
from payroll import utils
from payroll import choices

from monthyear.models import MonthField
from users.models import CustomUser


class Department(SoftDeleteModel):
    name = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class EmployeeManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="active")

    # def search(self, query=None):
    #     return self.get_queryset().search(query=query)


class EmployeeProfile(SoftDeleteModel):
    emp_id = models.CharField(
        default=emp_id,
        unique=True,
        max_length=255,
        editable=False,
        db_index=True,
    )
    slug = models.CharField(
        unique=True,
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
        if self.photo and hasattr(self.photo, "path"):
            img = Image.open(self.photo.path)

            if img.height > 300 or img.width > 300:
                output_size = (300, 300)
                img.thumbnail(output_size)
                img.save(self.photo.path)

    @property
    def get_first_name(self):
        return self.first_name

    @property
    def format_rsa(self):
        return f"RSA-{self.pension_rsa}"

    @property
    def save_slug(self):
        return f"{self.first_name}-{self.last_name}"

    @property
    def get_email(self):
        return f"{self.first_name}.{self.last_name}@email.com"

    def clean(self):
        super().clean()
        if self.phone and not self.phone_regex.regex.match(self.phone):
            raise ValidationError({"phone": self.phone_regex.message})

    def save(self, *args, **kwargs):
        self.net_pay = utils.get_net_pay(self)  # noqa: F405
        self.email = self.get_email
        self.slug = self.save_slug
        self.pension_rsa = self.format_rsa
        super(EmployeeProfile, self).save(*args, **kwargs)


@receiver(post_save, sender=CustomUser)
def create_employee(sender, instance, created, **kwargs):
    if created:
        EmployeeProfile.objects.create(
            user=instance, first_name=instance.first_name, last_name=instance.last_name
        )


class PerformanceReview(models.Model):
    employee = models.ForeignKey(
        EmployeeProfile, on_delete=models.CASCADE, related_name="performance_reviews"
    )
    review_date = models.DateField()
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 11)])  # 1-10 rating
    comments = models.TextField()

    def __str__(self):
        employee_name = (
            self.employee.user.get_full_name()
            if hasattr(self.employee.user, "get_full_name")
            else "Unknown"
        )
        return f"Review for {employee_name} on {self.review_date}"
