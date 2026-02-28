from __future__ import annotations

import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from celery import shared_task
from django.utils import timezone

from payroll.services.notification_service import NotificationService
from standup.models import (
    StandupCheckin,
    StandupDispatchLog,
    StandupFollow,
    StandupTeam,
    StandupTeamMember,
)


logger = logging.getLogger(__name__)


def _team_local_now(team: StandupTeam):
    return timezone.now().astimezone(ZoneInfo(team.timezone_name))


def _is_team_active_today(team: StandupTeam, local_now) -> bool:
    if team.cadence == StandupTeam.CADENCE_DAILY:
        return True
    if team.cadence == StandupTeam.CADENCE_WEEKDAYS:
        return local_now.weekday() < 5
    return local_now.weekday() < 5


def _team_members(team: StandupTeam):
    return (
        StandupTeamMember.objects.select_related("employee", "employee__user")
        .filter(team=team, is_active=True)
    )


@shared_task(name="standup.send_reminders")
def send_standup_reminders_task():
    sent = 0
    teams = StandupTeam.objects.filter(is_active=True).exclude(reminder_time__isnull=True)
    notification_service = NotificationService()

    for team in teams.iterator():
        local_now = _team_local_now(team)
        if not _is_team_active_today(team, local_now):
            continue
        if (local_now.hour, local_now.minute) != (
            team.reminder_time.hour,
            team.reminder_time.minute,
        ):
            continue

        work_date = local_now.date()
        _, created = StandupDispatchLog.objects.get_or_create(
            team=team,
            work_date=work_date,
            event_type=StandupDispatchLog.EVENT_REMINDER,
        )
        if not created:
            continue

        for membership in _team_members(team):
            checkin, _ = StandupCheckin.objects.get_or_create(
                company=team.company,
                team=team,
                member=membership.employee,
                work_date=work_date,
                defaults={"created_by": membership.employee.user},
            )
            if checkin.status == StandupCheckin.STATUS_SUBMITTED:
                continue

            notification_service.send_notification(
                recipient=membership.employee,
                notification_type="INFO",
                title=f"Standup reminder: {team.name}",
                message=f"Please submit your standup for {work_date.isoformat()}.",
                priority="MEDIUM",
                metadata={
                    "category": "standup_reminder",
                    "team_id": team.id,
                    "work_date": work_date.isoformat(),
                },
            )
            sent += 1

    return {"sent": sent}


@shared_task(name="standup.mark_missed")
def mark_missed_standups_task():
    marked = 0
    teams = StandupTeam.objects.filter(is_active=True).exclude(deadline_time__isnull=True)
    notification_service = NotificationService()

    for team in teams.iterator():
        local_now = _team_local_now(team)
        if not _is_team_active_today(team, local_now):
            continue
        if (local_now.hour, local_now.minute) != (
            team.deadline_time.hour,
            team.deadline_time.minute,
        ):
            continue

        work_date = local_now.date()
        _, created = StandupDispatchLog.objects.get_or_create(
            team=team,
            work_date=work_date,
            event_type=StandupDispatchLog.EVENT_MISSED,
        )
        if not created:
            continue

        for membership in _team_members(team):
            checkin, _ = StandupCheckin.objects.get_or_create(
                company=team.company,
                team=team,
                member=membership.employee,
                work_date=work_date,
                defaults={"created_by": membership.employee.user},
            )
            if checkin.status == StandupCheckin.STATUS_SUBMITTED:
                continue

            checkin.status = StandupCheckin.STATUS_MISSED
            checkin.save(update_fields=["status", "updated_at"])
            marked += 1

            notification_service.send_notification(
                recipient=membership.employee,
                notification_type="WARNING",
                title=f"Standup missed: {team.name}",
                message=f"Standup submission deadline passed for {work_date.isoformat()}.",
                priority="HIGH",
                metadata={
                    "category": "standup_missed",
                    "team_id": team.id,
                    "work_date": work_date.isoformat(),
                },
            )

    return {"marked_missed": marked}


@shared_task(name="standup.send_daily_digest")
def send_standup_daily_digest_task():
    sent = 0
    teams = StandupTeam.objects.filter(is_active=True).exclude(deadline_time__isnull=True)
    notification_service = NotificationService()

    for team in teams.iterator():
        local_now = _team_local_now(team)
        if not _is_team_active_today(team, local_now):
            continue
        if local_now < local_now.replace(
            hour=team.deadline_time.hour,
            minute=team.deadline_time.minute,
            second=0,
            microsecond=0,
        ) + timedelta(minutes=5):
            continue

        work_date = local_now.date()
        _, created = StandupDispatchLog.objects.get_or_create(
            team=team,
            work_date=work_date,
            event_type=StandupDispatchLog.EVENT_DAILY_DIGEST,
        )
        if not created:
            continue

        checkins = StandupCheckin.objects.filter(team=team, work_date=work_date)
        submitted_count = checkins.filter(status=StandupCheckin.STATUS_SUBMITTED).count()
        missed_count = checkins.filter(status=StandupCheckin.STATUS_MISSED).count()
        pending_count = checkins.filter(status=StandupCheckin.STATUS_DRAFT).count()
        blocker_total = checkins.filter(status=StandupCheckin.STATUS_SUBMITTED).values_list(
            "blocker_count", flat=True
        )
        blocker_count = sum(blocker_total)

        team_memberships = list(_team_members(team))
        member_map = {membership.employee_id: membership.employee for membership in team_memberships}

        lead_employee_ids = set(
            membership.employee_id
            for membership in team_memberships
            if membership.role == StandupTeamMember.ROLE_LEAD
        )
        follow_employee_ids = set(
            StandupFollow.objects.filter(team=team, follower__employee_user__isnull=False).values_list(
                "follower__employee_user__id", flat=True
            )
        )
        recipient_ids = lead_employee_ids | follow_employee_ids

        for employee_id in recipient_ids:
            employee = member_map.get(employee_id)
            if employee is None:
                from payroll.models import EmployeeProfile

                employee = EmployeeProfile.objects.filter(id=employee_id).first()
            if employee is None:
                continue

            notification_service.send_notification(
                recipient=employee,
                notification_type="INFO",
                title=f"Daily standup digest: {team.name}",
                message=(
                    f"{work_date.isoformat()} summary: submitted {submitted_count}, "
                    f"missed {missed_count}, pending {pending_count}, blockers {blocker_count}."
                ),
                priority="LOW",
                metadata={
                    "category": "standup_digest",
                    "team_id": team.id,
                    "work_date": work_date.isoformat(),
                    "submitted_count": submitted_count,
                    "missed_count": missed_count,
                    "pending_count": pending_count,
                    "blocker_count": blocker_count,
                },
            )
            sent += 1

        StandupDispatchLog.objects.filter(
            team=team,
            work_date=work_date,
            event_type=StandupDispatchLog.EVENT_DAILY_DIGEST,
        ).update(
            metadata={
                "submitted_count": submitted_count,
                "missed_count": missed_count,
                "pending_count": pending_count,
                "blocker_count": blocker_count,
                "recipient_count": len(recipient_ids),
            }
        )

    return {"sent": sent}
