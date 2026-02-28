from django.contrib import admin

from standup.models import (
    StandupAnswer,
    StandupCheckin,
    StandupDispatchLog,
    StandupFollow,
    StandupQuestion,
    StandupTeam,
    StandupTeamMember,
)


@admin.register(StandupTeam)
class StandupTeamAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "cadence", "is_active", "updated_at")
    list_filter = ("company", "cadence", "is_active")
    search_fields = ("name", "slug", "company__name")


@admin.register(StandupTeamMember)
class StandupTeamMemberAdmin(admin.ModelAdmin):
    list_display = ("team", "employee", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active", "team__company")
    search_fields = ("team__name", "employee__first_name", "employee__last_name")


@admin.register(StandupQuestion)
class StandupQuestionAdmin(admin.ModelAdmin):
    list_display = ("team", "order", "prompt", "is_required", "is_active")
    list_filter = ("is_required", "is_active", "team__company")
    search_fields = ("team__name", "prompt")


@admin.register(StandupCheckin)
class StandupCheckinAdmin(admin.ModelAdmin):
    list_display = ("work_date", "team", "member", "status", "blocker_count", "submitted_at")
    list_filter = ("status", "team__company", "team")
    search_fields = ("team__name", "member__first_name", "member__last_name")


@admin.register(StandupAnswer)
class StandupAnswerAdmin(admin.ModelAdmin):
    list_display = ("checkin", "question", "is_blocker", "updated_at")
    list_filter = ("is_blocker", "checkin__company")
    search_fields = ("checkin__team__name", "body")


@admin.register(StandupFollow)
class StandupFollowAdmin(admin.ModelAdmin):
    list_display = ("team", "follower", "created_at")
    list_filter = ("team__company",)
    search_fields = ("team__name", "follower__email")


@admin.register(StandupDispatchLog)
class StandupDispatchLogAdmin(admin.ModelAdmin):
    list_display = ("team", "event_type", "work_date", "created_at")
    list_filter = ("event_type", "team__company")
    search_fields = ("team__name",)

# Register your models here.
