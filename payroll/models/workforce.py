from payroll.workflow_managers import HRWorkflowManager, HRWorkflowQuerySet
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone

from payroll.models.utils import SoftDeleteModel


class Position(SoftDeleteModel):
    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full time"
        PART_TIME = "part_time", "Part time"
        CONTRACT = "contract", "Contract"
        INTERN = "intern", "Intern"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        FILLED = "filled", "Filled"
        CLOSED = "closed", "Closed"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="positions",
    )
    department = models.ForeignKey(
        "payroll.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="positions",
    )
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True)
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    headcount = models.PositiveIntegerField(default=1)
    reports_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_reports",
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        unique_together = ("company", "title", "department")

    def __str__(self):
        return self.title


class HiringStage(SoftDeleteModel):
    class StageType(models.TextChoices):
        SOURCED = "sourced", "Sourced"
        SCREENING = "screening", "Screening"
        STRUCTURED_INTERVIEW = "structured_interview", "Structured Interview"
        SCORECARD_REVIEW = "scorecard_review", "Scorecard Review"
        REFERENCE_CHECK = "reference_check", "Reference Check"
        OFFER = "offer", "Offer"
        HIRED = "hired", "Hired"
        REJECTED = "rejected", "Rejected"

    company = models.ForeignKey("company.Company", on_delete=models.CASCADE, related_name="hiring_stages")
    name = models.CharField(max_length=120)
    stage_type = models.CharField(max_length=40, choices=StageType.choices)
    sequence = models.PositiveIntegerField(default=1)
    requires_scorecard = models.BooleanField(default=False)
    requires_approval = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    guidance = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sequence", "name"]
        unique_together = ("company", "stage_type")

    def __str__(self):
        return self.name


class JobRequisition(SoftDeleteModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        ON_HOLD = "on_hold", "On hold"
        FILLED = "filled", "Filled"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey("company.Company", on_delete=models.CASCADE, related_name="job_requisitions")
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name="requisitions")
    title = models.CharField(max_length=255)
    hiring_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_job_requisitions",
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opened_job_requisitions",
    )
    headcount = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    compensation_min = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    compensation_max = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="NGN")
    outcomes_90_days = models.TextField(blank=True)
    must_have_criteria = models.JSONField(default=list, blank=True)
    scorecard_template = models.JSONField(default=dict, blank=True)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-opened_at", "title"]

    def __str__(self):
        return self.title


