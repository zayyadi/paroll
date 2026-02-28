from datetime import timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from company.models import Company
from payroll.models import Notification
from standup.models import (
    StandupCheckin,
    StandupDispatchLog,
    StandupFollow,
    StandupQuestion,
    StandupTeam,
    StandupTeamMember,
)
from standup.tasks import (
    mark_missed_standups_task,
    send_standup_daily_digest_task,
    send_standup_reminders_task,
)


User = get_user_model()


class StandupTaskTests(TestCase):
    def setUp(self):
        now_utc = timezone.now().astimezone(dt_timezone.utc)
        self.current_time = now_utc.replace(second=0, microsecond=0).time()

        self.company = Company.objects.create(name="Standup Tasks Co")

        self.member_user = User.objects.create_user(
            email="member@standup.test",
            password="password123",
            first_name="Member",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        self.lead_user = User.objects.create_user(
            email="lead@standup.test",
            password="password123",
            first_name="Lead",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        self.follower_user = User.objects.create_user(
            email="follower@standup.test",
            password="password123",
            first_name="Follower",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )

        self.member_employee = self.member_user.employee_user
        self.member_employee.company = self.company
        self.member_employee.save()

        self.lead_employee = self.lead_user.employee_user
        self.lead_employee.company = self.company
        self.lead_employee.save()

        self.follower_employee = self.follower_user.employee_user
        self.follower_employee.company = self.company
        self.follower_employee.save()

        self.team = StandupTeam.objects.create(
            company=self.company,
            name="Backend Daily",
            slug="backend-daily",
            timezone_name="UTC",
            reminder_time=self.current_time,
            deadline_time=self.current_time,
        )
        StandupQuestion.objects.create(team=self.team, prompt="Yesterday", order=1)
        StandupQuestion.objects.create(team=self.team, prompt="Today", order=2)

        StandupTeamMember.objects.create(
            team=self.team, employee=self.member_employee, role=StandupTeamMember.ROLE_MEMBER
        )
        StandupTeamMember.objects.create(
            team=self.team, employee=self.lead_employee, role=StandupTeamMember.ROLE_LEAD
        )
        StandupFollow.objects.create(team=self.team, follower=self.follower_user)

    @patch("payroll.services.notification_service.NotificationService._queue_notification", return_value=True)
    def test_send_reminders_creates_draft_checkins_and_notifications(self, _mock_queue):
        result = send_standup_reminders_task()
        self.assertEqual(result["sent"], 2)

        work_date = timezone.now().astimezone(dt_timezone.utc).date()
        self.assertEqual(
            StandupCheckin.objects.filter(team=self.team, work_date=work_date).count(), 2
        )
        self.assertEqual(
            Notification.objects.filter(
                metadata__category="standup_reminder",
                recipient__in=[self.member_employee, self.lead_employee],
            ).count(),
            2,
        )

    @patch("payroll.services.notification_service.NotificationService._queue_notification", return_value=True)
    def test_mark_missed_updates_unsubmitted_checkins(self, _mock_queue):
        work_date = timezone.now().astimezone(dt_timezone.utc).date()
        StandupCheckin.objects.create(
            company=self.company,
            team=self.team,
            member=self.member_employee,
            work_date=work_date,
            status=StandupCheckin.STATUS_DRAFT,
        )
        StandupCheckin.objects.create(
            company=self.company,
            team=self.team,
            member=self.lead_employee,
            work_date=work_date,
            status=StandupCheckin.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )

        result = mark_missed_standups_task()
        self.assertEqual(result["marked_missed"], 1)

        member_checkin = StandupCheckin.objects.get(
            team=self.team, member=self.member_employee, work_date=work_date
        )
        lead_checkin = StandupCheckin.objects.get(
            team=self.team, member=self.lead_employee, work_date=work_date
        )
        self.assertEqual(member_checkin.status, StandupCheckin.STATUS_MISSED)
        self.assertEqual(lead_checkin.status, StandupCheckin.STATUS_SUBMITTED)
        self.assertEqual(
            Notification.objects.filter(metadata__category="standup_missed").count(), 1
        )

    @patch("payroll.services.notification_service.NotificationService._queue_notification", return_value=True)
    def test_daily_digest_is_idempotent_per_team_day(self, _mock_queue):
        now_utc = timezone.now().astimezone(dt_timezone.utc).replace(second=0, microsecond=0)
        self.team.deadline_time = (now_utc - timedelta(minutes=10)).time()
        self.team.save(update_fields=["deadline_time"])

        work_date = timezone.now().astimezone(dt_timezone.utc).date()
        StandupCheckin.objects.create(
            company=self.company,
            team=self.team,
            member=self.member_employee,
            work_date=work_date,
            status=StandupCheckin.STATUS_SUBMITTED,
            blocker_count=1,
            submitted_at=timezone.now(),
        )
        StandupCheckin.objects.create(
            company=self.company,
            team=self.team,
            member=self.lead_employee,
            work_date=work_date,
            status=StandupCheckin.STATUS_MISSED,
        )

        first = send_standup_daily_digest_task()
        second = send_standup_daily_digest_task()

        self.assertEqual(first["sent"], 2)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(
            Notification.objects.filter(metadata__category="standup_digest").count(), 2
        )
        self.assertEqual(
            StandupDispatchLog.objects.filter(
                team=self.team,
                work_date=work_date,
                event_type=StandupDispatchLog.EVENT_DAILY_DIGEST,
            ).count(),
            1,
        )
