from django.utils import timezone
from django.db import models
from django.core.validators import RegexValidator
from django.db.models import Q,signals
from django.contrib.auth.models import User
from django.dispatch import receiver

from employee.generator import emp_id, nin_no, tin_no

CONTRACT_TYPE = (("P", "Permanent"), ("T", "Temporary"))

GENDER = (
    ("others", "Others"),
    ("male", "Male"),
    ("female", "Female"),
)

LEVEL = (
    ("C", "Casual"),
    ("JS", "Junior staff"),
    ("OP", "Operator"),
    ("SU", "SUpervisor"),
    ("M", "Manager"),
    ("COO", "C.O.O"),
    # ("S", "Store Control Officer"),
)


PAYMENT_METHOD = (
    ("B", "BANK PAYMENT"),
    ("H", "HAND PAYMENT"),
)

BANK = (
    ("Zenith", "Zenith BANK"),
    ("Access", "Access Bank"),
    ("GTB", "GT Bank"),
    ("Jaiz", "JAIZ Bank"),
    ("FCMB", "FCMB"),
    ("FBN", "First Bank"),
    ("Union", "Union Bank"),
    ("UBA", "UBA"),
)

class EmployeeQuerySet(models.QuerySet):
    def search(self, query=None):
        if query is None or query == "":
            return self.none()
        lookups = (
            Q(first_name__icontains=query) | 
            Q(email__icontains=query) |
            Q(directions__icontains=query)
        )
        return self.filter(lookups)

class EmployeeManager(models.Manager):
    def get_queryset(self):
        return EmployeeQuerySet(self.model, using=self._db)

    def search(self, query=None):
        return self.get_queryset().search(query=query)

class Employee(models.Model):
    emp_id = models.CharField(default=emp_id, unique = True, max_length=255, editable=False)
    # user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="employee_user")
    first_name = models.CharField(max_length=255, blank=False, null=True)
    last_name = models.CharField(max_length=255, blank=False, null=True)
    email = models.EmailField(max_length=255, blank=True, unique=True)
    photo = models.FileField(blank=True, null=True)
    nin = models.CharField(default=nin_no, unique = True,max_length=255, editable=False)
    tin_no = models.CharField(default=tin_no, unique = True, max_length=255, editable=False)
    date_of_birth = models.DateField()
    # passport_photo = models.ImageField(blank=True, null=True)
    # allowances = models.ManyToManyField("Allowance", blank=True)
    date_of_employment = models.DateField(null=True)
    contract_type = models.CharField(choices=CONTRACT_TYPE, max_length=1, null=True)
    phone_regex = RegexValidator(
        regex=r"^\+?1?\d{3}\d{9,13}$",
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.",
    )
    phone = models.CharField(
        validators=[phone_regex],
        default=1234567890,
        max_length=13,
        blank=False,
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
        max_length=255, blank=False, null=True, verbose_name="address"
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
        max_length=255, verbose_name="Bank Account Name", unique=True, blank=True
    )
    bank_account_number = models.CharField(
        max_length=10, verbose_name="Bank Account Number", unique=True, blank=False
    )
    is_active = models.BooleanField(default=True)
    objects = EmployeeManager()

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.first_name

    @property
    def get_email(self):
        return f"{self.first_name}@example.com"

    def save(self, *args, **kwargs):
        self.email = self.get_email

        super(Employee, self).save(*args, **kwargs)

# @receiver(signals.post_save, sender=User)
# def create_user_profile(sender, instance, created, **kwargs):
#     if created:
#         Employee.objects.create(user=instance)

# @receiver(signals.post_save, sender=User)
# def save_user_profile(sender, instance, **kwargs):
#     instance.employee.save()

