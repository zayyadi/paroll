from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounting.models import DisciplinaryCase
from company.models import Company
from payroll.models import (
    CandidateConsent,
    EmployeeProfile,
    HiringCandidate,
    HiringStage,
    HRRetentionPolicy,
    JobRequisition,
    LeavePolicy,
    LeaveBalance,
    LeaveCarryover,
    LeaveRequest,
    Position,
    SurveyQuestion,
    SurveyResponse,
    SurveyTemplate,
    get_leave_balance,
)
from payroll.tasks.retention_tasks import apply_hr_retention_task


User = get_user_model()


class Phase4HRFeatureTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Phase 4 Co")
        self.user = User.objects.create_user(
            email="phase4@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.save(update_fields=["company"])

    def _grant(self, codename):
        permission = Permission.objects.get(
            content_type__app_label="payroll",
            codename=codename,
        )
        self.user.user_permissions.add(permission)

    def _requisition(self):
        position = Position.objects.create(company=self.company, title="Analyst")
        return JobRequisition.objects.create(
            company=self.company,
            position=position,
            title="Analyst",
        )

    def test_get_leave_balance_creates_carryover_audit_record(self):
        LeaveBalance.objects.create(
            employee=self.employee,
            year=2025,
            annual_leave=5,
        )

        balance = get_leave_balance(self.employee, 2026)

        self.assertEqual(balance.carried_over_annual_leave, 5)
        carryover = LeaveCarryover.objects.get(employee=self.employee, from_year=2025)
        self.assertEqual(carryover.to_year, 2026)
        self.assertEqual(carryover.days, 5)

    def test_leave_calendar_view_lists_approved_leave(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            reason="Rest",
            status="APPROVED",
            hr_override=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("payroll:leave_calendar"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(leave, list(response.context["leave_requests"]))

    def test_leave_management_views_and_actions(self):
        self._grant("change_leaverequest")
        self._grant("view_leavepolicy")
        LeavePolicy.objects.create(
            company=self.company,
            leave_type="ANNUAL",
            max_days=20,
        )
        leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 6, 8),
            end_date=date(2026, 6, 10),
            reason="Family rest",
            status="PENDING",
        )
        self.client.force_login(self.user)

        list_response = self.client.get(reverse("payroll:leave_requests"))
        manage_response = self.client.get(reverse("payroll:manage_leave_requests"))
        policy_response = self.client.get(reverse("payroll:leave_policies"))
        detail_response = self.client.get(
            reverse("payroll:view_leave_request", args=[leave.pk])
        )
        edit_response = self.client.post(
            reverse("payroll:edit_leave_request", args=[leave.pk]),
            {
                "leave_type": "ANNUAL",
                "start_date": "2026-06-09",
                "end_date": "2026-06-10",
                "reason": "Family rest updated",
            },
        )
        approve_response = self.client.post(
            reverse("payroll:approve_leave", args=[leave.pk])
        )
        leave.refresh_from_db()

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(manage_response.status_code, 200)
        self.assertEqual(policy_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(approve_response.status_code, 302)
        self.assertEqual(leave.status, "APPROVED")

        second_leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="SICK",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            reason="Clinic",
            status="PENDING",
        )
        reject_response = self.client.post(
            reverse("payroll:reject_leave", args=[second_leave.pk])
        )
        second_leave.refresh_from_db()
        delete_response = self.client.get(
            reverse("payroll:delete_leave_request", args=[second_leave.pk])
        )

        self.assertEqual(reject_response.status_code, 302)
        self.assertEqual(second_leave.status, "REJECTED")
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(LeaveRequest.objects.filter(pk=second_leave.pk).exists())

    def test_candidate_consent_audit_and_reconsent_workflow(self):
        candidate = HiringCandidate.objects.create(
            company=self.company,
            requisition=self._requisition(),
            first_name="Consent",
            last_name="Person",
            email="consent@example.com",
            consent_to_process=True,
            consent_version="v1",
        )

        self.assertEqual(candidate.consent_records.count(), 1)
        consent = candidate.consent_records.get()
        self.assertTrue(consent.consent_given)
        self.assertEqual(consent.version, "v1")

        candidate.consent_expires_at = timezone.now() - timedelta(days=1)
        candidate.request_reconsent(version="v2")
        candidate.refresh_from_db()

        self.assertFalse(candidate.consent_to_process)
        self.assertEqual(candidate.consent_version, "v2")
        self.assertTrue(
            CandidateConsent.objects.filter(
                candidate=candidate,
                consent_given=False,
                version="v2",
            ).exists()
        )

    def test_retention_task_uses_policy_for_candidate_survey_and_discipline(self):
        policy = HRRetentionPolicy.objects.create(
            company=self.company,
            candidate_retention_days=365,
            survey_retention_days=730,
            disciplinary_retention_days=1095,
        )
        candidate = HiringCandidate.objects.create(
            company=self.company,
            requisition=self._requisition(),
            first_name="Old",
            last_name="Rejected",
            email="old@example.com",
            status=HiringCandidate.Status.REJECTED,
            rejected_at=timezone.now() - timedelta(days=400),
        )
        survey = SurveyTemplate.objects.create(company=self.company, name="Old survey")
        question = SurveyQuestion.objects.create(survey=survey, prompt="Q")
        response = SurveyResponse.objects.create(
            company=self.company,
            survey=survey,
            question=question,
            employee=self.employee,
            text_response="old",
        )
        SurveyResponse.objects.filter(pk=response.pk).update(
            submitted_at=timezone.now() - timedelta(days=800)
        )
        case = DisciplinaryCase.objects.create(
            company=self.company,
            case_number="DC-OLD",
            respondent=self.user,
            reporter=self.user,
            incident_date=date(2022, 1, 1),
            allegation_summary="Old case",
            violation_level=DisciplinaryCase.ViolationLevel.LEVEL_1,
            status=DisciplinaryCase.Status.CLOSED,
        )

        result = apply_hr_retention_task()

        candidate.refresh_from_db()
        case.refresh_from_db()
        self.assertEqual(result["policy_id"], policy.pk)
        self.assertTrue(candidate.email.startswith("deleted-candidate-"))
        self.assertFalse(SurveyResponse.objects.filter(pk=response.pk).exists())
        self.assertTrue(case.allegation_summary.startswith("Archived disciplinary case"))