class HiringCandidate(SoftDeleteModel):
    objects = HRWorkflowManager()
    all_objects = HRWorkflowQuerySet.as_manager()

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROCESS = "in_process", "In process"
        OFFER = "offer", "Offer"
        HIRED = "hired", "Hired"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    company = models.ForeignKey("company.Company", on_delete=models.CASCADE, related_name="hiring_candidates")
    requisition = models.ForeignKey(JobRequisition, on_delete=models.CASCADE, related_name="candidates")
    current_stage = models.ForeignKey(
        HiringStage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_candidates",
    )
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    source = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    consent_to_process = models.BooleanField(default=False)
    consent_recorded_at = models.DateTimeField(null=True, blank=True)
    consent_expires_at = models.DateTimeField(null=True, blank=True)
    consent_version = models.CharField(max_length=50, blank=True)
    structured_notes = models.JSONField(default=dict, blank=True)
    applied_at = models.DateTimeField(default=timezone.now)
    hired_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        base_manager_name = "all_objects"
        ordering = ["-applied_at", "last_name", "first_name"]
        unique_together = ("requisition", "email")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_consent_expired(self):
        return bool(self.consent_expires_at and self.consent_expires_at <= timezone.now())

    def delete(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_delete
        guard_delete(self)
        return super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        from payroll.services.hr_workflow import require_execution
        old = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if self.current_stage_id and self.current_stage.requires_approval and (old is None or old.current_stage_id != self.current_stage_id):
            require_execution(self, "hiring.advance")
        was_new = self.pk is None
        previous_consent = None
        if not was_new:
            previous_consent = (
                HiringCandidate.objects.filter(pk=self.pk)
                .values_list("consent_to_process", flat=True)
                .first()
            )
        if self.consent_to_process and self.consent_recorded_at is None:
            self.consent_recorded_at = timezone.now()
        if self.consent_to_process and self.consent_expires_at is None:
            self.consent_expires_at = timezone.now() + timedelta(days=365)
        super().save(*args, **kwargs)
        if self.consent_to_process and (was_new or previous_consent is False):
            CandidateConsent.objects.get_or_create(
                candidate=self,
                consent_given=True,
                version=self.consent_version or "default",
                defaults={
                    "recorded_at": self.consent_recorded_at or timezone.now(),
                    "expires_at": self.consent_expires_at,
                    "source": "candidate",
                },
            )

    def request_reconsent(self, *, version: str = ""):
        self.consent_to_process = False
        self.consent_version = version
        self.consent_expires_at = timezone.now()
        self.save(
            update_fields=[
                "consent_to_process",
                "consent_version",
                "consent_expires_at",
                "updated_at",
            ]
        )
        return CandidateConsent.objects.create(
            candidate=self,
            consent_given=False,
            version=version,
            source="reconsent",
            metadata={"reason": "reconsent_requested"},
        )


class CandidateConsent(SoftDeleteModel):
    candidate = models.ForeignKey(
        HiringCandidate,
        on_delete=models.CASCADE,
        related_name="consent_records",
    )
    consent_given = models.BooleanField(default=True)
    version = models.CharField(max_length=50, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    captured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="captured_candidate_consents",
    )
    source = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [
            models.Index(fields=["candidate", "consent_given"]),
            models.Index(fields=["expires_at"]),
        ]

    @property
    def is_active(self):
        return bool(
            self.consent_given
            and (self.expires_at is None or self.expires_at > timezone.now())
        )

    def __str__(self):
        return f"{self.candidate} consent {self.version or 'default'}"


class HiringStageScorecard(SoftDeleteModel):
    class Recommendation(models.TextChoices):
        STRONG_YES = "strong_yes", "Strong yes"
        YES = "yes", "Yes"
        NO = "no", "No"
        STRONG_NO = "strong_no", "Strong no"

    company = models.ForeignKey("company.Company", on_delete=models.CASCADE, related_name="hiring_scorecards")
    candidate = models.ForeignKey(HiringCandidate, on_delete=models.CASCADE, related_name="scorecards")
    stage = models.ForeignKey(HiringStage, on_delete=models.PROTECT, related_name="scorecards")
    interviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hiring_scorecards",
    )
    competency_scores = models.JSONField(default=dict, blank=True)
    average_score = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    recommendation = models.CharField(max_length=20, choices=Recommendation.choices)
    notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        unique_together = ("candidate", "stage", "interviewer")

    def __str__(self):
        return f"{self.candidate} - {self.stage}"


class JobOffer(SoftDeleteModel):
    objects = HRWorkflowManager()
    all_objects = HRWorkflowQuerySet.as_manager()

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        WITHDRAWN = "withdrawn", "Withdrawn"

    candidate = models.ForeignKey(HiringCandidate, on_delete=models.CASCADE, related_name="offers")
    company = models.ForeignKey("company.Company", on_delete=models.CASCADE, related_name="job_offers")
    title = models.CharField(max_length=255)
    employment_type = models.CharField(max_length=20, choices=Position.EmploymentType.choices)
    salary_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")
    start_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_job_offers",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    terms = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def delete(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_delete
        guard_delete(self)
        return super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_state
        from django.core.exceptions import PermissionDenied
        old = type(self)._base_manager.filter(pk=self.pk).first() if self.pk else None
        written = kwargs.get("update_fields")
        status_written = written is None or "status" in written
        if old is None and self.status != self.Status.DRAFT:
            raise PermissionDenied("New offers must be drafts submitted for independent release approval.")
        if old is not None and status_written and old.status != self.status:
            permitted = {
                self.Status.DRAFT: {self.Status.SENT, self.Status.WITHDRAWN},
                self.Status.SENT: {self.Status.ACCEPTED, self.Status.DECLINED, self.Status.WITHDRAWN},
            }
            if self.status not in permitted.get(old.status, set()):
                raise PermissionDenied("Offer acknowledgment requires a released offer; completed history cannot be reopened.")
        if old is not None and old.status in {self.Status.ACCEPTED, self.Status.DECLINED, self.Status.WITHDRAWN}:
            if any(field.name not in {"updated_at"} and (written is None or field.name in written or field.attname in written)
                   and getattr(old, field.attname) != getattr(self, field.attname) for field in self._meta.concrete_fields):
                raise PermissionDenied("Completed offer history is immutable.")
        if self.status == "sent" and (not old or old.status != "sent"):
            guard_state(self, "hiring.offer.release", {"sent"}, (), update_fields=kwargs.get("update_fields"))
        if old and old.status == self.Status.SENT:
            fields = tuple(field.attname for field in self._meta.concrete_fields
                           if field.name not in {"status", "accepted_at", "updated_at"})
            guard_state(self, "hiring.offer.release", set(), fields, update_fields=written)
            if (written is None or "accepted_at" in written) and self.accepted_at != old.accepted_at and self.status != self.Status.ACCEPTED:
                raise PermissionDenied("Acceptance metadata requires acknowledgment of the released offer.")
        return super().save(*args, **kwargs)

    class Meta:
        base_manager_name = "all_objects"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} offer for {self.candidate}"


