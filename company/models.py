from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Company(models.Model):
    name = models.CharField(max_length=255, unique=True, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class CompanyMembership(models.Model):
    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_MEMBER = "member"

    ROLE_CHOICES = (
        (ROLE_OWNER, "Owner"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_MEMBER, "Member"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_memberships",
    )
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "company")
        ordering = ["-is_default", "company__name"]

    def __str__(self):
        return f"{self.user.email} @ {self.company.name}"


class ActionProposalQuerySet(models.QuerySet):
    def update(self, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Approval proposals are immutable; create a replacement proposal.')
    def delete(self):
        from django.core.exceptions import ValidationError
        raise ValidationError('Approval proposals cannot be deleted.')
    def bulk_create(self, objs, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Submit proposals through the workflow service.')


class ActionProposal(models.Model):
    """Immutable inputs for operations whose business record is created after approval."""
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    action = models.CharField(max_length=120)
    parameters = models.JSONField(default=dict)
    currency = models.CharField(max_length=3, default='NGN')
    created_by = models.ForeignKey('users.CustomUser', on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default='PENDING', choices=[('PENDING','Pending'),('APPLIED','Applied')])
    result_type = models.CharField(max_length=120, blank=True)
    request_key = models.CharField(max_length=64)
    result_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ActionProposalQuerySet.as_manager()

    class Meta:
        base_manager_name = "objects"
        constraints = [models.UniqueConstraint(fields=['company', 'action', 'created_by', 'request_key'], name='unique_action_submission_key')]

    def __str__(self):
        return f'{self.action.replace(".", " · ")} #{self.pk}'

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        from approvals.services import execution_authorized
        from approvals.permissions import require_company_authority
        from approvals.registry import get_action
        if not self.pk:
            if self.status != 'PENDING' or self.result_id is not None or self.result_type:
                raise ValidationError('New proposals must be pending and unapplied.')
            from approvals.proposals import _SUBMISSION_PERMISSIONS
            require_company_authority(self.created_by, self.company, _SUBMISSION_PERMISSIONS.get(self.action, get_action(self.action).permission))
        else:
            previous = type(self).objects.get(pk=self.pk)
            if not execution_authorized(self, previous.action):
                raise ValidationError('Approval proposals are immutable.')
            if any(getattr(previous, field) != getattr(self, field) for field in ('company_id','action','parameters','created_by_id','currency','request_key')):
                raise ValidationError('Approved proposal inputs cannot change.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Approval proposals cannot be deleted.')
