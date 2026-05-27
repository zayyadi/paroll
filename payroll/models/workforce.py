from django.conf import settings
from django.db import models
from decimal import Decimal, ROUND_HALF_UP
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
    structured_notes = models.JSONField(default=dict, blank=True)
    applied_at = models.DateTimeField(default=timezone.now)
    hired_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-applied_at", "last_name", "first_name"]
        unique_together = ("requisition", "email")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SENT)
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

    class Meta:
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


STANDARD_HIRING_STAGE_BLUEPRINT = [
    (HiringStage.StageType.SOURCED, "Sourced", False, False),
    (HiringStage.StageType.SCREENING, "Screening", False, False),
    (HiringStage.StageType.STRUCTURED_INTERVIEW, "Structured Interview", True, False),
    (HiringStage.StageType.SCORECARD_REVIEW, "Scorecard Review", True, True),
    (HiringStage.StageType.REFERENCE_CHECK, "Reference Check", False, False),
    (HiringStage.StageType.OFFER, "Offer", False, True),
    (HiringStage.StageType.HIRED, "Hired", False, False),
]


def create_standard_hiring_stages(company):
    stages = []
    for sequence, (stage_type, name, requires_scorecard, requires_approval) in enumerate(
        STANDARD_HIRING_STAGE_BLUEPRINT, start=1
    ):
        stage, _created = HiringStage.objects.update_or_create(
            company=company,
            stage_type=stage_type,
            defaults={
                "name": name,
                "sequence": sequence,
                "requires_scorecard": requires_scorecard,
                "requires_approval": requires_approval,
                "is_active": True,
            },
        )
        stages.append(stage)
    return stages


def record_candidate_scorecard(*, candidate, stage, interviewer, competency_scores, recommendation, notes=""):
    if candidate.company_id != stage.company_id:
        raise ValueError("Candidate and hiring stage must belong to the same company")
    numeric_scores = [Decimal(str(score)) for score in competency_scores.values()]
    average_score = Decimal("0.00")
    if numeric_scores:
        average_score = (sum(numeric_scores) / len(numeric_scores)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return HiringStageScorecard.objects.create(
        company=candidate.company,
        candidate=candidate,
        stage=stage,
        interviewer=interviewer,
        competency_scores=competency_scores,
        average_score=average_score,
        recommendation=recommendation,
        notes=notes,
    )


def advance_candidate(candidate, next_stage, advanced_by=None):
    if candidate.company_id != next_stage.company_id:
        raise ValueError("Candidate and hiring stage must belong to the same company")
    if next_stage.requires_scorecard and not candidate.scorecards.filter(stage=next_stage).exists():
        raise ValueError("A structured scorecard is required before advancing to this stage")
    candidate.current_stage = next_stage
    candidate.status = (
        HiringCandidate.Status.HIRED
        if next_stage.stage_type == HiringStage.StageType.HIRED
        else HiringCandidate.Status.IN_PROCESS
    )
    if candidate.status == HiringCandidate.Status.HIRED:
        candidate.hired_at = timezone.now()
    candidate.save(update_fields=["current_stage", "status", "hired_at", "updated_at"])
    return candidate


def create_job_offer(*, candidate, title, employment_type, salary_amount, currency, start_date, created_by=None, terms=None):
    offer = JobOffer.objects.create(
        company=candidate.company,
        candidate=candidate,
        title=title,
        employment_type=employment_type,
        salary_amount=salary_amount,
        currency=currency,
        start_date=start_date,
        created_by=created_by,
        terms=terms or {},
    )
    candidate.status = HiringCandidate.Status.OFFER
    candidate.save(update_fields=["status", "updated_at"])
    return offer


def accept_job_offer(offer, accepted_by=None):
    offer.status = JobOffer.Status.ACCEPTED
    offer.accepted_at = timezone.now()
    offer.save(update_fields=["status", "accepted_at", "updated_at"])

    stages = create_standard_hiring_stages(offer.company)
    hired_stage = next(stage for stage in stages if stage.stage_type == HiringStage.StageType.HIRED)
    candidate = offer.candidate
    candidate.current_stage = hired_stage
    candidate.status = HiringCandidate.Status.HIRED
    candidate.hired_at = timezone.now()
    candidate.save(update_fields=["current_stage", "status", "hired_at", "updated_at"])

    requisition = candidate.requisition
    hired_count = requisition.candidates.filter(status=HiringCandidate.Status.HIRED).count()
    if hired_count >= requisition.headcount:
        requisition.status = JobRequisition.Status.FILLED
        requisition.closed_at = timezone.now()
        requisition.position.status = Position.Status.FILLED
        requisition.position.save(update_fields=["status", "updated_at"])
        requisition.save(update_fields=["status", "closed_at", "updated_at"])

    template = (
        WorkflowTemplate.objects.filter(
            company=offer.company,
            workflow_type=WorkflowTemplate.WorkflowType.ONBOARDING,
            trigger_event="candidate.hired",
            is_active=True,
        )
        .order_by("name")
        .first()
    )
    if template is None:
        template = WorkflowTemplate.objects.create(
            company=offer.company,
            name="Candidate Onboarding",
            workflow_type=WorkflowTemplate.WorkflowType.ONBOARDING,
            trigger_event="candidate.hired",
        )
    return WorkflowExecution.objects.create(
        company=offer.company,
        template=template,
        started_by=accepted_by,
        status=WorkflowExecution.Status.PENDING,
        context={
            "trigger_event": "candidate.hired",
            "candidate_id": candidate.pk,
            "candidate_email": candidate.email,
            "candidate_name": str(candidate),
            "requisition_id": requisition.pk,
            "position_title": requisition.title,
            "start_date": offer.start_date.isoformat(),
        },
    )


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