class Skill(SoftDeleteModel):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="skills",
    )
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("company", "name")

    def __str__(self):
        return self.name


class EmployeeSkill(SoftDeleteModel):
    class Proficiency(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"
        EXPERT = "expert", "Expert"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="employee_skills",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="skills",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="employee_links",
    )
    proficiency = models.CharField(
        max_length=20,
        choices=Proficiency.choices,
        default=Proficiency.BEGINNER,
    )
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    assessed_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("employee", "skill")

    def __str__(self):
        return f"{self.employee} - {self.skill}"


class AttendanceRecord(SoftDeleteModel):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        REMOTE = "remote", "Remote"
        LEAVE = "leave", "Leave"
        HALF_DAY = "half_day", "Half day"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    work_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PRESENT,
    )
    clock_in = models.DateTimeField(null=True, blank=True)
    clock_out = models.DateTimeField(null=True, blank=True)
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    location_label = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_date", "employee__first_name"]
        unique_together = ("employee", "work_date")

    def clean(self):
        """Odoo-style attendance validity (P1-7).

        - a clock-out requires a clock-in;
        - at most one open check-in (clocked in, not clocked out) per employee;
        - no two sessions for the same employee may overlap in time
          (back-to-back sessions that merely touch are allowed).

        Status-only rows (leave/absent/half-day with no clock times) are not
        check-ins and are exempt from the check-in rules.
        """
        super().clean()
        if self.clock_out and not self.clock_in:
            raise ValidationError(
                {"clock_out": "A clock-out requires a clock-in."}
            )
        if not self.clock_in:
            return

        from django.utils import timezone

        def _aware(value):
            # Rows read back from the DB are tz-aware; freshly assigned
            # values may be naive. Normalise before comparing.
            if value is None or timezone.is_aware(value):
                return value
            return timezone.make_aware(value, timezone.get_current_timezone())

        self_in = _aware(self.clock_in)
        self_out = _aware(self.clock_out)

        others = type(self).objects.filter(employee_id=self.employee_id)
        if self.pk:
            others = others.exclude(pk=self.pk)
        others = others.filter(clock_in__isnull=False)

        if self_out is None:
            # One open check-in per employee (Odoo hr_attendance).
            if others.filter(clock_out__isnull=True).exists():
                raise ValidationError(
                    "An employee can only have one open check-in."
                )

        # No overlapping sessions: intersecting [clock_in, clock_out]
        # intervals are rejected; None means an open-ended session.
        for other in others:
            other_in = _aware(other.clock_in)
            other_out = _aware(other.clock_out)
            starts_before_other_ends = (
                other_out is None or self_in < other_out
            )
            other_starts_before_ends = (
                self_out is None or other_in < self_out
            )
            if starts_before_other_ends and other_starts_before_ends:
                raise ValidationError(
                    "Attendance records for an employee cannot overlap in time."
                )

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is None or not set(update_fields).isdisjoint(
            {"clock_in", "clock_out", "work_date", "employee"}
        ):
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} - {self.work_date}"


class EmployeeDocument(SoftDeleteModel):
    class DocumentType(models.TextChoices):
        CONTRACT = "contract", "Contract"
        POLICY = "policy", "Policy"
        IDENTIFICATION = "identification", "Identification"
        CERTIFICATION = "certification", "Certification"
        ONBOARDING = "onboarding", "Onboarding"
        OTHER = "other", "Other"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="employee_documents",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    document_type = models.CharField(
        max_length=30,
        choices=DocumentType.choices,
        default=DocumentType.OTHER,
    )
    file = models.FileField(upload_to="employee_documents/", blank=True, null=True)
    acknowledgement_required = models.BooleanField(default=False)
    is_acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class AssetCategory(SoftDeleteModel):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="asset_categories",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("company", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class EmployeeAsset(SoftDeleteModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        IN_USE = "in_use", "In use"
        RETURNED = "returned", "Returned"
        LOST = "lost", "Lost"
        RETIRED = "retired", "Retired"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="employee_assets",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets",
    )
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets",
    )
    name = models.CharField(max_length=255)
    asset_tag = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    replacement_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Recovery value charged at exit if the asset is not returned "
            "(P2-15). Empty means the asset carries no recoverable value."
        ),
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("company", "asset_tag")
        ordering = ["asset_tag"]

    def __str__(self):
        return self.asset_tag


