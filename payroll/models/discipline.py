"""HR disciplinary cases, evidence, sanctions and appeals.

These models lived in accounting and moved here (payroll migration 0095).
Their tables keep the original accounting_* names, so no data moved.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounting.models import BaseModel

User = get_user_model()


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

    case_number = models.CharField(max_length=30, editable=False)
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="disciplinary_cases",
        db_index=True,
    )
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
        db_table = "accounting_disciplinarycase"
        permissions = [("review_hr_disciplinarycase", "Can approve HR lead disciplinary decisions"),
                       ("review_panel_disciplinarycase", "Can approve panel disciplinary decisions"),
                       ("review_executive_disciplinarycase", "Can approve executive disciplinary decisions")]
        base_manager_name = "objects"
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Case"
        verbose_name_plural = "Disciplinary Cases"
        indexes = [
            models.Index(fields=["case_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["violation_level"]),
            models.Index(fields=["required_review_level"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "case_number"],
                name="uniq_case_company_case_number",
            ),
        ]

    def __str__(self):
        return f"{self.case_number} - {self.allegation_summary}"

    def save(self, *args, **kwargs):
        if self.company_id is None:
            respondent_company = getattr(self.respondent, "active_company", None) or getattr(
                self.respondent, "company", None
            )
            reporter_company = getattr(self.reporter, "active_company", None) or getattr(
                self.reporter, "company", None
            )
            self.company = respondent_company or reporter_company

        if not self.case_number:
            year = timezone.now().year
            prefix = f"DISC-{year}-"
            latest = (
                DisciplinaryCase.objects.filter(
                    company=self.company, case_number__startswith=prefix
                )
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
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"required_review_level"}
        super().save(*args, **kwargs)

    def compute_required_review_level(self):
        if self.emergency_case:
            return self.ReviewLevel.EXECUTIVE
        if (self.violation_level in [self.ViolationLevel.LEVEL_3, self.ViolationLevel.LEVEL_4, self.ViolationLevel.LEVEL_5]
                or self.power_imbalance_flag or self.conflict_of_interest_flag):
            return self.ReviewLevel.PANEL
        if self.violation_level == self.ViolationLevel.LEVEL_2 or self.repeat_offense_suspected:
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

    def decide(self, finding, decided_by, rationale, findings_summary="", **workflow_options):
        from accounting.discipline_approval_actions import submit_case_decision
        actor = workflow_options.get("approval_actor") or decided_by
        return submit_case_decision(case=self, actor=actor, finding=finding, rationale=rationale,
                                    findings_summary=findings_summary)

    def close_case(self):
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at", "updated_at"])


class DisciplinaryCaseAudit(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        INVESTIGATION_STARTED = "investigation_started", "Investigation Started"
        DECISION_RECORDED = "decision_recorded", "Decision Recorded"
        SANCTION_CREATED = "sanction_created", "Sanction Created"
        SANCTION_COMPLETED = "sanction_completed", "Sanction Completed"
        APPEAL_SUBMITTED = "appeal_submitted", "Appeal Submitted"
        APPEAL_REVIEWED = "appeal_reviewed", "Appeal Reviewed"
        STATUS_CHANGED = "status_changed", "Status Changed"
        CASE_CLOSED = "case_closed", "Case Closed"

    case = models.ForeignKey(
        DisciplinaryCase,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    action = models.CharField(max_length=40, choices=Action.choices)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disciplinary_case_audit_events",
    )
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounting_disciplinarycaseaudit"
        ordering = ["-timestamp", "-id"]
        indexes = [
            models.Index(fields=["case", "timestamp"]),
            models.Index(fields=["actor", "timestamp"]),
            models.Index(fields=["action", "timestamp"]),
        ]
        verbose_name = "Disciplinary Case Audit Event"
        verbose_name_plural = "Disciplinary Case Audit Events"

    def __str__(self):
        return f"{self.case_id}:{self.action} by {self.actor_id}"


def log_disciplinary_case_audit(case, action, actor=None, details=None):
    if case is None:
        return None
    actor = actor if getattr(actor, "is_authenticated", False) else None
    return DisciplinaryCaseAudit.objects.create(
        case=case,
        action=action,
        actor=actor,
        details=details or {},
    )


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
        db_table = "accounting_disciplinaryevidence"
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
    employment_effect_snapshot = models.JSONField(default=dict, blank=True)

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
        PENDING = "PENDING", _("Pending approval")
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        REVOKED = "REVOKED", "Revoked"

    case = models.ForeignKey(
        DisciplinaryCase,
        on_delete=models.CASCADE,
        related_name="sanctions",
    )
    sanction_type = models.CharField(max_length=30, choices=SanctionType.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
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
        db_table = "accounting_disciplinarysanction"
        base_manager_name = "objects"
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
        from accounting.discipline_services import apply_termination
        apply_termination(self)

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
        db_table = "accounting_disciplinaryappeal"
        base_manager_name = "objects"
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Appeal"
        verbose_name_plural = "Disciplinary Appeals"

    def __str__(self):
        return f"Appeal for {self.case.case_number}"

    def clean(self):
        if not self.pk and self.case_id and self.case.status not in {DisciplinaryCase.Status.DECIDED, DisciplinaryCase.Status.CLOSED}:
            raise ValidationError("A finalized case decision is required before filing an appeal.")
        if (
            not self.pk
            and self.case.appeal_window_ends_at
            and timezone.now() > self.case.appeal_window_ends_at
        ):
            raise ValidationError("Appeal window has closed for this case.")
