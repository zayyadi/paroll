from django.db import models
from django.utils import timezone


class CompanyChatRoom(models.Model):
    DEFAULT_SLUG = "general"
    TYPE_COMPANY = "company"
    TYPE_TEAM = "team"
    TYPE_DIRECT = "direct"
    TYPE_CHOICES = (
        (TYPE_COMPANY, "Company"),
        (TYPE_TEAM, "Team"),
        (TYPE_DIRECT, "Direct"),
    )

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="chat_rooms",
        db_index=True,
    )
    slug = models.SlugField(max_length=64)
    name = models.CharField(max_length=120, default="Company Chat")
    description = models.TextField(blank=True)
    room_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_COMPANY,
    )
    created_by = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_chat_rooms",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "slug"],
                name="uniq_company_chat_room_slug",
            )
        ]
        indexes = [
            models.Index(fields=["company", "is_active"]),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.name}"

    @classmethod
    def get_or_create_default(cls, company):
        return cls.objects.get_or_create(
            company=company,
            slug=cls.DEFAULT_SLUG,
            defaults={
                "name": "Company Chat",
                "description": "Shared room for company-wide conversations.",
                "room_type": cls.TYPE_COMPANY,
            },
        )


class CompanyChatMessage(models.Model):
    room = models.ForeignKey(
        "payroll.CompanyChatRoom",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["room", "created_at"]),
        ]

    def __str__(self):
        return f"{self.sender} @ {self.created_at:%Y-%m-%d %H:%M}"


class CompanyChatReadState(models.Model):
    room = models.ForeignKey(
        "payroll.CompanyChatRoom",
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="chat_read_states",
    )
    last_read_message = models.ForeignKey(
        "payroll.CompanyChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    last_read_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "employee"],
                name="uniq_company_chat_read_state",
            )
        ]
        indexes = [
            models.Index(fields=["room", "employee"]),
        ]

    def __str__(self):
        return f"{self.employee} read {self.room}"


class CompanyChatRoomMember(models.Model):
    ROLE_MEMBER = "member"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = (
        (ROLE_MEMBER, "Member"),
        (ROLE_ADMIN, "Admin"),
    )

    room = models.ForeignKey(
        "payroll.CompanyChatRoom",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    employee = models.ForeignKey(
        "payroll.EmployeeProfile",
        on_delete=models.CASCADE,
        related_name="chat_memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "employee"],
                name="uniq_company_chat_room_member",
            )
        ]
        indexes = [
            models.Index(fields=["room", "is_active"]),
            models.Index(fields=["employee", "is_active"]),
        ]

    def __str__(self):
        return f"{self.employee} in {self.room}"
