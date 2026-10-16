"""Compensation planning cycles + salary bands (P2-11).

Gap #11 of docs/world_class_employee_management_research_2026-10-14.md: port a
create -> recommend -> approve -> apply compensation-review cycle on top of
``SalaryHistory``, and add salary bands per ``Position`` (BambooHR compensation
planning).

Design notes
------------
A ``SalaryBand`` is the approved pay range for a position; a ``CompCycle`` is a
budgeted planning round; a ``CompReview`` is one employee's proposed raise in
that round.

Applying an approved raise writes a ``SalaryHistory`` row AND updates the
employee's live ``Payroll.basic_salary``, wrapped in ``approved_context`` so it
rides the existing ``EmployeeProfile`` salary-change guard
(``payroll/models/employee_profile.py:397``) rather than fighting it. The
review itself carries a snapshot (``current_basic``/``proposed_basic``) so the
audit trail survives even after the live config moves on.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class SalaryBand(models.Model):
    """Approved pay range for a position (BambooHR compensation band)."""

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="salary_bands",
    )
    # Bands anchor to a position *title* (``EmployeeProfile.job_title`` is a
    # CharField, and there is no employee->Position FK yet), so the title text
    # is the join key rather than a foreign key.
    position_title = models.CharField(max_length=255)
    min_salary = models.DecimalField(max_digits=12, decimal_places=2)
    mid_salary = models.DecimalField(max_digits=12, decimal_places=2)
    max_salary = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position_title", "min_salary"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "position_title"],
                name="uniq_salary_band_company_title",
            )
        ]

    def clean(self):
        super().clean()
        if not (self.min_salary <= self.mid_salary <= self.max_salary):
            raise ValidationError(
                "A salary band must satisfy min <= mid <= max."
            )

    def __str__(self):
        return (
            f"{self.position_title}: {self.min_salary}–{self.max_salary}"
        )

    def contains(self, amount: Decimal) -> bool:
        return self.min_salary <= amount <= self.max_salary


class CompCycle(models.Model):
    """A budgeted compensation-review round for one company."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RECOMMENDED = "recommended", "Recommended"
        APPROVED = "approved", "Approved"
        APPLIED = "applied", "Applied"
        CLOSED = "closed", "Closed"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="comp_cycles",
    )
    name = models.CharField(max_length=120)
    effective_date = models.DateField()
    budget_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total annual increase budget; None means unbounded.",
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.OPEN
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="comp_cycles_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_comp_cycle_company_name"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"


class CompReview(models.Model):
    """One employee's proposed raise inside a ``CompCycle``."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        RECOMMENDED = "recommended", "Recommended"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        APPLIED = "applied", "Applied"

    cycle = models.ForeignKey(
        CompCycle, on_delete=models.CASCADE, related_name="reviews"
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="comp_reviews",
    )
    current_basic = models.DecimalField(max_digits=12, decimal_places=2)
    proposed_basic = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PROPOSED
    )
    note = models.CharField(max_length=255, blank=True)
    approval_request = models.ForeignKey(
        "approvals.ApprovalRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comp_reviews",
        help_text="The submitted salary-change approval for this raise.",
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["employee__first_name", "employee__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["cycle", "employee"], name="uniq_comp_review_cycle_emp"
            )
        ]

    def __str__(self):
        return f"{self.employee} {self.current_basic} → {self.proposed_basic}"

    @property
    def increase_amount(self) -> Decimal:
        return self.proposed_basic - self.current_basic

    @property
    def increase_percent(self) -> Decimal:
        if not self.current_basic:
            return Decimal("0")
        return (
            (self.increase_amount / self.current_basic) * Decimal("100")
        ).quantize(Decimal("0.01"))

    @property
    def salary_band(self):
        """The active band matching the employee's ``job_title``, if any."""
        title = getattr(self.employee, "job_title", "")
        if not title:
            return None
        return (
            SalaryBand.objects.filter(
                company=self.employee.company,
                position_title=title,
                is_active=True,
            )
            .order_by("-created_at")
            .first()
        )

    @property
    def within_band(self) -> bool | None:
        """True/F False when a band exists; None when the role has no band."""
        band = self.salary_band
        if band is None:
            return None
        return band.contains(self.proposed_basic)
