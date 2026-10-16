"""Outbound signed webhooks + change feed (P1-9).

Gap #9 of docs/world_class_employee_management_research_2026-10-14.md:
emit events for payroll run state changes, leave approvals, terminations and
remittance status; sign with HMAC over payload+timestamp, retry with jitter,
HTTPS only — per BambooHR's webhook scheme. ``GET``-style delta endpoints for
employee data live in ``webhooks.views.changed_employees``.
"""
from __future__ import annotations

import secrets
import uuid

from django.db import models


class WebhookEndpoint(models.Model):
    """One subscriber URL, scoped to a company and a set of event types."""

    class EventType(models.TextChoices):
        PAYROLL_RUN_STATE = (
            "payroll.run.state_changed",
            "Payroll run state changed",
        )
        LEAVE_APPROVED = (
            "leave.request.approved",
            "Leave request approved",
        )
        EMPLOYEE_TERMINATED = (
            "employee.terminated",
            "Employee terminated",
        )
        REMITTANCE_FILED = (
            "remittance.filed",
            "Remittance filed",
        )
        EMPLOYEE_CHANGED = (
            "employee.changed",
            "Employee record changed",
        )

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="webhook_endpoints",
    )
    name = models.CharField(max_length=120)
    url = models.URLField(
        max_length=500,
        help_text="Must be an HTTPS URL; plaintext HTTP is rejected.",
    )
    secret = models.CharField(
        max_length=64,
        editable=False,
        help_text="HMAC shared secret, generated per endpoint.",
    )
    event_types = models.JSONField(
        default=list,
        help_text="Subscribed event type codes; empty list means all events.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company", "name"]

    def __str__(self):
        return f"{self.name} ({self.url})"

    @staticmethod
    def generate_secret() -> str:
        return secrets.token_hex(32)

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = self.generate_secret()
        # BambooHR scheme: HTTPS only, reject anything else loudly.
        if not self.url.lower().startswith("https://"):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"url": "Webhook endpoints must use HTTPS."}
            )
        super().save(*args, **kwargs)

    def subscribes_to(self, event_type: str) -> bool:
        if not self.event_types:
            return True
        return event_type in self.event_types


class WebhookDelivery(models.Model):
    """One (event, endpoint) delivery attempt ledger with retry state."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed (gave up)"

    event_id = models.UUIDField(default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=60, db_index=True)
    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    payload = models.JSONField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                name="webhook_due_idx",
            )
        ]

    def __str__(self):
        return f"{self.event_type} -> {self.endpoint} ({self.status})"
