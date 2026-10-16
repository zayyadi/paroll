from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from .context import _writing


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if not _writing.get():
            raise ValidationError(
                "Approval audit records can only be changed by the workflow service."
            )
        return super().update(**kwargs)

    def delete(self):
        raise ValidationError("Approval audit records cannot be deleted.")

    def bulk_create(self, objs, **kwargs):
        if not _writing.get():
            raise ValidationError(
                "Approval audit records can only be created by the workflow service."
            )
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if not _writing.get():
            raise ValidationError(
                "Approval audit records can only be changed by the workflow service."
            )
        return super().bulk_update(objs, fields, **kwargs)


class ProtectedAudit(models.Model):
    objects = AuditQuerySet.as_manager()

    class Meta:
        abstract = True
        base_manager_name = "objects"

    def save(self, *args, **kwargs):
        if not _writing.get():
            raise ValidationError("Use the approval workflow service.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Approval audit records cannot be deleted.")


class ApprovalPolicy(models.Model):
    company = models.ForeignKey("company.Company", on_delete=models.PROTECT)
    action = models.CharField(max_length=120)
    name = models.CharField(max_length=200, blank=True)
    enabled = models.BooleanField(default=True)
    stages = models.JSONField(default=list)
    minimum_amount = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "action", "currency", "minimum_amount"],
                name="unique_approval_policy_threshold",
            ),
            models.UniqueConstraint(
                fields=["company", "action", "currency"],
                condition=models.Q(minimum_amount__isnull=True),
                name="unique_approval_policy_baseline",
            ),
        ]
        permissions = [("configure_policy", "Configure company approval policies")]

    def clean(self):
        from .registry import get_action
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        get_action(self.action)
        if self.minimum_amount is not None and (
            not self.minimum_amount.is_finite() or self.minimum_amount < 0
        ):
            raise ValidationError("Minimum amount must be finite and nonnegative.")
        if self.currency and (
            len(self.currency) != 3
            or not self.currency.isalpha()
            or self.currency != self.currency.upper()
        ):
            raise ValidationError("Currency must be a three-letter uppercase code.")
        if self.minimum_amount is not None and not self.currency:
            raise ValidationError("An amount threshold requires a currency.")
        if not isinstance(self.stages, list) or not self.stages:
            raise ValidationError("At least one approval stage is required.")
        for stage in self.stages:
            if not isinstance(stage, dict) or set(stage) - {
                "permission",
                "approver_ids",
                "name",
            }:
                raise ValidationError("Invalid approval stage.")
            perm = stage.get("permission", "")
            if "." not in perm:
                raise ValidationError("Every stage requires an explicit permission.")
            app, codename = perm.split(".", 1)
            if not Permission.objects.filter(
                content_type__app_label=app, codename=codename
            ).exists():
                raise ValidationError("Unknown approval permission.")
            ids = stage.get("approver_ids", [])
            if (
                not isinstance(ids, list)
                or any(type(x) is not int for x in ids)
                or len(ids) != len(set(ids))
            ):
                raise ValidationError("Approver IDs must be unique integer IDs.")
            for user_id in ids:
                if (
                    not get_user_model()
                    .objects.filter(pk=user_id, is_active=True)
                    .filter(
                        models.Q(company_id=self.company_id)
                        | models.Q(company_memberships__company_id=self.company_id)
                    )
                    .exists()
                ):
                    raise ValidationError(
                        "Designated approvers must belong to this company."
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ApprovalRequest(ProtectedAudit):
    company = models.ForeignKey("company.Company", on_delete=models.PROTECT)
    action = models.CharField(max_length=120)
    content_type = models.ForeignKey(
        "contenttypes.ContentType", on_delete=models.PROTECT
    )
    object_id = models.PositiveBigIntegerField()
    source = GenericForeignKey("content_type", "object_id")
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approval_requests",
    )
    beneficiary_ids = models.JSONField(default=list)
    payload = models.JSONField(default=dict)
    source_snapshot = models.JSONField(default=dict)
    source_hash = models.CharField(max_length=64)
    execution_snapshot = models.JSONField(default=dict)
    policy_snapshot = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        default="PENDING",
        choices=[
            (s, s.title()) for s in ["PENDING", "APPROVED", "REJECTED", "CANCELLED"]
        ],
    )
    current_stage = models.PositiveIntegerField(default=0)
    pending_key = models.CharField(
        max_length=200, unique=True, null=True, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at"]
        base_manager_name = "objects"


class ApprovalDecision(ProtectedAudit):
    request = models.ForeignKey(
        ApprovalRequest, on_delete=models.PROTECT, related_name="decisions"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    stage = models.PositiveIntegerField()
    decision = models.CharField(max_length=12)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        base_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=["request", "actor"], name="approval_distinct_actor"
            )
        ]


class ApprovalEvent(ProtectedAudit):
    request = models.ForeignKey(
        ApprovalRequest, on_delete=models.PROTECT, related_name="events"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=32)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
