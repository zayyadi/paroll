from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from company.models import Company
from payroll.models import (
    HiringCandidate,
    HiringStage,
    HiringStageScorecard,
    JobOffer,
    JobRequisition,
    Position,
)
from payroll.services.hiring import (
    accept_job_offer,
    create_job_offer,
    create_standard_hiring_stages,
)


User = get_user_model()


class HiringPipelineFeatureTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Hiring Co")
        self.user = User.objects.create_user(
            email="hiring@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.user.employee_user.company = self.company
        self.user.employee_user.save(update_fields=["company"])
        self.position = Position.objects.create(company=self.company, title="Engineer")
        self.requisition = JobRequisition.objects.create(
            company=self.company,
            position=self.position,
            title="Engineer",
        )
        self.stages = create_standard_hiring_stages(self.company)

    def _grant(self, codename):
        permission = Permission.objects.get(
            content_type__app_label="payroll",
            codename=codename,
        )
        self.user.user_permissions.add(permission)

    def _candidate(self, email="hire@example.com"):
        return HiringCandidate.objects.create(
            company=self.company,
            requisition=self.requisition,
            current_stage=self.stages[0],
            first_name="Hire",
            last_name="Me",
            email=email,
            consent_to_process=True,
        )

    def test_requisition_to_offer_acceptance(self):
        candidate = self._candidate()
        offer = create_job_offer(
            candidate=candidate,
            title="Engineer",
            employment_type=Position.EmploymentType.FULL_TIME,
            salary_amount=Decimal("250000.00"),
            currency="NGN",
            start_date=date(2026, 7, 1),
            created_by=self.user,
        )
        execution = accept_job_offer(offer, accepted_by=self.user)
        candidate.refresh_from_db()

        self.assertEqual(candidate.status, HiringCandidate.Status.HIRED)
        self.assertEqual(candidate.current_stage.stage_type, HiringStage.StageType.HIRED)
        self.assertEqual(execution.context["candidate_id"], candidate.pk)

    def test_hiring_workspace_and_post_actions(self):
        self._grant("view_employeeprofile")
        self.client.force_login(self.user)

        workspace = self.client.get(reverse("payroll:hiring_workspace"))
        create_candidate = self.client.post(
            reverse("payroll:hiring_candidate_create"),
            {
                "requisition": self.requisition.pk,
                "first_name": "Pipeline",
                "last_name": "Candidate",
                "email": "pipeline@example.com",
                "phone": "08000000000",
                "source": "Referral",
                "consent_to_process": "on",
            },
        )
        candidate = HiringCandidate.objects.get(email="pipeline@example.com")
        screen_stage = self.stages[1]
        scorecard = self.client.post(
            reverse("payroll:hiring_scorecard_create", args=[candidate.pk]),
            {
                "stage": screen_stage.pk,
                "recommendation": HiringStageScorecard.Recommendation.YES,
                "competency_scores": '{"role_fit": 5, "values": 4}',
                "notes": "Strong structured interview.",
            },
        )
        advance = self.client.post(
            reverse("payroll:hiring_candidate_advance", args=[candidate.pk]),
            {"next_stage": screen_stage.pk},
        )
        offer_create = self.client.post(
            reverse("payroll:hiring_offer_create", args=[candidate.pk]),
            {
                "title": "Engineer",
                "employment_type": Position.EmploymentType.FULL_TIME,
                "salary_amount": "250000.00",
                "currency": "NGN",
                "start_date": "2026-07-01",
                "expires_at": "2026-06-15",
                "terms": '{"probation_months": 6}',
            },
        )
        offer = JobOffer.objects.get(candidate=candidate)
        offer_accept = self.client.post(
            reverse("payroll:hiring_offer_accept", args=[offer.pk])
        )

        self.assertEqual(workspace.status_code, 200)
        self.assertEqual(create_candidate.status_code, 302)
        self.assertEqual(scorecard.status_code, 302)
        self.assertEqual(advance.status_code, 302)
        self.assertEqual(offer_create.status_code, 302)
        self.assertEqual(offer_accept.status_code, 302)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, HiringCandidate.Status.HIRED)
