from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from company.models import Company, CompanyMembership
from standup.models import (
    StandupAnswer,
    StandupCheckin,
    StandupQuestion,
    StandupTeam,
    StandupTeamMember,
)


User = get_user_model()


class StandupAPITests(APITestCase):
    @staticmethod
    def grant_model_perms(user, model, codenames):
        content_type = ContentType.objects.get_for_model(model)
        perms = Permission.objects.filter(
            content_type=content_type, codename__in=codenames
        )
        user.user_permissions.add(*perms)

    def setUp(self):
        self.company_a = Company.objects.create(name="Standup Co A")
        self.company_b = Company.objects.create(name="Standup Co B")

        self.user_a = User.objects.create_user(
            email="standup-a@test.com",
            password="password123",
            first_name="Standup",
            last_name="A",
            company=self.company_a,
            active_company=self.company_a,
        )
        self.user_b = User.objects.create_user(
            email="standup-b@test.com",
            password="password123",
            first_name="Standup",
            last_name="B",
            company=self.company_b,
            active_company=self.company_b,
        )

        CompanyMembership.objects.get_or_create(
            user=self.user_a,
            company=self.company_a,
            defaults={"role": CompanyMembership.ROLE_OWNER, "is_default": True},
        )
        CompanyMembership.objects.get_or_create(
            user=self.user_b,
            company=self.company_b,
            defaults={"role": CompanyMembership.ROLE_OWNER, "is_default": True},
        )

        for model in (StandupTeam, StandupQuestion, StandupCheckin, StandupTeamMember):
            self.grant_model_perms(
                self.user_a,
                model,
                [
                    f"view_{model._meta.model_name}",
                    f"add_{model._meta.model_name}",
                    f"change_{model._meta.model_name}",
                    f"delete_{model._meta.model_name}",
                ],
            )

        self.employee_a = self.user_a.employee_user
        self.employee_a.company = self.company_a
        self.employee_a.first_name = "A"
        self.employee_a.last_name = "Employee"
        self.employee_a.save()

        self.employee_b = self.user_b.employee_user
        self.employee_b.company = self.company_b
        self.employee_b.first_name = "B"
        self.employee_b.last_name = "Employee"
        self.employee_b.save()

        self.team_a = StandupTeam.objects.create(
            company=self.company_a,
            name="Engineering Daily",
            slug="engineering-daily",
        )
        self.team_b = StandupTeam.objects.create(
            company=self.company_b,
            name="Ops Daily",
            slug="ops-daily",
        )

        self.question_a1 = StandupQuestion.objects.create(
            team=self.team_a,
            prompt="What did you do yesterday?",
            order=1,
        )
        self.question_a2 = StandupQuestion.objects.create(
            team=self.team_a,
            prompt="What will you do today?",
            order=2,
        )
        self.question_b1 = StandupQuestion.objects.create(
            team=self.team_b,
            prompt="Cross tenant question",
            order=1,
        )
        self.user_a2 = User.objects.create_user(
            email="standup-a2@test.com",
            password="password123",
            first_name="Standup",
            last_name="A2",
            company=self.company_a,
            active_company=self.company_a,
        )
        CompanyMembership.objects.get_or_create(
            user=self.user_a2,
            company=self.company_a,
            defaults={"role": CompanyMembership.ROLE_MEMBER, "is_default": False},
        )
        self.employee_a2 = self.user_a2.employee_user
        self.employee_a2.company = self.company_a
        self.employee_a2.first_name = "A2"
        self.employee_a2.last_name = "Employee"
        self.employee_a2.save()

        StandupTeamMember.objects.create(team=self.team_a, employee=self.employee_a)
        StandupTeamMember.objects.create(team=self.team_a, employee=self.employee_a2)
        StandupTeamMember.objects.create(team=self.team_b, employee=self.employee_b)

    def test_create_team_attaches_active_company(self):
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:standup-team-list")
        response = self.client.post(
            url,
            {
                "name": "Platform Daily",
                "slug": "platform-daily",
                "description": "Platform team standup",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["company"], self.company_a.id)

    def test_checkin_list_is_tenant_scoped(self):
        StandupCheckin.objects.create(
            company=self.company_a,
            team=self.team_a,
            member=self.employee_a,
            work_date="2026-02-26",
            status=StandupCheckin.STATUS_SUBMITTED,
        )
        StandupCheckin.objects.create(
            company=self.company_b,
            team=self.team_b,
            member=self.employee_b,
            work_date="2026-02-26",
            status=StandupCheckin.STATUS_SUBMITTED,
        )

        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:standup-checkin-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["team"], self.team_a.id)

    def test_submit_checkin_creates_answers_and_blocker_count(self):
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:standup-checkin-submit")
        response = self.client.post(
            url,
            {
                "team": self.team_a.id,
                "work_date": "2026-02-27",
                "answers": [
                    {
                        "question": self.question_a1.id,
                        "body": "Finished payroll API cleanup.",
                        "is_blocker": False,
                    },
                    {
                        "question": self.question_a2.id,
                        "body": "Implement standup models and migrations.",
                        "is_blocker": True,
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], StandupCheckin.STATUS_SUBMITTED)
        self.assertEqual(response.data["blocker_count"], 1)
        self.assertEqual(len(response.data["answers"]), 2)

    def test_submit_rejects_cross_tenant_question(self):
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:standup-checkin-submit")
        response = self.client.post(
            url,
            {
                "team": self.team_a.id,
                "work_date": "2026-02-27",
                "answers": [
                    {
                        "question": self.question_b1.id,
                        "body": "This should fail.",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_is_idempotent_per_member_day_team(self):
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:standup-checkin-submit")

        payload = {
            "team": self.team_a.id,
            "work_date": "2026-02-27",
            "answers": [
                {
                    "question": self.question_a1.id,
                    "body": "First version.",
                    "is_blocker": False,
                },
                {
                    "question": self.question_a2.id,
                    "body": "Second version.",
                    "is_blocker": False,
                },
            ],
        }

        first = self.client.post(url, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        payload["answers"][0]["body"] = "Updated content."
        second = self.client.post(url, payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_200_OK)

        checkins = StandupCheckin.objects.filter(
            team=self.team_a, member=self.employee_a, work_date="2026-02-27"
        )
        self.assertEqual(checkins.count(), 1)
        self.assertEqual(checkins.first().answers.count(), 2)

    def test_team_daily_summary_returns_aggregate_and_blockers(self):
        checkin = StandupCheckin.objects.create(
            company=self.company_a,
            team=self.team_a,
            member=self.employee_a,
            work_date="2026-02-27",
            status=StandupCheckin.STATUS_SUBMITTED,
            blocker_count=1,
        )
        StandupCheckin.objects.create(
            company=self.company_a,
            team=self.team_a,
            member=self.employee_a2,
            work_date="2026-02-27",
            status=StandupCheckin.STATUS_MISSED,
        )
        StandupAnswer.objects.create(
            checkin=checkin,
            question=self.question_a2,
            body="Blocked on staging credentials.",
            is_blocker=True,
        )

        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:standup-team-daily-summary", args=[self.team_a.id])
        response = self.client.get(url, {"work_date": "2026-02-27"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["members"], 2)
        self.assertEqual(response.data["summary"]["submitted"], 1)
        self.assertEqual(response.data["summary"]["missed"], 1)
        self.assertEqual(response.data["summary"]["pending"], 0)
        self.assertEqual(response.data["summary"]["blockers"], 1)
        self.assertEqual(len(response.data["blockers"]), 1)
        self.assertEqual(response.data["blockers"][0]["body"], "Blocked on staging credentials.")

    def test_team_daily_summary_is_tenant_scoped(self):
        self.client.force_authenticate(self.user_a)
        url = reverse("api:v1:standup-team-daily-summary", args=[self.team_b.id])
        response = self.client.get(url, {"work_date": "2026-02-27"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