class WorkflowTemplate(SoftDeleteModel):
    class WorkflowType(models.TextChoices):
        ONBOARDING = "onboarding", "Onboarding"
        OFFBOARDING = "offboarding", "Offboarding"
        APPROVAL = "approval", "Approval"
        PROBATION = "probation", "Probation"
        DOCUMENT = "document", "Document"
        OTHER = "other", "Other"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="workflow_templates",
    )
    name = models.CharField(max_length=255)
    workflow_type = models.CharField(
        max_length=30,
        choices=WorkflowType.choices,
        default=WorkflowType.OTHER,
    )
    trigger_event = models.CharField(max_length=100, blank=True)
    definition = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("company", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class WorkflowExecution(SoftDeleteModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="workflow_executions",
    )
    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="executions",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_executions",
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_workflow_executions",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    context = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.template} - {self.status}"


def create_standard_hiring_stages(company):
    from payroll.services.hiring import create_standard_hiring_stages as service

    return service(company)


def record_candidate_scorecard(*, candidate, stage, interviewer, competency_scores, recommendation, notes=""):
    from payroll.services.hiring import record_candidate_scorecard as service

    return service(
        candidate=candidate,
        stage=stage,
        interviewer=interviewer,
        competency_scores=competency_scores,
        recommendation=recommendation,
        notes=notes,
    )


def advance_candidate(candidate, next_stage, advanced_by=None):
    from payroll.services.hiring import advance_candidate as service

    return service(candidate, next_stage, advanced_by=advanced_by)


def create_job_offer(*, candidate, title, employment_type, salary_amount, currency, start_date, created_by=None, terms=None):
    from payroll.services.hiring import create_job_offer as service

    return service(
        candidate=candidate,
        title=title,
        employment_type=employment_type,
        salary_amount=salary_amount,
        currency=currency,
        start_date=start_date,
        created_by=created_by,
        terms=terms,
    )


def accept_job_offer(offer, accepted_by=None):
    from payroll.services.hiring import accept_job_offer as service

    return service(offer, accepted_by=accepted_by)


class Goal(SoftDeleteModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        AT_RISK = "at_risk", "At risk"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="goals",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="goals",
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_goals",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    cycle = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    progress_percent = models.PositiveSmallIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class OneOnOne(SoftDeleteModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="one_on_ones",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="one_on_ones",
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="one_on_ones_as_manager",
    )
    scheduled_for = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    agenda = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_for"]

    def __str__(self):
        return f"1:1 - {self.employee}"


class SurveyTemplate(SoftDeleteModel):
    class SurveyType(models.TextChoices):
        PULSE = "pulse", "Pulse"
        ENGAGEMENT = "engagement", "Engagement"
        EXIT = "exit", "Exit"
        ONBOARDING = "onboarding", "Onboarding"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="survey_templates",
    )
    name = models.CharField(max_length=255)
    survey_type = models.CharField(
        max_length=20,
        choices=SurveyType.choices,
        default=SurveyType.PULSE,
    )
    description = models.TextField(blank=True)
    is_anonymous = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("company", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class SurveyQuestion(SoftDeleteModel):
    class QuestionType(models.TextChoices):
        TEXT = "text", "Text"
        RATING = "rating", "Rating"
        SINGLE_CHOICE = "single_choice", "Single choice"
        MULTI_CHOICE = "multi_choice", "Multi choice"

    survey = models.ForeignKey(
        SurveyTemplate,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    prompt = models.TextField()
    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.TEXT,
    )
    choices = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=1)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.prompt[:50]


