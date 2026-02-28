from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class StandupTeam(models.Model):
    CADENCE_DAILY = "DAILY"
    CADENCE_WEEKDAYS = "WEEKDAYS"
    CADENCE_CUSTOM = "CUSTOM"
    CADENCE_CHOICES = (
        (CADENCE_DAILY, "Daily"),
        (CADENCE_WEEKDAYS, "Weekdays"),
        (CADENCE_CUSTOM, "Custom"),
    )

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="standup_teams",
        db_index=True,
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    description = models.TextField(blank=True)
    cadence = models.CharField(
        max_length=20,
        choices=CADENCE_CHOICES,
        default=CADENCE_WEEKDAYS,
    )
    timezone_name = models.CharField(max_length=64, default="Africa/Lagos")
    reminder_time = models.TimeField(null=True, blank=True)
    deadline_time = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "slug"], name="uniq_standup_team_slug_per_company"
            ),
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_standup_team_name_per_company"
            ),
        ]
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["company", "name"]),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.name}"


class StandupTeamMember(models.Model):
    ROLE_MEMBER = "MEMBER"
    ROLE_LEAD = "LEAD"
    ROLE_CHOICES = (
        (ROLE_MEMBER, "Member"),
        (ROLE_LEAD, "Lead"),
    )

    team = models.ForeignKey(
        "standup.StandupTeam",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="standup_memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["team__name", "employee__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "employee"], name="uniq_standup_team_member"
            )
        ]
        indexes = [
            models.Index(fields=["team", "is_active"]),
            models.Index(fields=["employee", "is_active"]),
        ]

    def __str__(self):
        return f"{self.team.name} - {self.employee}"

    def clean(self):
        if self.team_id and self.employee_id and self.team.company_id != self.employee.company_id:
            raise ValidationError("Team and employee must belong to the same company.")


class StandupQuestion(models.Model):
    ANSWER_TEXT = "TEXT"
    ANSWER_LONG_TEXT = "LONG_TEXT"
    ANSWER_CHOICES = (
        (ANSWER_TEXT, "Short Text"),
        (ANSWER_LONG_TEXT, "Long Text"),
    )

    team = models.ForeignKey(
        "standup.StandupTeam",
        on_delete=models.CASCADE,
        related_name="questions",
    )
    prompt = models.CharField(max_length=255)
    help_text = models.CharField(max_length=255, blank=True)
    answer_type = models.CharField(max_length=20, choices=ANSWER_CHOICES, default=ANSWER_LONG_TEXT)
    order = models.PositiveSmallIntegerField(default=1)
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["team", "order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "order"], name="uniq_standup_question_order_per_team"
            )
        ]
        indexes = [
            models.Index(fields=["team", "is_active"]),
        ]

    def __str__(self):
        return f"{self.team.name} Q{self.order}"


class StandupCheckin(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_MISSED = "MISSED"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_MISSED, "Missed"),
    )

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="standup_checkins",
        db_index=True,
    )
    team = models.ForeignKey(
        "standup.StandupTeam",
        on_delete=models.CASCADE,
        related_name="checkins",
    )
    member = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="standup_checkins",
    )
    work_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    blocker_count = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_standup_checkins",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_date", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "member", "work_date"],
                name="uniq_standup_checkin_member_per_day",
            )
        ]
        indexes = [
            models.Index(fields=["company", "work_date"]),
            models.Index(fields=["team", "work_date"]),
            models.Index(fields=["member", "work_date"]),
            models.Index(fields=["company", "status", "-work_date"]),
        ]

    def __str__(self):
        return f"{self.member} - {self.work_date}"

    def mark_submitted(self):
        self.status = self.STATUS_SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=["status", "submitted_at", "updated_at"])

    def clean(self):
        if self.team_id and self.company_id and self.team.company_id != self.company_id:
            raise ValidationError("Team and company mismatch.")
        if self.member_id and self.company_id and self.member.company_id != self.company_id:
            raise ValidationError("Member and company mismatch.")


class StandupAnswer(models.Model):
    checkin = models.ForeignKey(
        "standup.StandupCheckin",
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        "standup.StandupQuestion",
        on_delete=models.PROTECT,
        related_name="answers",
    )
    body = models.TextField()
    is_blocker = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["question__order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["checkin", "question"], name="uniq_standup_answer_per_question"
            )
        ]
        indexes = [
            models.Index(fields=["checkin", "is_blocker"]),
        ]

    def __str__(self):
        return f"Answer {self.id} for {self.checkin_id}"

    def clean(self):
        if self.checkin_id and self.question_id and self.checkin.team_id != self.question.team_id:
            raise ValidationError("Question must belong to the checkin team.")


class StandupDispatchLog(models.Model):
    EVENT_REMINDER = "REMINDER"
    EVENT_MISSED = "MISSED"
    EVENT_DAILY_DIGEST = "DAILY_DIGEST"
    EVENT_CHOICES = (
        (EVENT_REMINDER, "Reminder"),
        (EVENT_MISSED, "Mark Missed"),
        (EVENT_DAILY_DIGEST, "Daily Digest"),
    )

    team = models.ForeignKey(
        "standup.StandupTeam",
        on_delete=models.CASCADE,
        related_name="dispatch_logs",
    )
    work_date = models.DateField()
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "work_date", "event_type"],
                name="uniq_standup_dispatch_per_event_date",
            )
        ]
        indexes = [
            models.Index(fields=["team", "work_date", "event_type"]),
        ]

    def __str__(self):
        return f"{self.team.name} {self.event_type} {self.work_date}"


class StandupFollow(models.Model):
    team = models.ForeignKey(
        "standup.StandupTeam",
        on_delete=models.CASCADE,
        related_name="followers",
    )
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="standup_follows",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "follower"], name="uniq_standup_follower_per_team"
            )
        ]
        indexes = [models.Index(fields=["team", "follower"])]

    def __str__(self):
        return f"{self.follower} follows {self.team}"
