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


class DataSubjectRequest(models.Model):
    """NDPA 2023 data-subject request intake and fulfilment (P1-8).

    Gap #8 of docs/world_class_employee_management_research_2026-10-14.md:
    NDPA rights need a request intake, identity verification, and
    approve/fulfil/reject states with export/erasure actions that respect
    retention rules.

    Lifecycle (enforced by ``compliance.services``):

        submitted -> verified -> approved -> fulfilled
                  \-> rejected  \-> rejected  \-> rejected

    ``fulfilled`` and ``rejected`` are terminal. Every transition is performed
    by a service function that records who did it and when.
    """

    class RequestType(models.TextChoices):
        ACCESS = "access", "Access"
        RECTIFICATION = "rectification", "Rectification"
        ERASURE = "erasure", "Erasure"
        OBJECTION = "objection", "Objection"
        PORTABILITY = "portability", "Portability"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        VERIFIED = "verified", "Verified"
        APPROVED = "approved", "Approved"
        FULFILLED = "fulfilled", "Fulfilled"
        REJECTED = "rejected", "Rejected"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="data_subject_requests"
    )
    subject = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_subject_requests",
        help_text="The NDPA data subject the request concerns.",
    )
    subject_email = models.EmailField(
        help_text="Contact email for the requester (may differ from the subject)."
    )
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SUBMITTED
    )

    received_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField(
        help_text="Response deadline (received_at + 30 days)."
    )
    verification_note = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dsrs_verified",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dsrs_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    response = models.JSONField(
        null=True, blank=True,
        help_text="Export payload or fulfilment summary.",
    )

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(
                fields=["company", "status"], name="dsr_company_status_idx"
            )
        ]

    def __str__(self):
        return f"{self.get_request_type_display()} — {self.subject_email} ({self.status})"