class SurveyResponse(SoftDeleteModel):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="survey_responses",
    )
    survey = models.ForeignKey(
        SurveyTemplate,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    question = models.ForeignKey(
        SurveyQuestion,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="survey_responses",
    )
    text_response = models.TextField(blank=True)
    numeric_response = models.IntegerField(null=True, blank=True)
    choice_response = models.JSONField(default=list, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.survey} response"


class LearningCourse(SoftDeleteModel):
    class CourseType(models.TextChoices):
        COMPLIANCE = "compliance", "Compliance"
        ROLE_BASED = "role_based", "Role based"
        LEADERSHIP = "leadership", "Leadership"
        TECHNICAL = "technical", "Technical"

    class DeliveryMode(models.TextChoices):
        SELF_PACED = "self_paced", "Self paced"
        INSTRUCTOR_LED = "instructor_led", "Instructor led"
        HYBRID = "hybrid", "Hybrid"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="learning_courses",
    )
    title = models.CharField(max_length=255)
    course_type = models.CharField(
        max_length=20,
        choices=CourseType.choices,
        default=CourseType.ROLE_BASED,
    )
    delivery_mode = models.CharField(
        max_length=20,
        choices=DeliveryMode.choices,
        default=DeliveryMode.SELF_PACED,
    )
    description = models.TextField(blank=True)
    estimated_minutes = models.PositiveIntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class CourseEnrollment(SoftDeleteModel):
    class Status(models.TextChoices):
        ENROLLED = "enrolled", "Enrolled"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        OVERDUE = "overdue", "Overdue"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="course_enrollments",
    )
    course = models.ForeignKey(
        LearningCourse,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="course_enrollments",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ENROLLED,
    )
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("course", "employee")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.course} - {self.employee}"


class BenefitPlan(SoftDeleteModel):
    class PlanType(models.TextChoices):
        HEALTH = "health", "Health"
        PENSION = "pension", "Pension"
        TRANSPORT = "transport", "Transport"
        WELLNESS = "wellness", "Wellness"
        OTHER = "other", "Other"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="benefit_plans",
    )
    name = models.CharField(max_length=255)
    plan_type = models.CharField(
        max_length=20,
        choices=PlanType.choices,
        default=PlanType.OTHER,
    )
    description = models.TextField(blank=True)
    enrollment_window_start = models.DateField(null=True, blank=True)
    enrollment_window_end = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("company", "name")

    def __str__(self):
        return self.name


class BenefitEnrollment(SoftDeleteModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ENROLLED = "enrolled", "Enrolled"
        WAIVED = "waived", "Waived"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="benefit_enrollments",
    )
    plan = models.ForeignKey(
        BenefitPlan,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="benefit_enrollments",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    effective_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("plan", "employee")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.plan} - {self.employee}"


class OffboardingChecklist(SoftDeleteModel):
    objects = HRWorkflowManager()
    all_objects = HRWorkflowQuerySet.as_manager()

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="offboarding_checklists",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="offboarding_checklists",
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    last_working_day = models.DateField()
    reason = models.CharField(
        max_length=50,
        choices=[
            ("RESIGNATION", "Resignation"),
            ("TERMINATION", "Termination"),
            ("RETIREMENT", "Retirement"),
            ("CONTRACT_EXPIRY", "Contract Expiry"),
            ("OTHER", "Other"),
        ],
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("IN_PROGRESS", "In Progress"),
            ("COMPLETED", "Completed"),
            ("CANCELLED", "Cancelled"),
        ],
        default="IN_PROGRESS",
    )
    exit_interview_completed = models.BooleanField(default=False)
    exit_interview_notes = models.TextField(blank=True)
    final_settlement_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def delete(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_delete
        guard_delete(self)
        return super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_state
        guard_state(self, "offboarding.complete", {"COMPLETED"}, (), update_fields=kwargs.get("update_fields"))
        old = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if old and old.status == "COMPLETED":
            guard_state(self, "offboarding.complete", set(), ("company_id", "employee_id", "initiated_by_id", "last_working_day", "reason", "final_settlement_amount"), update_fields=kwargs.get("update_fields"))
        return super().save(*args, **kwargs)

    class Meta:
        base_manager_name = "all_objects"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Offboarding: {self.employee} ({self.get_reason_display()})"


class OffboardingTask(SoftDeleteModel):
    checklist = models.ForeignKey(
        OffboardingChecklist,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    category = models.CharField(
        max_length=30,
        choices=[
            ("ASSET_RETURN", "Asset Return"),
            ("ACCESS_REVOCATION", "Access Revocation"),
            ("KNOWLEDGE_TRANSFER", "Knowledge Transfer"),
            ("DOCUMENTATION", "Documentation"),
            ("FINANCIAL", "Financial Settlement"),
            ("IT", "IT Systems"),
            ("HR", "HR Administration"),
        ],
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"


class OvertimePolicy(SoftDeleteModel):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="overtime_policies",
    )
    daily_threshold_hours = models.DecimalField(
        max_digits=4, decimal_places=2, default=8.00
    )
    weekly_threshold_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=40.00
    )
    weekday_rate_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=1.50
    )
    weekend_rate_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=2.00
    )
    holiday_rate_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=2.00
    )
    max_daily_overtime_hours = models.DecimalField(
        max_digits=4, decimal_places=2, default=4.00
    )
    requires_approval = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Overtime policies"

    def __str__(self):
        return f"Overtime Policy ({self.company})"


