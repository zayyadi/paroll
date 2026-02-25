from django.db import models
from django.db.models import Sum, Q
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps
from datetime import date, timedelta
import json

User = get_user_model()


class BaseModel(models.Model):
    """Abstract base model to include common fields like timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        abstract = True


class Account(BaseModel):
    class AccountType(models.TextChoices):
        ASSET = "ASSET", _("Asset")
        LIABILITY = "LIABILITY", _("Liability")
        EQUITY = "EQUITY", _("Equity")
        REVENUE = "REVENUE", _("Revenue")
        EXPENSE = "EXPENSE", _("Expense")

    name = models.CharField(max_length=255, unique=True)
    account_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    type = models.CharField(max_length=10, choices=AccountType.choices)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.account_number} - {self.name}"

    def get_balance(self):
        debits = (
            self.entries.filter(entry_type="DEBIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )
        credits = (
            self.entries.filter(entry_type="CREDIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )

        if self.type in [self.AccountType.ASSET, self.AccountType.EXPENSE]:
            return debits - credits
        else:  # Liability, Equity, Revenue
            return credits - debits

    @property
    def balance(self):
        return self.get_balance()

    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Accounts"
        ordering = ["account_number"]


class FiscalYear(BaseModel):
    """Represents a fiscal year for accounting purposes"""

    year = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_fiscal_years",
    )

    class Meta:
        ordering = ["-year"]
        verbose_name = "Fiscal Year"
        verbose_name_plural = "Fiscal Years"

    def __str__(self):
        return f"FY {self.year} ({self.name})"

    def clean(self):
        if self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")

        # Check for overlapping fiscal years
        overlapping = FiscalYear.objects.filter(
            models.Q(start_date__lte=self.end_date)
            & models.Q(end_date__gte=self.start_date)
        ).exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError("Fiscal year dates overlap with existing fiscal year")

    def close(self, user):
        """Close fiscal year"""
        if self.is_closed:
            raise ValidationError("Fiscal year is already closed")

        # Check if all periods are closed
        if self.periods.filter(is_closed=False).exists():
            raise ValidationError("Cannot close fiscal year with open periods")

        self.is_closed = True
        self.closed_at = timezone.now()
        self.closed_by = user
        self.save()

        # Signal will automatically log the closure through signal handlers


class AccountingPeriod(BaseModel):
    """Represents an accounting period within a fiscal year"""

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.CASCADE, related_name="periods"
    )
    period_number = models.PositiveIntegerField()
    name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_periods",
    )

    class Meta:
        ordering = ["fiscal_year", "period_number"]
        unique_together = ["fiscal_year", "period_number"]
        verbose_name = "Accounting Period"
        verbose_name_plural = "Accounting Periods"

    def __str__(self):
        return f"{self.fiscal_year.name} - Period {self.period_number} ({self.name})"

    def clean(self):
        if self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")

        # Check if period is within fiscal year dates
        if (
            self.start_date < self.fiscal_year.start_date
            or self.end_date > self.fiscal_year.end_date
        ):
            raise ValidationError("Period dates must be within fiscal year dates")

        # Check for overlapping periods within the same fiscal year
        overlapping = AccountingPeriod.objects.filter(
            models.Q(start_date__lte=self.end_date)
            & models.Q(end_date__gte=self.start_date),
            fiscal_year=self.fiscal_year,
        ).exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError(
                "Period dates overlap with existing period in the same fiscal year"
            )

    def close(self, user):
        """Close accounting period"""
        if self.is_closed:
            raise ValidationError("Accounting period is already closed")

        # Add any period closing logic here
        self.is_closed = True
        self.closed_at = timezone.now()
        self.closed_by = user
        self.save()

        # Signal will automatically log the closure through signal handlers


class TransactionNumber(BaseModel):
    """Manages automatic transaction numbering"""

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.CASCADE, related_name="transaction_numbers"
    )
    prefix = models.CharField(max_length=10, default="TXN")
    current_number = models.PositiveIntegerField(default=1)
    padding = models.PositiveIntegerField(default=6)

    class Meta:
        unique_together = ["fiscal_year", "prefix"]
        verbose_name = "Transaction Number"
        verbose_name_plural = "Transaction Numbers"

    def __str__(self):
        return f"{self.prefix} for {self.fiscal_year.name}"

    @classmethod
    def get_next_number(cls, fiscal_year, prefix="TXN"):
        """Get next globally unique transaction number for this fiscal year/prefix."""
        JournalModel = cls._meta.apps.get_model("accounting", "Journal")

        with transaction.atomic():
            txn_number, created = cls.objects.select_for_update().get_or_create(
                fiscal_year=fiscal_year, prefix=prefix, defaults={"current_number": 1}
            )

            next_number = txn_number.current_number
            formatted_number = f"{prefix}{str(next_number).zfill(txn_number.padding)}"

            # transaction_number is globally unique on Journal, so back-posting older
            # periods can collide with numbers already issued in a different fiscal year.
            while JournalModel.objects.filter(
                transaction_number=formatted_number
            ).exists():
                next_number += 1
                formatted_number = f"{prefix}{str(next_number).zfill(txn_number.padding)}"

            txn_number.current_number = next_number + 1
            txn_number.save()

        return formatted_number


class AccountingAuditTrail(BaseModel):
    """Enhanced audit trail for accounting transactions"""

    class ActionType(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        APPROVE = "APPROVE", "Approve"
        REJECT = "REJECT", "Reject"
        POST = "POST", "Post"
        REVERSE = "REVERSE", "Reverse"
        CLOSE_PERIOD = "CLOSE_PERIOD", "Close Period"
        CLOSE_FISCAL_YEAR = "CLOSE_FISCAL_YEAR", "Close Fiscal Year"

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ActionType.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Object reference
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    # Change details
    changes = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)

    # Approval workflow
    approval_level = models.PositiveIntegerField(null=True, blank=True)
    approval_status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("APPROVED", "Approved"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING",
    )

    class Meta:
        verbose_name = "Accounting Audit Trail"
        verbose_name_plural = "Accounting Audit Trails"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user} performed {self.action} on {self.content_object} at {self.timestamp}"

    @classmethod
    def log_action(
        cls,
        user,
        action,
        instance,
        changes=None,
        reason=None,
        ip_address=None,
        user_agent=None,
        approval_level=None,
    ):
        """Log an action to audit trail"""

        def create_audit_entry():
            try:
                return cls.objects.create(
                    user=user,
                    action=action,
                    content_type=ContentType.objects.get_for_model(instance),
                    object_id=instance.pk,
                    changes=changes or {},
                    reason=reason or "",
                    ip_address=ip_address,
                    user_agent=user_agent or "",
                    approval_level=approval_level,
                )
            except Exception:
                # Silently fail to avoid breaking the main application
                # In production, this should be logged to error monitoring
                pass

        # Check if we're in an atomic block and if the transaction is in a good state
        try:
            # Try to use on_commit if we're in a working transaction
            if transaction.get_connection().in_atomic_block:
                transaction.on_commit(create_audit_entry)
            else:
                # Not in an atomic block, create directly
                create_audit_entry()
        except Exception:
            # If transaction is broken or on_commit fails, try to create directly
            # This handles the case where we're in a broken transaction state
            try:
                # Use a separate transaction to avoid the broken one
                with transaction.atomic(using=None, savepoint=False):
                    create_audit_entry()
            except Exception:
                # As a last resort, try without any transaction wrapper
                # This ensures audit logging doesn't break the main application
                create_audit_entry()


class Journal(BaseModel):
    class JournalStatus(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        PENDING_APPROVAL = "PENDING_APPROVAL", _("Pending Approval")
        APPROVED = "APPROVED", _("Approved")
        POSTED = "POSTED", _("Posted")
        CANCELLED = "CANCELLED", _("Cancelled")
        REVERSED = "REVERSED", _("Reversed")

    # Basic fields
    transaction_number = models.CharField(max_length=20, unique=True, editable=False)
    description = models.CharField(max_length=255)
    date = models.DateField(default=timezone.now)
    period = models.ForeignKey(
        AccountingPeriod, on_delete=models.PROTECT, related_name="journals"
    )
    status = models.CharField(
        max_length=20, choices=JournalStatus.choices, default=JournalStatus.DRAFT
    )

    # Audit fields
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_journals",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_journals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posted_journals",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    # Reversal fields
    reversed_journal = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversal_of",
    )
    reversal_reason = models.TextField(blank=True, null=True)

    # Source transaction reference
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    def __str__(self):
        return f"{self.transaction_number} - {self.description} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Generate transaction number if new
        if not self.pk and not self.transaction_number:
            current_year = timezone.now().year
            fiscal_year = FiscalYear.objects.filter(
                year=current_year, is_active=True
            ).first()
            if not fiscal_year:
                # Create or get current fiscal year
                fiscal_year, _ = FiscalYear.objects.get_or_create(
                    year=current_year,
                    defaults={
                        "name": f"FY {current_year}",
                        "start_date": date(current_year, 1, 1),
                        "end_date": date(current_year, 12, 31),
                        "is_active": True,
                    },
                )

            self.transaction_number = TransactionNumber.get_next_number(fiscal_year)

        # Set period if not set
        if not self.period_id:
            current_year = timezone.now().year
            fiscal_year = FiscalYear.objects.get(year=current_year, is_active=True)
            current_month = timezone.now().month
            period = AccountingPeriod.objects.filter(
                fiscal_year=fiscal_year, period_number=current_month
            ).first()
            if not period:
                # Create monthly period
                period = AccountingPeriod.objects.create(
                    fiscal_year=fiscal_year,
                    period_number=current_month,
                    name=f"Month {current_month}",
                    start_date=date(current_year, current_month, 1),
                    end_date=get_last_day_of_month(current_year, current_month),
                    is_active=True,
                )
            self.period = period

        super(Journal, self).save(*args, **kwargs)

    def clean(self):
        # Basic validation
        if self.status == self.JournalStatus.POSTED:
            if not self.entries.exists():
                raise ValidationError("A posted journal must have entries.")
            self.validate_entries()

    def validate_entries(self):
        """Validates that sum of debits equals sum of credits"""
        debits = (
            self.entries.filter(entry_type="DEBIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )
        credits = (
            self.entries.filter(entry_type="CREDIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )

        if debits != credits:
            raise ValidationError(
                f"Debits ({debits}) and credits ({credits}) must be equal for a journal."
            )

    def submit_for_approval(self):
        """Submit journal for approval"""
        if self.status != self.JournalStatus.DRAFT:
            raise ValidationError("Only draft journals can be submitted for approval")

        self.status = self.JournalStatus.PENDING_APPROVAL
        self.save()

    def approve(self, user):
        """Approve the journal"""
        if self.status != self.JournalStatus.PENDING_APPROVAL:
            raise ValidationError("Only pending journals can be approved")

        self.status = self.JournalStatus.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

        # Signal will automatically log the approval through signal handlers

    def post(self, user):
        """Mark the journal as posted"""
        if self.status != self.JournalStatus.APPROVED:
            raise ValidationError("Only approved journals can be posted")

        self.validate_entries()
        self.status = self.JournalStatus.POSTED
        self.posted_by = user
        self.posted_at = timezone.now()
        self.save()

        # Signal will automatically log the posting through signal handlers

    def reverse(self, user, reason):
        """Create a reversal journal"""
        if self.status != self.JournalStatus.POSTED:
            raise ValidationError("Only posted journals can be reversed")

        if self.reversed_journal:
            raise ValidationError("Journal has already been reversed")

        with transaction.atomic():
            # Create reversal journal
            reversal_journal = Journal.objects.create(
                description=f"REVERSAL: {self.description}",
                date=timezone.now().date(),
                period=self.period,
                status=self.JournalStatus.DRAFT,
                created_by=user,
                reversal_reason=reason,
                reversed_journal=self,
            )

            # Create reversal entries (swap debits and credits)
            for entry in self.entries.all():
                reversal_entry_type = (
                    "CREDIT" if entry.entry_type == "DEBIT" else "DEBIT"
                )
                JournalEntry.objects.create(
                    journal=reversal_journal,
                    account=entry.account,
                    entry_type=reversal_entry_type,
                    amount=entry.amount,
                    memo=f"Reversal of entry {entry.id}: {entry.memo or ''}",
                )

            # Auto-approve and post reversal
            reversal_journal.approve(user)
            reversal_journal.post(user)

            # Mark original journal as reversed
            self.status = self.JournalStatus.REVERSED
            self.save()

            return reversal_journal

    def add_entry(self, account, entry_type, amount, memo=None):
        """Helper to add a journal entry"""
        if self.status in [self.JournalStatus.POSTED, self.JournalStatus.CANCELLED]:
            raise ValidationError(
                "Cannot add entries to a posted or cancelled journal."
            )

        return JournalEntry.objects.create(
            journal=self,
            account=account,
            entry_type=entry_type,
            amount=amount,
            memo=memo,
        )

    class Meta:
        verbose_name = "Journal"
        verbose_name_plural = "Journals"
        ordering = ["-date", "-created_at"]


class JournalEntry(BaseModel):
    class EntryType(models.TextChoices):
        DEBIT = "DEBIT", _("Debit")
        CREDIT = "CREDIT", _("Credit")

    journal = models.ForeignKey(
        Journal, on_delete=models.CASCADE, related_name="entries"
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="entries"
    )
    entry_type = models.CharField(max_length=6, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    memo = models.CharField(max_length=255, blank=True, null=True)

    # Audit field
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_entries",
    )

    def __str__(self):
        return f"{self.journal.transaction_number} - {self.get_entry_type_display()} {self.amount} to {self.account.name}"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Amount must be greater than zero")

    class Meta:
        verbose_name = "Journal Entry"
        verbose_name_plural = "Journal Entries"
        ordering = ["journal__date", "entry_type", "account__name"]


def get_last_day_of_month(year, month):
    """Get the last day of a month"""
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    else:
        return date(year, month + 1, 1) - timedelta(days=1)


class DisciplinaryCase(BaseModel):
    class ViolationLevel(models.TextChoices):
        LEVEL_1 = "LEVEL_1", "Level 1 - Minor"
        LEVEL_2 = "LEVEL_2", "Level 2 - Moderate"
        LEVEL_3 = "LEVEL_3", "Level 3 - Serious"
        LEVEL_4 = "LEVEL_4", "Level 4 - Major"
        LEVEL_5 = "LEVEL_5", "Level 5 - Critical"

    class Status(models.TextChoices):
        INTAKE = "INTAKE", "Intake"
        UNDER_INVESTIGATION = "UNDER_INVESTIGATION", "Under Investigation"
        PANEL_REVIEW = "PANEL_REVIEW", "Panel Review"
        DECIDED = "DECIDED", "Decided"
        APPEALED = "APPEALED", "Appealed"
        CLOSED = "CLOSED", "Closed"
        DISMISSED = "DISMISSED", "Dismissed"

    class Finding(models.TextChoices):
        UNSUBSTANTIATED = "UNSUBSTANTIATED", "Unsubstantiated"
        PARTIALLY_SUBSTANTIATED = "PARTIALLY_SUBSTANTIATED", "Partially Substantiated"
        SUBSTANTIATED = "SUBSTANTIATED", "Substantiated"

    class ReviewLevel(models.TextChoices):
        MANAGER = "MANAGER", "Manager Review"
        HR_LEAD = "HR_LEAD", "HR + Functional Lead"
        PANEL = "PANEL", "Disciplinary Panel"
        EXECUTIVE = "EXECUTIVE", "Executive Oversight"

    case_number = models.CharField(max_length=30, unique=True, editable=False)
    allegation_summary = models.CharField(max_length=255)
    allegation_details = models.TextField()
    incident_date = models.DateField(null=True, blank=True)
    reported_at = models.DateTimeField(default=timezone.now)
    respondent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_cases_as_respondent",
    )
    reporter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_cases_reported",
    )
    investigator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disciplinary_cases_investigated",
    )
    violation_level = models.CharField(
        max_length=20,
        choices=ViolationLevel.choices,
        default=ViolationLevel.LEVEL_1,
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.INTAKE)
    finding = models.CharField(
        max_length=30,
        choices=Finding.choices,
        blank=True,
        null=True,
    )
    required_review_level = models.CharField(
        max_length=20,
        choices=ReviewLevel.choices,
        default=ReviewLevel.MANAGER,
    )
    emergency_case = models.BooleanField(default=False)
    repeat_offense_suspected = models.BooleanField(default=False)
    power_imbalance_flag = models.BooleanField(default=False)
    conflict_of_interest_flag = models.BooleanField(default=False)
    mental_health_context = models.BooleanField(default=False)
    cultural_context = models.BooleanField(default=False)
    interim_measures = models.TextField(blank=True)
    findings_summary = models.TextField(blank=True)
    decision_rationale = models.TextField(blank=True)
    due_process_notified_at = models.DateTimeField(null=True, blank=True)
    respondent_response_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disciplinary_cases_decided",
    )
    decision_at = models.DateTimeField(null=True, blank=True)
    appeal_window_ends_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Case"
        verbose_name_plural = "Disciplinary Cases"
        indexes = [
            models.Index(fields=["case_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["violation_level"]),
            models.Index(fields=["required_review_level"]),
        ]

    def __str__(self):
        return f"{self.case_number} - {self.allegation_summary}"

    def save(self, *args, **kwargs):
        if not self.case_number:
            year = timezone.now().year
            prefix = f"DISC-{year}-"
            latest = (
                DisciplinaryCase.objects.filter(case_number__startswith=prefix)
                .order_by("-case_number")
                .first()
            )
            next_number = 1
            if latest and latest.case_number:
                try:
                    next_number = int(latest.case_number.split("-")[-1]) + 1
                except (ValueError, IndexError):
                    next_number = 1
            self.case_number = f"{prefix}{str(next_number).zfill(5)}"

        self.required_review_level = self.compute_required_review_level()
        super().save(*args, **kwargs)

    def compute_required_review_level(self):
        if self.violation_level in [
            self.ViolationLevel.LEVEL_4,
            self.ViolationLevel.LEVEL_5,
        ]:
            return self.ReviewLevel.PANEL

        if self.violation_level == self.ViolationLevel.LEVEL_3:
            return self.ReviewLevel.PANEL

        if self.repeat_offense_suspected:
            return self.ReviewLevel.HR_LEAD

        if self.power_imbalance_flag or self.conflict_of_interest_flag:
            return self.ReviewLevel.PANEL

        if self.emergency_case:
            return self.ReviewLevel.EXECUTIVE

        if self.violation_level == self.ViolationLevel.LEVEL_2:
            return self.ReviewLevel.HR_LEAD

        return self.ReviewLevel.MANAGER

    def mark_due_process_notice(self):
        self.due_process_notified_at = timezone.now()
        self.save(update_fields=["due_process_notified_at", "updated_at"])

    def mark_respondent_response(self):
        self.respondent_response_at = timezone.now()
        self.save(update_fields=["respondent_response_at", "updated_at"])

    def move_to_investigation(self):
        self.status = self.Status.UNDER_INVESTIGATION
        self.save(update_fields=["status", "updated_at"])

    def decide(self, finding, decided_by, rationale):
        self.finding = finding
        self.decision_rationale = rationale
        self.decided_by = decided_by
        self.decision_at = timezone.now()
        self.appeal_window_ends_at = timezone.now() + timedelta(days=10)
        self.status = self.Status.DECIDED
        self.save(
            update_fields=[
                "finding",
                "decision_rationale",
                "decided_by",
                "decision_at",
                "appeal_window_ends_at",
                "status",
                "updated_at",
            ]
        )

    def close_case(self):
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at", "updated_at"])


class DisciplinaryEvidence(BaseModel):
    class EvidenceType(models.TextChoices):
        DOCUMENT = "DOCUMENT", "Document"
        EMAIL = "EMAIL", "Email"
        CHAT = "CHAT", "Chat"
        SYSTEM_LOG = "SYSTEM_LOG", "System Log"
        CCTV = "CCTV", "CCTV"
        WITNESS_STATEMENT = "WITNESS_STATEMENT", "Witness Statement"
        OTHER = "OTHER", "Other"

    case = models.ForeignKey(
        DisciplinaryCase,
        on_delete=models.CASCADE,
        related_name="evidence_items",
    )
    title = models.CharField(max_length=255)
    evidence_type = models.CharField(max_length=30, choices=EvidenceType.choices)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="disciplinary/evidence/", blank=True, null=True)
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_evidence_submitted",
    )
    is_confidential = models.BooleanField(default=False)
    chain_of_custody_notes = models.TextField(blank=True)
    reliability_score = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Evidence"
        verbose_name_plural = "Disciplinary Evidence"

    def __str__(self):
        return f"{self.case.case_number} - {self.title}"

    def clean(self):
        if not self.description and not self.file:
            raise ValidationError("Provide either a description or an uploaded file.")

        if self.reliability_score and not 1 <= self.reliability_score <= 5:
            raise ValidationError("Reliability score must be between 1 and 5.")


class DisciplinarySanction(BaseModel):
    class SanctionType(models.TextChoices):
        COACHING = "COACHING", "Coaching"
        WRITTEN_WARNING = "WRITTEN_WARNING", "Written Warning"
        FINAL_WARNING = "FINAL_WARNING", "Final Warning"
        TRAINING = "TRAINING", "Mandatory Training"
        PERFORMANCE_PLAN = "PERFORMANCE_PLAN", "Performance Improvement Plan"
        ROLE_RESTRICTION = "ROLE_RESTRICTION", "Role Restriction"
        SUSPENSION = "SUSPENSION", "Suspension"
        DEMOTION = "DEMOTION", "Demotion"
        TERMINATION_REVIEW = "TERMINATION_REVIEW", "Termination Review"
        TERMINATION = "TERMINATION", "Termination"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        REVOKED = "REVOKED", "Revoked"

    case = models.ForeignKey(
        DisciplinaryCase,
        on_delete=models.CASCADE,
        related_name="sanctions",
    )
    sanction_type = models.CharField(max_length=30, choices=SanctionType.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE)
    rationale = models.TextField()
    effective_date = models.DateField(default=timezone.now)
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    compliance_due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_rehabilitative = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_sanctions_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Sanction"
        verbose_name_plural = "Disciplinary Sanctions"

    def __str__(self):
        return f"{self.case.case_number} - {self.get_sanction_type_display()}"

    def clean(self):
        high_impact_sanctions = [
            self.SanctionType.DEMOTION,
            self.SanctionType.TERMINATION_REVIEW,
            self.SanctionType.TERMINATION,
        ]
        if (
            self.sanction_type in high_impact_sanctions
            and self.case.violation_level
            not in [DisciplinaryCase.ViolationLevel.LEVEL_3, DisciplinaryCase.ViolationLevel.LEVEL_4, DisciplinaryCase.ViolationLevel.LEVEL_5]
        ):
            raise ValidationError(
                "High-impact sanctions require a case severity of Level 3 or above."
            )

        if (
            self.sanction_type == self.SanctionType.SUSPENSION
            and not self.duration_days
        ):
            raise ValidationError("Suspension sanctions require duration in days.")

    @property
    def end_date(self):
        if not self.duration_days:
            return None
        return self.effective_date + timedelta(days=self.duration_days - 1)

    def is_effective_on(self, target_date):
        if target_date < self.effective_date:
            return False
        if self.end_date is None:
            return True
        return target_date <= self.end_date

    def overlaps_period(self, period_start, period_end):
        if self.effective_date > period_end:
            return False
        sanction_end = self.end_date
        if sanction_end is None:
            return True
        return sanction_end >= period_start

    def _apply_employment_effects(self):
        if (
            self.status != self.Status.ACTIVE
            or self.sanction_type != self.SanctionType.TERMINATION
        ):
            return

        today = timezone.localdate()
        if self.effective_date and self.effective_date > today:
            return

        respondent = self.case.respondent
        if not respondent:
            return

        if respondent.is_active:
            respondent.is_active = False
            respondent.save(update_fields=["is_active"])

        EmployeeProfile = apps.get_model("payroll", "EmployeeProfile")
        try:
            employee = EmployeeProfile.objects.get(user=respondent)
        except EmployeeProfile.DoesNotExist:
            return

        if employee.status != "terminated":
            employee.status = "terminated"
            employee.save(update_fields=["status"])

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._apply_employment_effects()

    def mark_completed(self):
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])


class DisciplinaryAppeal(BaseModel):
    class AppealGround(models.TextChoices):
        PROCEDURAL_UNFAIRNESS = "PROCEDURAL_UNFAIRNESS", "Procedural Unfairness"
        NEW_EVIDENCE = "NEW_EVIDENCE", "New Evidence"
        BIAS_OR_CONFLICT = "BIAS_OR_CONFLICT", "Bias or Conflict of Interest"
        DISPROPORTIONATE_SANCTION = "DISPROPORTIONATE_SANCTION", "Disproportionate Sanction"

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        UPHELD = "UPHELD", "Upheld"
        MODIFIED = "MODIFIED", "Modified"
        OVERTURNED = "OVERTURNED", "Overturned"
        REINVESTIGATION_ORDERED = "REINVESTIGATION_ORDERED", "Reinvestigation Ordered"
        REJECTED = "REJECTED", "Rejected"

    case = models.ForeignKey(
        DisciplinaryCase,
        on_delete=models.CASCADE,
        related_name="appeals",
    )
    appellant = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_appeals_filed",
    )
    grounds = models.CharField(max_length=40, choices=AppealGround.choices)
    details = models.TextField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SUBMITTED)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disciplinary_appeals_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    outcome_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Appeal"
        verbose_name_plural = "Disciplinary Appeals"

    def __str__(self):
        return f"Appeal for {self.case.case_number}"

    def clean(self):
        if (
            not self.pk
            and self.case.appeal_window_ends_at
            and timezone.now() > self.case.appeal_window_ends_at
        ):
            raise ValidationError("Appeal window has closed for this case.")
