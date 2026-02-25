from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from datetime import date

from accounting.models import DisciplinaryCase, DisciplinarySanction
from payroll.models import EmployeeProfile


User = get_user_model()


class DisciplinaryWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="accounting_user",
            email="accounting@example.com",
            password="testpass123",
        )
        group, _ = Group.objects.get_or_create(name="Accountant")
        self.user.groups.add(group)

        self.respondent = User.objects.create_user(
            username="respondent_user",
            email="respondent@example.com",
            password="testpass123",
        )
        self.client.force_login(self.user)

    def test_case_create_assigns_case_number(self):
        case = DisciplinaryCase.objects.create(
            allegation_summary="Repeated lateness",
            allegation_details="Multiple lateness incidents in current month.",
            respondent=self.respondent,
            reporter=self.user,
            violation_level=DisciplinaryCase.ViolationLevel.LEVEL_2,
        )
        self.assertTrue(case.case_number.startswith("DISC-"))
        self.assertEqual(case.required_review_level, DisciplinaryCase.ReviewLevel.HR_LEAD)

    def test_create_case_view(self):
        response = self.client.post(
            reverse("payroll:discipline_case_create"),
            {
                "allegation_summary": "Policy breach",
                "allegation_details": "Ignored data handling policy.",
                "incident_date": "2026-02-01",
                "respondent": self.respondent.pk,
                "violation_level": DisciplinaryCase.ViolationLevel.LEVEL_3,
                "emergency_case": "",
                "repeat_offense_suspected": "on",
                "power_imbalance_flag": "",
                "conflict_of_interest_flag": "",
                "mental_health_context": "",
                "cultural_context": "",
                "interim_measures": "Temporary access restriction",
            },
        )
        self.assertEqual(response.status_code, 302)
        case = DisciplinaryCase.objects.get(allegation_summary="Policy breach")
        self.assertEqual(case.reporter, self.user)

    def test_start_investigation_endpoint(self):
        case = DisciplinaryCase.objects.create(
            allegation_summary="Escalation test",
            allegation_details="Details",
            respondent=self.respondent,
            reporter=self.user,
        )
        response = self.client.post(
            reverse("payroll:discipline_case_start_investigation", kwargs={"pk": case.pk})
        )
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.status, DisciplinaryCase.Status.UNDER_INVESTIGATION)
        self.assertEqual(case.investigator, self.user)

    def test_termination_sanction_disables_user_and_marks_employee_terminated(self):
        employee_profile = EmployeeProfile.objects.get(user=self.respondent)
        self.assertTrue(self.respondent.is_active)
        self.assertNotEqual(employee_profile.status, "terminated")

        case = DisciplinaryCase.objects.create(
            allegation_summary="Termination policy breach",
            allegation_details="Critical offence.",
            respondent=self.respondent,
            reporter=self.user,
            violation_level=DisciplinaryCase.ViolationLevel.LEVEL_5,
        )
        DisciplinarySanction.objects.create(
            case=case,
            sanction_type=DisciplinarySanction.SanctionType.TERMINATION,
            rationale="Final decision",
            effective_date=date(2026, 2, 1),
            created_by=self.user,
        )

        self.respondent.refresh_from_db()
        employee_profile.refresh_from_db()

        self.assertFalse(self.respondent.is_active)
        self.assertEqual(employee_profile.status, "terminated")