class OvertimeEntry(SoftDeleteModel):
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="created_overtimeentry_requests")

    objects = HRWorkflowManager()
    all_objects = HRWorkflowQuerySet.as_manager()

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="overtime_entries",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="overtime_entries",
    )
    attendance = models.OneToOneField(
        "AttendanceRecord",
        on_delete=models.CASCADE,
        related_name="overtime_entry",
        null=True,
        blank=True,
    )
    date = models.DateField()
    hours = models.DecimalField(max_digits=4, decimal_places=2)
    rate_multiplier = models.DecimalField(max_digits=4, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("APPROVED", "Approved"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_delete
        guard_delete(self)
        return super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_requester
        guard_requester(self, kwargs.get("update_fields"))
        from payroll.services.hr_workflow import guard_state
        guard_state(self, "overtime.approve", {"APPROVED", "REJECTED"}, ("approved_by_id", "approved_at"), update_fields=kwargs.get("update_fields"))
        old = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if old and old.status == "APPROVED":
            guard_state(self, "overtime.approve", set(), ("company_id", "employee_id", "attendance_id", "hours", "rate_multiplier", "date"), update_fields=kwargs.get("update_fields"))
        return super().save(*args, **kwargs)

    class Meta:
        base_manager_name = "all_objects"
        ordering = ["-date"]

    def __str__(self):
        return f"OT: {self.employee} - {self.date} ({self.hours}h)"


class Shift(SoftDeleteModel):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="shifts",
    )
    name = models.CharField(max_length=100)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_minutes = models.PositiveIntegerField(default=60)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_time"]

    def __str__(self):
        return f"{self.name} ({self.start_time}-{self.end_time})"


class ShiftTemplate(SoftDeleteModel):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="shift_templates",
    )
    name = models.CharField(max_length=100)
    monday = models.ForeignKey(
        Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    tuesday = models.ForeignKey(
        Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    wednesday = models.ForeignKey(
        Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    thursday = models.ForeignKey(
        Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    friday = models.ForeignKey(
        Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    saturday = models.ForeignKey(
        Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    sunday = models.ForeignKey(
        Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_shift_for_day(self, date_obj):
        day_name = date_obj.strftime("%A").lower()
        return getattr(self, day_name, None)

    def __str__(self):
        return self.name


class ShiftAssignment(SoftDeleteModel):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="shift_assignments",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="shift_assignments",
    )
    shift_template = models.ForeignKey(
        ShiftTemplate, on_delete=models.CASCADE
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.employee} -> {self.shift_template}"


class Timesheet(SoftDeleteModel):
    """A weekly roll-up of raw attendance awaiting approval (P2-14).

    BambooHR time tracking separates raw clock data from approved hours: an
    attendance row is a *record* of a clock event, whereas a timesheet is the
    *reviewed* set of hours an employee certifies and a manager approves before
    those hours become payable. This model is that reviewed container — one row
    per (employee, week) — and links the ``ApprovalRequest`` that carries it
    through the existing approval policy machinery.

    The week boundary is Monday-anchored (ISO). ``status`` mirrors the
    ``ApprovalRequest`` lifecycle rather than duplicating it: the request is the
    source of truth, and this field is a denormalised convenience for list
    views and the payroll pre-flight check.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="timesheets",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="timesheets",
    )
    week_start = models.DateField(
        help_text="Monday of the timesheet's week (ISO week boundary)."
    )
    # Total hours the employee certifies for the week. Seeded from the sum of
    # AttendanceRecord.hours_worked but editable before submission, so an
    # employee can correct a missed clock-out rather than leaving raw data
    # unreviewed.
    total_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_timesheets",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approval_request = models.ForeignKey(
        "approvals.ApprovalRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timesheets",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_timesheets",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-week_start", "employee__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "week_start"],
                name="unique_employee_timesheet_week",
            )
        ]

    def clean(self):
        """Anchor the week to Monday and keep the total sane."""
        super().clean()
        if self.week_start and self.week_start.weekday() != 0:
            raise ValidationError(
                {"week_start": "A timesheet week must start on a Monday."}
            )
        if self.total_hours is not None and self.total_hours < 0:
            raise ValidationError({"total_hours": "Hours cannot be negative."})
        if self.total_hours is not None and self.total_hours > Decimal("168"):
            raise ValidationError(
                {"total_hours": "A week cannot exceed 168 hours."}
            )

    @property
    def week_end(self):
        """Sunday of the timesheet's week."""
        return self.week_start + timedelta(days=6)

    @property
    def is_payable(self):
        """Approved hours only; draft/submitted/rejected hours are not payable.

        This is the property the payroll pre-flight check reads, keeping raw
        clock data out of gross pay until a manager has certified it.
        """
        return self.status == self.Status.APPROVED

    def approve(self, actor):
        """Mark the timesheet approved (called from the approval adapter)."""
        self.status = self.Status.APPROVED
        self.approved_by = actor
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at"])

    def __str__(self):
        return f"{self.employee} - week of {self.week_start}"


class ExitSettlement(SoftDeleteModel):
    """The single Full-and-Final settlement document (P2-15).

    Frappe's Full and Final Statement combines payables, receivables and
    asset recovery into one statement with journal linkage; paroll previously
    spread this across ``OffboardingChecklist.final_settlement_amount`` (a
    payables-only figure), IOU balances and the asset register with no
    document tying them together at exit.

    This model *is* that document: one row per offboarding checklist. It is
    computed by ``exit_settlement_service.build_settlement`` (never hand-
    entered beyond the discretionary add-back/deduction fields) and posted
    through the ``exit.settlement`` approval action, which writes the double-
    entry journal and links it via ``journal``. ``status`` mirrors the
    approval lifecycle: DRAFT until an approval posts it, POSTED afterwards.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="exit_settlements",
    )
    checklist = models.OneToOneField(
        "payroll.OffboardingChecklist",
        on_delete=models.CASCADE,
        related_name="exit_settlement",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.PROTECT,
        related_name="exit_settlements",
    )
    last_working_day = models.DateField()

    # --- Payables: what the company owes the leaver. ---
    final_month_salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="One month's basic salary paid out at exit.",
    )
    leave_encashment = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Encashment of unused encashable leave, per LeaveType rates.",
    )
    other_payables = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Discretionary add-backs (bonus, commission) reviewed by HR.",
    )

    # --- Receivables: what the leaver owes the company. ---
    outstanding_iou = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Unrepaid IOU/EWA principal plus interest at exit.",
    )
    unreturned_assets_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Recovery value of company assets still in use or lost.",
    )
    other_receivables = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Discretionary deductions (damages, advances) reviewed by HR.",
    )

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    journal = models.ForeignKey(
        "accounting.Journal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exit_settlements",
        help_text="The double-entry journal written when this statement posted.",
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posted_exit_settlements",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def payables_total(self) -> Decimal:
        return (
            self.final_month_salary
            + self.leave_encashment
            + self.other_payables
        )

    @property
    def receivables_total(self) -> Decimal:
        return (
            self.outstanding_iou
            + self.unreturned_assets_value
            + self.other_receivables
        )

    @property
    def net_settlement(self) -> Decimal:
        """Positive: the company pays the leaver. Negative: the leaver repays."""
        return self.payables_total - self.receivables_total

    @property
    def is_payable(self) -> bool:
        return self.net_settlement > 0

    def clean(self):
        super().clean()
        for name in (
            "final_month_salary",
            "leave_encashment",
            "other_payables",
            "outstanding_iou",
            "unreturned_assets_value",
            "other_receivables",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValidationError({name: "Settlement amounts cannot be negative."})

    def save(self, *args, **kwargs):
        from payroll.services.hr_workflow import guard_state

        guard_state(
            self,
            "exit.settlement",
            {"POSTED"},
            ("posted_by_id", "posted_at"),
            update_fields=kwargs.get("update_fields"),
        )
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Exit settlement: {self.employee} ({self.get_status_display()})"
