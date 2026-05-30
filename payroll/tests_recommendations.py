from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from company.models import Company
from payroll.models import (
    AttendanceRecord,
    Department,
    EmployeeProfile,
    HiringCandidate,
    HiringStage,
    JobRequisition,
    LeaveBalance,
    LeaveBlackoutPeriod,
    LeaveRequest,
    Payroll,
    Position,
    SalaryHistory,
    SurveyQuestion,
    SurveyResponse,
    SurveyTemplate,
    get_leave_balance,
)
from payroll.services.access import visible_employee_profiles_for
from payroll.services.employee_data_export import build_employee_export


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class RecommendationImplementationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Recommendation Co")
        self.other_company = Company.objects.create(name="Other Co")
        self.user = User.objects.create_user(
            email="employee-rec@test.com",
            password="password123",
            first_name="Employee",
            last_name="Person",
            company=self.company,
            active_company=self.company,
        )
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.department = None
        self.employee.nin = "12345678901"
        self.employee.tin_no = "TIN-12345"
        self.employee.bank_account_name = "Employee Person"
        self.employee.bank_account_number = "0123456789"
        self.employee.pension_rsa = "RSA-123"
        self.employee.emergency_contact_phone = "08012345678"
        self.employee.save()

    def test_sensitive_employee_fields_are_encrypted_at_rest_and_decrypted_in_python(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "select nin, tin_no, bank_account_name, bank_account_number, "
                "pension_rsa, emergency_contact_phone from payroll_employeeprofile "
                "where id = %s",
                [self.employee.pk],
            )
            raw_values = cursor.fetchone()

        self.assertNotIn("12345678901", raw_values)
        self.assertTrue(all(value.startswith("enc:v1:") for value in raw_values))

        employee = EmployeeProfile.objects.get(pk=self.employee.pk)
        self.assertEqual(employee.nin, "12345678901")
        self.assertEqual(employee.bank_account_number, "0123456789")

    def test_employee_identity_properties_use_user_as_canonical_source(self):
        self.user.first_name = "Canonical"
        self.user.last_name = "Identity"
        self.user.email = "canonical@test.com"
        self.user.save()
        self.employee.refresh_from_db()

        self.assertEqual(self.employee.display_first_name, "Canonical")
        self.assertEqual(self.employee.display_last_name, "Identity")
        self.assertEqual(self.employee.get_email(), "canonical@test.com")

    def test_employee_export_supports_json_csv_and_pdf_payloads(self):
        json_payload = build_employee_export(self.employee, "json")
        csv_payload = build_employee_export(self.employee, "csv")
        pdf_payload = build_employee_export(self.employee, "pdf")

        self.assertEqual(json_payload.content_type, "application/json")
        self.assertIn('"email": "employee-rec@test.com"', json_payload.body)
        self.assertEqual(csv_payload.content_type, "text/csv")
        self.assertIn("employee-rec@test.com", csv_payload.body)
        self.assertEqual(pdf_payload.content_type, "application/pdf")
        self.assertTrue(pdf_payload.body.startswith("%PDF-1.4"))

    def test_employee_can_download_own_data_export(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("payroll:employee_data_export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertContains(response, "employee-rec@test.com")

    def test_row_level_visibility_limits_regular_users_to_self_and_managers_to_department(self):
        department = Department.objects.create(company=self.company, name="Engineering")
        self.employee.department = department
        self.employee.save(update_fields=["department"])
        manager_user = User.objects.create_user(
            email="manager-rec@test.com",
            password="password123",
            first_name="Manager",
            last_name="Person",
            company=self.company,
            active_company=self.company,
            is_manager=True,
        )
        manager_employee = manager_user.employee_user
        manager_employee.company = self.company
        manager_employee.department = department
        manager_employee.save(update_fields=["company", "department"])
        other_user = User.objects.create_user(
            email="outside-rec@test.com",
            password="password123",
            first_name="Outside",
            last_name="Person",
            company=self.other_company,
            active_company=self.other_company,
        )
        outside_employee = other_user.employee_user

        self.assertQuerySetEqual(
            visible_employee_profiles_for(self.user).order_by("id"),
            [self.employee],
        )
        visible_to_manager = list(visible_employee_profiles_for(manager_user))
        self.assertIn(self.employee, visible_to_manager)
        self.assertIn(manager_employee, visible_to_manager)
        self.assertNotIn(outside_employee, visible_to_manager)

    def test_hiring_candidate_tracks_consent_metadata_and_expiry(self):
        requisition = self._create_requisition()
        candidate = HiringCandidate.objects.create(
            company=self.company,
            requisition=requisition,
            first_name="Candidate",
            last_name="Person",
            email="candidate@test.com",
            consent_to_process=True,
        )

        self.assertIsNotNone(candidate.consent_recorded_at)
        self.assertIsNotNone(candidate.consent_expires_at)
        self.assertFalse(candidate.is_consent_expired)

        candidate.consent_expires_at = timezone.now() - timedelta(days=1)
        self.assertTrue(candidate.is_consent_expired)

    def test_rejected_candidate_retention_anonymizes_expired_records(self):
        requisition = self._create_requisition()
        candidate = HiringCandidate.objects.create(
            company=self.company,
            requisition=requisition,
            first_name="Reject",
            last_name="Me",
            email="reject@test.com",
            status=HiringCandidate.Status.REJECTED,
            rejected_at=timezone.now() - timedelta(days=800),
        )

        call_command("apply_hr_retention", "--dry-run", verbosity=0)
        candidate.refresh_from_db()
        self.assertEqual(candidate.email, "reject@test.com")

        call_command("apply_hr_retention", verbosity=0)
        candidate.refresh_from_db()
        self.assertTrue(candidate.email.startswith("deleted-candidate-"))
        self.assertEqual(candidate.first_name, "Deleted")

    def test_salary_history_records_compensation_changes(self):
        payroll = Payroll.objects.create(company=self.company, basic_salary=Decimal("100000.00"))
        self.employee.employee_pay = payroll
        self.employee.save(update_fields=["employee_pay"])
        new_payroll = Payroll.objects.create(company=self.company, basic_salary=Decimal("120000.00"))
        self.employee.employee_pay = new_payroll
        self.employee.save(update_fields=["employee_pay"])

        histories = SalaryHistory.objects.filter(employee=self.employee).order_by("effective_date", "id")
        self.assertGreaterEqual(histories.count(), 2)
        self.assertEqual(histories.last().salary_config, new_payroll)

    def test_probation_confirmation_updates_status_and_timestamp(self):
        self.employee.probation_start_date = date(2026, 1, 1)
        self.employee.probation_end_date = date(2026, 3, 31)
        self.employee.save()
        self.employee.confirm_probation(confirmed_by=self.user)

        self.assertEqual(self.employee.probation_status, EmployeeProfile.ProbationStatus.CONFIRMED)
        self.assertEqual(self.employee.status, "active")
        self.assertIsNotNone(self.employee.confirmed_at)

    def test_leave_blackout_blocks_non_override_requests(self):
        LeaveBlackoutPeriod.objects.create(
            company=self.company,
            name="Payroll close",
            start_date=date(2026, 12, 20),
            end_date=date(2026, 12, 31),
        )
        request = LeaveRequest(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 12, 24),
            end_date=date(2026, 12, 24),
            reason="Holiday",
        )

        with self.assertRaisesMessage(Exception, "blackout"):
            request.full_clean()

    def test_leave_approval_populates_attendance_records_and_carryover(self):
        LeaveBalance.objects.create(
            employee=self.employee,
            year=2025,
            annual_leave=4,
            sick_leave=1,
            casual_leave=0,
            maternity_leave=0,
            paternity_leave=0,
        )
        balance = get_leave_balance(self.employee, 2026)
        self.assertEqual(balance.carried_over_annual_leave, 4)

        request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            reason="Rest",
        )
        request.status = "APPROVED"
        request.approved_by = self.user
        request.save(user=self.user)

        records = AttendanceRecord.objects.filter(employee=self.employee, status=AttendanceRecord.Status.LEAVE)
        self.assertEqual(records.count(), 2)

    def test_old_survey_response_retention_deletes_expired_responses(self):
        survey = SurveyTemplate.objects.create(company=self.company, name="Old pulse")
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

        call_command("apply_hr_retention", verbosity=0)

        self.assertFalse(SurveyResponse.objects.filter(pk=response.pk).exists())

    def _create_requisition(self):
        position = Position.objects.create(company=self.company, title="Engineer")
        stage = HiringStage.objects.create(
            company=self.company,
            name="Sourced",
            stage_type=HiringStage.StageType.SOURCED,
        )
        return JobRequisition.objects.create(
            company=self.company,
            position=position,
            title="Engineer",
        )
