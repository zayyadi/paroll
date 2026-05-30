from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class DataRetentionPolicy(models.Model):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="retention_policies"
    )
    record_type = models.CharField(
        max_length=50, choices=[
            ("PAYROLL", "Payroll Records"),
            ("LEAVE", "Leave Records"),
            ("DISCIPLINARY", "Disciplinary Records"),
            ("AUDIT", "Audit Trail"),
            ("TAX", "Tax Records"),
            ("INVENTORY", "Inventory Records"),
        ]
    )
    retention_days = models.PositiveIntegerField(default=2555)
    auto_delete = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "record_type"], name="uniq_retention_company_type"
            )
        ]
        ordering = ["company", "record_type"]

    def __str__(self):
        return f"{self.get_record_type_display()} — {self.retention_days} days"


class PolicyAcknowledgment(models.Model):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="policy_acknowledgments"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="policy_acknowledgments"
    )
    policy_name = models.CharField(max_length=255)
    policy_version = models.CharField(max_length=40, default="1.0")
    acknowledged_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "policy_name", "policy_version"],
                name="uniq_acknowledgment_user_policy_version",
            )
        ]
        ordering = ["-acknowledged_at"]

    def __str__(self):
        return f"{self.user} — {self.policy_name} v{self.policy_version}"
