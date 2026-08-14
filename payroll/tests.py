from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from company.models import Company
from accounting.models import DisciplinaryCase, DisciplinarySanction, Journal, JournalEntry
from payroll.forms import PayrollRunCreateForm, IOURequestForm, IOUApprovalForm
from payroll.models.utils import AuditTrail
from payroll.services.ewa import ew_advance_limits
from payroll.models import (
    CompanyPayrollSetting,
    EmployeeProfile,
    LeaveRequest,
    LeaveAllowanceEmailJob,
    Allowance,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
    PayslipEmailJob,
    Appraisal,
    AppraisalAssignment,
    Review,
    Rating,
    Metric,
    Position,
    Skill,
    EmployeeSkill,
    AttendanceRecord,
    EmployeeDocument,
    AssetCategory,
    EmployeeAsset,
    WorkflowTemplate,
    WorkflowExecution,
    Goal,
    OneOnOne,
    SurveyTemplate,
    SurveyQuestion,
    SurveyResponse,
    LearningCourse,
    CourseEnrollment,
    BenefitPlan,
    BenefitEnrollment,
    HiringCandidate,
    HiringStage,
    HiringStageScorecard,
    JobOffer,
    JobRequisition,
    create_standard_hiring_stages,
    advance_candidate,
    record_candidate_scorecard,
    create_job_offer,
    accept_job_offer,
)
from payroll.views.payroll_payslips import (
    _queue_payslip_emails_for_payroll_run,
    _send_payslips_for_payroll_run,
)
from payroll.views.payroll_helpers import _get_payroll_close_journal_transaction_number
from payroll.tasks.payslip_tasks import send_payslips_for_payroll_run_task
from payroll.tasks.leave_allowance_tasks import send_leave_allowance_slip_task
from payroll.notification_signals import _dispatch_iou_rejected_event
from payroll.models import IOU

User = get_user_model()


class PayrollAllowanceRulesTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme Ltd")
        self.payroll = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("120000"),
        )
        self.employee = EmployeeProfile.objects.create(
            company=self.company,
            first_name="Jane",
            last_name="Doe",
            employee_pay=self.payroll,
        )
        self.setting = CompanyPayrollSetting.objects.create(
            company=self.company,
            leave_allowance_percentage=Decimal("15.00"),
            pays_thirteenth_month=True,
            thirteenth_month_percentage=Decimal("20.00"),
        )

    def _create_payroll_entry_for_month(self, payroll_month: int, payroll_year: int = 2026):
        payroll_entry = PayrollEntry.objects.create(
            company=self.company,
            pays=self.employee,
            status="active",
        )
        payroll_run = PayrollRun.objects.create(
            company=self.company,
            name=f"Payroll {payroll_year}-{payroll_month:02d}",
            paydays=date(payroll_year, payroll_month, 1),
            is_active=True,
        )
        PayrollRunEntry.objects.create(payroll_run=payroll_run, payroll_entry=payroll_entry)
        return payroll_entry

    def test_leave_allowance_paid_for_staff_with_approved_leave(self):
        LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 3, 10),
            end_date=date(2026, 3, 14),
            reason="Annual vacation",
            status="APPROVED",
        )
        payroll_entry = self._create_payroll_entry_for_month(payroll_month=3)

        # 15% of annual basic salary (120,000 x 12) = 216,000
        self.assertEqual(payroll_entry.calc_allowance, Decimal("216000.00"))

    def test_leave_allowance_percentage_defaults_to_ten_percent(self):
        setting = CompanyPayrollSetting.objects.create(
            company=Company.objects.create(name="Default Allowance Co")
        )

        self.assertEqual(setting.leave_allowance_percentage, Decimal("10.00"))

    @patch("payroll.models.payroll.LeaveAllowanceEmailJob.enqueue")
    def test_approving_leave_uses_default_rate_when_company_setting_is_missing(
        self, mocked_enqueue
    ):
        self.setting.delete()
        leave_request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 3, 10),
            end_date=date(2026, 3, 14),
            reason="Annual vacation",
        )

        with self.captureOnCommitCallbacks(execute=True):
            leave_request.status = "APPROVED"
            leave_request.save()

        allowance = Allowance.objects.get(source_leave_request=leave_request)
        self.assertEqual(allowance.amount, Decimal("144000.00"))
        setting = CompanyPayrollSetting.objects.get(company=self.company)
        self.assertEqual(setting.leave_allowance_percentage, Decimal("10.00"))
        mocked_enqueue.assert_called_once()

    @patch("payroll.models.payroll.LeaveAllowanceEmailJob.enqueue")
    def test_process_leave_allowances_command_backfills_only_approved_annual_leaves(
        self, mocked_enqueue
    ):
        annual_leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 5),
            reason="Legacy annual leave",
        )
        sick_leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="SICK",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            reason="Legacy sick leave",
        )
        LeaveRequest.objects.filter(pk__in=[annual_leave.pk, sick_leave.pk]).update(
            status="APPROVED"
        )

        output = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("process_leave_allowances", stdout=output)

        annual_leave.refresh_from_db()
        sick_leave.refresh_from_db()
        allowance = Allowance.objects.get(source_leave_request=annual_leave)
        self.assertEqual(allowance.amount, Decimal("216000.00"))
        self.assertFalse(
            Allowance.objects.filter(source_leave_request=sick_leave).exists()
        )
        self.assertIn("Processed 1 leave allowance(s); skipped 0.", output.getvalue())
        mocked_enqueue.assert_called_once()

    @patch("payroll.models.payroll.LeaveAllowanceEmailJob.enqueue")
    def test_process_leave_allowances_command_can_skip_email_queueing(
        self, mocked_enqueue
    ):
        annual_leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 5),
            reason="Legacy annual leave",
        )
        LeaveRequest.objects.filter(pk=annual_leave.pk).update(status="APPROVED")

        output = StringIO()
        call_command("process_leave_allowances", "--skip-email", stdout=output)

        allowance = Allowance.objects.get(source_leave_request=annual_leave)
        self.assertEqual(allowance.amount, Decimal("216000.00"))
        self.assertTrue(
            LeaveAllowanceEmailJob.objects.filter(leave_request=annual_leave).exists()
        )
        self.assertIn("Processed 1 leave allowance(s); skipped 0.", output.getvalue())
        mocked_enqueue.assert_not_called()

    @patch("payroll.models.payroll.LeaveAllowanceEmailJob.enqueue")
    def test_approving_leave_processes_allowance_and_queues_slip_email(self, mocked_enqueue):
        leave_request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 3, 10),
            end_date=date(2026, 3, 14),
            reason="Annual vacation",
        )

        with self.captureOnCommitCallbacks(execute=True):
            leave_request.status = "APPROVED"
            leave_request.save()

        allowance = Allowance.objects.get(source_leave_request=leave_request)
        self.assertEqual(allowance.employee, self.employee)
        self.assertEqual(allowance.allowance_type, "LV")
        self.assertEqual(allowance.amount, Decimal("216000.00"))

        job = LeaveAllowanceEmailJob.objects.get(leave_request=leave_request)
        self.assertEqual(job.amount, Decimal("216000.00"))
        self.assertEqual(job.status, LeaveAllowanceEmailJob.Status.QUEUED)
        mocked_enqueue.assert_called_once()

        journal = Journal.objects.get(description__startswith="Leave allowance paid to Jane Doe")
        self.assertEqual(journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(journal.content_object, allowance)
        entries = {
            entry.account.name: entry
            for entry in journal.entries.select_related("account")
        }
        self.assertEqual(
            entries["Allowances Expense"].entry_type,
            JournalEntry.EntryType.DEBIT,
        )
        self.assertEqual(entries["Allowances Expense"].amount, Decimal("216000.00"))
        self.assertEqual(
            entries["Cash and Cash Equivalents"].entry_type,
            JournalEntry.EntryType.CREDIT,
        )
        self.assertEqual(
            entries["Cash and Cash Equivalents"].amount,
            Decimal("216000.00"),
        )

        payroll_entry = self._create_payroll_entry_for_month(payroll_month=3)
        self.assertEqual(payroll_entry.calc_allowance, Decimal("216000.00"))

    @patch("payroll.models.payroll.LeaveAllowanceEmailJob.enqueue")
    def test_reapproving_leave_does_not_duplicate_allowance_or_email_job(self, mocked_enqueue):
        leave_request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 5),
            reason="Annual vacation",
        )

        with self.captureOnCommitCallbacks(execute=True):
            leave_request.status = "APPROVED"
            leave_request.save()

        mocked_enqueue.reset_mock()
        leave_request.reason = "Updated note after approval"
        with self.captureOnCommitCallbacks(execute=True):
            leave_request.save()

        self.assertEqual(Allowance.objects.filter(source_leave_request=leave_request).count(), 1)
        self.assertEqual(
            LeaveAllowanceEmailJob.objects.filter(leave_request=leave_request).count(),
            1,
        )
        self.assertEqual(
            Journal.objects.filter(description__startswith="Leave allowance paid to Jane Doe").count(),
            1,
        )
        mocked_enqueue.assert_not_called()

    def test_december_includes_thirteenth_month_as_percentage_of_annual_salary(self):
        payroll_entry = self._create_payroll_entry_for_month(payroll_month=12)
        self.assertEqual(payroll_entry.calc_allowance, Decimal("288000.00"))

    def test_december_skips_thirteenth_month_when_disabled(self):
        self.setting.pays_thirteenth_month = False
        self.setting.save(update_fields=["pays_thirteenth_month"])
        payroll_entry = self._create_payroll_entry_for_month(payroll_month=12)
        self.assertEqual(payroll_entry.calc_allowance, Decimal("0.00"))

    def test_allowances_do_not_change_taxable_income_or_paye(self):
        LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 5),
            reason="Annual vacation",
            status="APPROVED",
        )
        payroll_entry = self._create_payroll_entry_for_month(payroll_month=12)
        taxable_income_before = self.payroll.taxable_income
        payee_before = self.payroll.payee

        # December leave allowance (15% annual) + 13th month (20% annual) = 504,000
        self.assertEqual(payroll_entry.calc_allowance, Decimal("504000.00"))
        self.assertEqual(self.payroll.taxable_income, taxable_income_before)
        self.assertEqual(self.payroll.payee, payee_before)


class PayrollDisciplinaryEligibilityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Compliance Inc")
        self.hr_user = User.objects.create_user(
            email="hr@compliance.test",
            password="testpass123",
            first_name="HR",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        self.respondent = User.objects.create_user(
            email="employee@compliance.test",
            password="testpass123",
            first_name="Suspended",
            last_name="Employee",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=self.respondent)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.bank_account_number = "1234567890"
        self.employee.bank_account_name = "Fallback User"
        self.employee.bank = "GTB"
        self.employee.save(
            update_fields=[
                "company",
                "status",
                "bank_account_number",
                "bank_account_name",
                "bank",
            ]
        )

    def test_payroll_run_create_skips_suspended_employee_for_overlapping_period(self):
        case = DisciplinaryCase.objects.create(
            allegation_summary="Serious misconduct",
            allegation_details="Details",
            respondent=self.respondent,
            reporter=self.hr_user,
            violation_level=DisciplinaryCase.ViolationLevel.LEVEL_3,
        )
        DisciplinarySanction.objects.create(
            case=case,
            sanction_type=DisciplinarySanction.SanctionType.SUSPENSION,
            rationale="Suspended for investigation",
            effective_date=date(2026, 3, 5),
            duration_days=21,
            created_by=self.hr_user,
        )

        form = PayrollRunCreateForm(
            data={
                "name": "March Payroll",
                "paydays": "2026-03",
                "is_active": "on",
                "payroll_payday": str(self.employee.pk),
            },
            user=self.hr_user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        payroll_run = form.save()

        self.assertEqual(payroll_run.payroll_run_entries.count(), 0)
        self.assertTrue(getattr(payroll_run, "_skipped_employee_reasons", []))


class PayrollRunActivationRequirementTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Activation Inc")
        self.hr_user = User.objects.create_user(
            email="hr@activation.test",
            password="testpass123",
            first_name="HR",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )

    def test_payroll_run_create_requires_mark_as_active(self):
        form = PayrollRunCreateForm(
            data={
                "name": "April Payroll",
                "paydays": "2026-04",
                "payroll_payday": "",
            },
            user=self.hr_user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("is_active", form.errors)


class PayrollCloseJournalLookupTests(TestCase):
    def test_missing_close_journal_returns_none(self):
        company = Company.objects.create(name="Journal Lookup Inc")
        payroll_run = PayrollRun.objects.create(
            company=company,
            name="July Payroll",
            paydays=date(2025, 7, 1),
            is_active=True,
        )

        self.assertIsNone(_get_payroll_close_journal_transaction_number(payroll_run))


class PayrollRunCreateViewTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Create View Inc")
        self.hr_user = User.objects.create_user(
            email="hr-create-view@example.com",
            password="testpass123",
            first_name="HR",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        permission = Permission.objects.get(codename="add_payrollrun")
        self.hr_user.user_permissions.add(permission)
        self.payroll = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("100000.00"),
        )
        self.employee = EmployeeProfile.objects.create(
            company=self.company,
            first_name="Ada",
            last_name="Okafor",
            email="ada@example.com",
            status="active",
            employee_pay=self.payroll,
            net_pay=Decimal("85000.00"),
        )

    def test_create_page_bootstraps_employee_selector(self):
        self.client.force_login(self.hr_user)

        response = self.client.get(reverse("payroll:payday_create_new"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada Okafor")
        self.assertContains(response, "alpine", html=False)
        self.assertContains(response, 'x-init="init()"')

    @patch("payroll.models.payroll.PayslipEmailJob.enqueue")
    def test_create_page_post_redirects_after_queueing_payslip_email(self, mocked_enqueue):
        self.client.force_login(self.hr_user)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("payroll:payday_create_new"),
                data={
                    "name": "June Payroll",
                    "paydays": "2026-06",
                    "is_active": "on",
                    "payroll_payday": str(self.employee.pk),
                },
            )

        payroll_run = PayrollRun.objects.get(name="June Payroll")
        self.assertRedirects(
            response,
            reverse("payroll:pay_period_detail", kwargs={"slug": payroll_run.slug}),
            fetch_redirect_response=False,
        )
        self.assertEqual(payroll_run.payroll_run_entries.count(), 1)
        self.assertEqual(PayslipEmailJob.objects.filter(payroll_run=payroll_run).count(), 1)
        mocked_enqueue.assert_called_once()

    @patch("payroll.models.payroll.PayslipEmailJob.enqueue")
    def test_create_page_posts_payment_date(self, mocked_enqueue):
        self.client.force_login(self.hr_user)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("payroll:payday_create_new"),
                data={
                    "name": "June Payroll Paid",
                    "paydays": "2026-06",
                    "payment_date": "2026-06-15",
                    "is_active": "on",
                    "payroll_payday": str(self.employee.pk),
                },
            )

        payroll_run = PayrollRun.objects.get(name="June Payroll Paid")
        self.assertRedirects(
            response,
            reverse("payroll:pay_period_detail", kwargs={"slug": payroll_run.slug}),
            fetch_redirect_response=False,
        )
        self.assertEqual(payroll_run.payment_date, date(2026, 6, 15))

    def test_create_page_post_shows_error_when_no_employee_is_selected(self):
        self.client.force_login(self.hr_user)

        response = self.client.post(
            reverse("payroll:payday_create_new"),
            data={
                "name": "Empty Payroll",
                "paydays": "2026-06",
                "is_active": "on",
                "payroll_payday": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select at least one employee")
        self.assertFalse(PayrollRun.objects.filter(name="Empty Payroll").exists())

    def test_create_page_post_shows_error_for_invalid_employee_selection_payload(self):
        self.client.force_login(self.hr_user)

        response = self.client.post(
            reverse("payroll:payday_create_new"),
            data={
                "name": "Invalid Payload Payroll",
                "paydays": "2026-06",
                "is_active": "on",
                "payroll_payday": f"{self.employee.pk},not-a-number",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid employee selection")
        self.assertFalse(PayrollRun.objects.filter(name="Invalid Payload Payroll").exists())

    def test_create_page_post_shows_error_for_employee_outside_company(self):
        other_company = Company.objects.create(name="Other Co")
        other_employee = EmployeeProfile.objects.create(
            company=other_company,
            first_name="Other",
            last_name="Employee",
            status="active",
        )
        self.client.force_login(self.hr_user)

        response = self.client.post(
            reverse("payroll:payday_create_new"),
            data={
                "name": "Wrong Company Payroll",
                "paydays": "2026-06",
                "is_active": "on",
                "payroll_payday": str(other_employee.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selected employees are no longer available")
        self.assertFalse(PayrollRun.objects.filter(name="Wrong Company Payroll").exists())


class AppraisalWorkflowStandardsTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha Co")
        self.other_company = Company.objects.create(name="Beta Co")

        self.reviewer_user = User.objects.create_user(
            email="reviewer@alpha.test",
            password="testpass123",
            first_name="Assigned",
            last_name="Reviewer",
            company=self.company,
            active_company=self.company,
        )
        self.appraisee_user = User.objects.create_user(
            email="appraisee@alpha.test",
            password="testpass123",
            first_name="Target",
            last_name="Employee",
            company=self.company,
            active_company=self.company,
        )
        self.unrelated_user = User.objects.create_user(
            email="unrelated@alpha.test",
            password="testpass123",
            first_name="Unrelated",
            last_name="Employee",
            company=self.company,
            active_company=self.company,
        )

        self.reviewer_profile = EmployeeProfile.objects.get(user=self.reviewer_user)
        self.appraisee_profile = EmployeeProfile.objects.get(user=self.appraisee_user)
        self.unrelated_profile = EmployeeProfile.objects.get(user=self.unrelated_user)
        for profile in [
            self.reviewer_profile,
            self.appraisee_profile,
            self.unrelated_profile,
        ]:
            profile.company = self.company
            profile.status = "active"
            profile.save(update_fields=["company", "status"])

        self.metric_1 = Metric.objects.create(name="Quality", description="Work quality")
        self.metric_2 = Metric.objects.create(name="Delivery", description="Timeliness")

        self.appraisal = Appraisal.objects.create(
            company=self.company,
            name="Q1 2026 Appraisal",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )
        AppraisalAssignment.objects.create(
            appraisal=self.appraisal,
            appraisee=self.appraisee_profile,
            appraiser=self.reviewer_profile,
        )
        self.other_company_appraisal = Appraisal.objects.create(
            company=self.other_company,
            name="Other Company Appraisal",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        perms = Permission.objects.filter(
            codename__in=[
                "view_appraisal",
                "add_review",
                "view_review",
                "change_review",
                "delete_review",
            ]
        )
        self.reviewer_user.user_permissions.add(*perms)

    def _review_payload(self):
        return {
            "self_assessment": "Completed assigned objectives.",
            "ratings-TOTAL_FORMS": "2",
            "ratings-INITIAL_FORMS": "0",
            "ratings-MIN_NUM_FORMS": "0",
            "ratings-MAX_NUM_FORMS": "1000",
            "ratings-0-metric": str(self.metric_1.pk),
            "ratings-0-rating": "4",
            "ratings-0-comments": "Strong ownership",
            "ratings-1-metric": str(self.metric_2.pk),
            "ratings-1-rating": "5",
            "ratings-1-comments": "Delivered on schedule",
        }

    def test_assigned_reviewer_can_submit_review_with_ratings(self):
        self.client.login(email=self.reviewer_user.email, password="testpass123")
        response = self.client.post(
            reverse(
                "payroll:review_create",
                kwargs={
                    "appraisal_pk": self.appraisal.pk,
                    "employee_pk": self.appraisee_profile.pk,
                },
            ),
            data=self._review_payload(),
        )

        self.assertEqual(response.status_code, 302)
        review = Review.objects.get(
            appraisal=self.appraisal,
            employee=self.appraisee_profile,
            reviewer=self.reviewer_profile,
        )
        self.assertEqual(Rating.objects.filter(review=review).count(), 2)

    def test_unassigned_user_cannot_submit_review(self):
        self.client.login(email=self.unrelated_user.email, password="testpass123")
        unrelated_perm = Permission.objects.get(codename="add_review")
        self.unrelated_user.user_permissions.add(unrelated_perm)

        response = self.client.post(
            reverse(
                "payroll:review_create",
                kwargs={
                    "appraisal_pk": self.appraisal.pk,
                    "employee_pk": self.appraisee_profile.pk,
                },
            ),
            data=self._review_payload(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Review.objects.count(), 0)

    def test_appraisal_list_is_scoped_to_users_company(self):
        self.client.login(email=self.reviewer_user.email, password="testpass123")
        response = self.client.get(reverse("payroll:appraisal_list"))

        self.assertEqual(response.status_code, 200)
        object_list = list(response.context["object_list"])
        self.assertIn(self.appraisal, object_list)
        self.assertNotIn(self.other_company_appraisal, object_list)

    def test_employee_can_view_own_review_even_without_view_permission(self):
        review = Review.objects.create(
            appraisal=self.appraisal,
            employee=self.appraisee_profile,
            reviewer=self.reviewer_profile,
            self_assessment="Completed all goals.",
        )

        self.client.login(email=self.appraisee_user.email, password="testpass123")
        response = self.client.get(
            reverse("payroll:review_detail", kwargs={"pk": review.pk})
        )
        self.assertEqual(response.status_code, 200)


class AppraisalAssignmentEmailTests(TestCase):
    @override_settings(NOTIFICATION_SIGNALS_ENABLED=True)
    @patch("payroll.notification_signals.NotificationService.send_notification")
    @patch("payroll.notification_signals.custom_send_mail")
    def test_assignment_sends_email_to_appraisee_and_appraiser(
        self, mocked_send_mail, mocked_send_notification
    ):
        company = Company.objects.create(name="Mail Co")
        appraiser_user = User.objects.create_user(
            email="reviewer@mailco.test",
            password="testpass123",
            first_name="Rita",
            last_name="Reviewer",
            company=company,
            active_company=company,
        )
        appraisee_user = User.objects.create_user(
            email="employee@mailco.test",
            password="testpass123",
            first_name="Evan",
            last_name="Employee",
            company=company,
            active_company=company,
        )

        appraiser_profile = EmployeeProfile.objects.get(user=appraiser_user)
        appraisee_profile = EmployeeProfile.objects.get(user=appraisee_user)
        appraiser_profile.company = company
        appraiser_profile.save(update_fields=["company"])
        appraisee_profile.company = company
        appraisee_profile.save(update_fields=["company"])

        appraisal = Appraisal.objects.create(
            company=company,
            name="Q2 Appraisal",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
        )

        AppraisalAssignment.objects.create(
            appraisal=appraisal,
            appraisee=appraisee_profile,
            appraiser=appraiser_profile,
        )

        self.assertEqual(mocked_send_mail.call_count, 2)
        recipients = {
            mocked_send_mail.call_args_list[0].kwargs["recipient_list"][0],
            mocked_send_mail.call_args_list[1].kwargs["recipient_list"][0],
        }
        self.assertEqual(
            recipients,
            {appraisee_user.email, appraiser_user.email},
        )


class PayrollRunPayslipEmailTests(TestCase):
    @patch("payroll.views.payroll_payslips.custom_send_mail")
    @patch("payroll.views.payroll_payslips.generate_payslip_pdf")
    def test_send_payslips_for_payroll_run_sends_email_with_attachment(
        self, mocked_generate_pdf, mocked_send_mail
    ):
        mocked_generate_pdf.return_value = b"%PDF-1.4 fake"
        company = Company.objects.create(name="Payroll Mail Co")
        user = User.objects.create_user(
            email="employee@payrollmail.test",
            password="testpass123",
            first_name="Pat",
            last_name="Worker",
            company=company,
            active_company=company,
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = company
        employee.status = "active"
        employee.save(update_fields=["company", "status"])

        payroll_run = PayrollRun.objects.create(
            company=company,
            name="May Payroll",
            paydays=date(2026, 5, 1),
            is_active=True,
        )
        payroll_entry = PayrollEntry.objects.create(
            company=company,
            pays=employee,
            status="active",
        )
        PayrollRunEntry.objects.create(
            payroll_run=payroll_run,
            payroll_entry=payroll_entry,
        )

        sent_count, skipped_count = _send_payslips_for_payroll_run(payroll_run)

        self.assertEqual(sent_count, 1)
        self.assertEqual(skipped_count, [])
        self.assertEqual(mocked_send_mail.call_count, 1)
        kwargs = mocked_send_mail.call_args.kwargs
        self.assertEqual(kwargs["recipient_list"], [user.email])
        self.assertEqual(kwargs["template_name"], "email/payslip_email.html")
        self.assertEqual(len(kwargs["attachments"]), 1)
        attachment = kwargs["attachments"][0]
        self.assertTrue(attachment["filename"].endswith(".pdf"))
        self.assertIn("payslip_", attachment["filename"])
        self.assertEqual(attachment["content"], mocked_generate_pdf.return_value)
        self.assertEqual(attachment["mimetype"], "application/pdf")

    @patch("payroll.tasks.payslip_tasks.send_payslips_for_payroll_run_task.apply_async")
    @patch("payroll.views.payroll_payslips.custom_send_mail")
    @patch("payroll.views.payroll_payslips.generate_payslip_pdf")
    def test_queue_payslip_emails_creates_job_and_defers_delivery_until_after_commit(
        self, mocked_generate_pdf, mocked_send_mail, mocked_apply_async
    ):
        mocked_apply_async.return_value.id = "celery-task-123"
        company = Company.objects.create(name="Async Payroll Mail Co")
        payroll_run = PayrollRun.objects.create(
            company=company,
            name="June Payroll",
            paydays=date(2026, 6, 1),
            is_active=True,
        )

        with self.captureOnCommitCallbacks(execute=True):
            job = _queue_payslip_emails_for_payroll_run(payroll_run)

        self.assertEqual(job.payroll_run, payroll_run)
        self.assertEqual(job.status, PayslipEmailJob.Status.QUEUED)
        mocked_generate_pdf.assert_not_called()
        mocked_send_mail.assert_not_called()
        mocked_apply_async.assert_called_once_with(
            args=[payroll_run.id, job.id],
            queue="notifications_normal",
        )
        job.refresh_from_db()
        self.assertEqual(job.celery_task_id, "celery-task-123")

    @patch("payroll.views.payroll_payslips._send_payslips_for_payroll_run")
    def test_payslip_task_marks_job_as_sent(self, mocked_send_payslips):
        mocked_send_payslips.return_value = (2, [])
        company = Company.objects.create(name="Task Status Co")
        payroll_run = PayrollRun.objects.create(
            company=company,
            name="July Payroll",
            paydays=date(2026, 7, 1),
            is_active=True,
        )
        job = PayslipEmailJob.objects.create(payroll_run=payroll_run)

        result = send_payslips_for_payroll_run_task(payroll_run.id, job.id)

        job.refresh_from_db()
        self.assertTrue(result["success"])
        self.assertEqual(job.status, PayslipEmailJob.Status.SENT)
        self.assertEqual(job.sent_count, 2)
        self.assertEqual(job.skipped_count, 0)
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.completed_at)

    @patch("payroll.tasks.leave_allowance_tasks.custom_send_mail")
    @patch("payroll.tasks.leave_allowance_tasks.generate_payslip_pdf")
    def test_leave_allowance_task_sends_pdf_slip_and_marks_job_sent(
        self, mocked_generate_pdf, mocked_send_mail
    ):
        mocked_generate_pdf.return_value = b"%PDF leave allowance"
        company = Company.objects.create(name="Leave Allowance Mail Co")
        payroll = Payroll.objects.create(
            company=company,
            basic_salary=Decimal("200000.00"),
        )
        user = User.objects.create_user(
            email="allowance.employee@test.com",
            password="testpass123",
            company=company,
            active_company=company,
        )
        employee = user.employee_user
        employee.company = company
        employee.employee_pay = payroll
        employee.save(update_fields=["company", "employee_pay"])
        CompanyPayrollSetting.objects.create(
            company=company,
            leave_allowance_percentage=Decimal("10.00"),
        )
        leave_request = LeaveRequest.objects.create(
            employee=employee,
            leave_type="ANNUAL",
            start_date=date(2026, 5, 4),
            end_date=date(2026, 5, 8),
            reason="Annual vacation",
            status="APPROVED",
        )
        allowance = Allowance.objects.get(source_leave_request=leave_request)
        job = LeaveAllowanceEmailJob.objects.get(leave_request=leave_request)

        result = send_leave_allowance_slip_task(leave_request.id, job.id)

        self.assertTrue(result["success"])
        self.assertEqual(result["amount"], "240000.00")
        mocked_generate_pdf.assert_called_once()
        mocked_send_mail.assert_called_once()
        kwargs = mocked_send_mail.call_args.kwargs
        self.assertEqual(kwargs["recipient_list"], [user.email])
        self.assertEqual(kwargs["template_name"], "email/leave_allowance_slip_email.html")
        self.assertEqual(kwargs["context"]["allowance"], allowance)
        attachment = kwargs["attachments"][0]
        self.assertTrue(attachment["filename"].endswith(".pdf"))
        self.assertIn("leave_allowance_slip_", attachment["filename"])
        self.assertEqual(attachment["content"], mocked_generate_pdf.return_value)
        self.assertEqual(attachment["mimetype"], "application/pdf")

        job.refresh_from_db()
        self.assertEqual(job.status, LeaveAllowanceEmailJob.Status.SENT)
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.completed_at)

    @patch(
        "payroll.management.commands.process_leave_allowance_email_jobs.send_leave_allowance_slip_task"
    )
    def test_process_leave_allowance_email_jobs_sends_existing_queued_jobs(
        self, mocked_task
    ):
        company = Company.objects.create(name="Leave Allowance Queue Co")
        payroll = Payroll.objects.create(
            company=company,
            basic_salary=Decimal("200000.00"),
        )
        employee = EmployeeProfile.objects.create(
            company=company,
            first_name="Queued",
            last_name="Allowance",
            employee_pay=payroll,
        )
        CompanyPayrollSetting.objects.create(
            company=company,
            leave_allowance_percentage=Decimal("10.00"),
        )
        leave_request = LeaveRequest.objects.create(
            employee=employee,
            leave_type="ANNUAL",
            start_date=date(2026, 5, 4),
            end_date=date(2026, 5, 8),
            reason="Annual vacation",
        )
        LeaveRequest.objects.filter(pk=leave_request.pk).update(status="APPROVED")
        call_command("process_leave_allowances", "--skip-email", stdout=StringIO())
        job = LeaveAllowanceEmailJob.objects.get(leave_request=leave_request)

        output = StringIO()
        call_command("process_leave_allowance_email_jobs", stdout=output)

        mocked_task.assert_called_once_with(leave_request.id, job.id)
        self.assertIn("Processed 1 leave allowance email job(s).", output.getvalue())

    @patch("payroll.models.payroll.PayslipEmailJob.enqueue")
    def test_admin_resend_job_url_requeues_selected_job(self, mocked_enqueue):
        admin_user = User.objects.create_superuser(
            email="admin-payslip@example.com",
            password="testpass123",
        )
        self.client.force_login(admin_user)
        company = Company.objects.create(name="Admin Resend Co")
        payroll_run = PayrollRun.objects.create(
            company=company,
            name="August Payroll",
            paydays=date(2026, 8, 1),
            is_active=True,
        )
        job = PayslipEmailJob.objects.create(
            payroll_run=payroll_run,
            status=PayslipEmailJob.Status.FAILED,
            error_message="SMTP timeout",
        )

        response = self.client.post(
            reverse("admin:payroll_payslipemailjob_resend", args=[job.id])
        )

        self.assertEqual(response.status_code, 302)
        mocked_enqueue.assert_called_once_with()

    @patch(
        "payroll.management.commands.process_payslip_email_jobs."
        "send_payslips_for_payroll_run_task"
    )
    def test_process_payslip_email_jobs_command_runs_queued_jobs(self, mocked_task):
        company = Company.objects.create(name="Command Fallback Co")
        payroll_run = PayrollRun.objects.create(
            company=company,
            name="September Payroll",
            paydays=date(2026, 9, 1),
            is_active=True,
        )
        job = PayslipEmailJob.objects.create(
            payroll_run=payroll_run,
            status=PayslipEmailJob.Status.QUEUED,
        )
        output = StringIO()

        call_command("process_payslip_email_jobs", "--limit=1", stdout=output)

        mocked_task.assert_called_once_with(payroll_run.id, job.id)
        self.assertIn("Processed 1 payslip email job(s).", output.getvalue())

    def test_core_exports_celery_app_with_payslip_task_registered(self):
        import core

        self.assertTrue(hasattr(core, "celery_app"))
        self.assertIn("payroll.send_payslips_for_payroll_run", core.celery_app.tasks)


class HRComplianceRulesTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Compliance Co")
        self.user = User.objects.create_user(
            email="compliance@example.com",
            password="testpass123",
            first_name="Comp",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])

    def test_company_payroll_setting_enforces_nigeria_baseline(self):
        setting = CompanyPayrollSetting(company=self.company)
        setting.pension_employee_percentage = Decimal("6.00")
        with self.assertRaises(ValidationError):
            setting.full_clean()

    def test_company_setup_edit_exposes_annual_leave_allowance_rate(self):
        permission = Permission.objects.get(codename="change_companypayrollsetting")
        self.user.user_permissions.add(permission)
        CompanyPayrollSetting.objects.create(company=self.company)
        self.client.force_login(self.user)

        response = self.client.get(reverse("payroll:company_payroll_settings_edit"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Annual Leave Allowance Rate (%)")
        self.assertContains(response, "Percentage of annual basic salary paid")

    def test_company_setup_edit_saves_annual_leave_allowance_rate(self):
        permission = Permission.objects.get(codename="change_companypayrollsetting")
        self.user.user_permissions.add(permission)
        setting = CompanyPayrollSetting.objects.create(company=self.company)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("payroll:company_payroll_settings_edit"),
            data={
                "basic_percentage": "40.00",
                "housing_percentage": "10.00",
                "transport_percentage": "10.00",
                "pension_employee_percentage": "8.00",
                "pension_employer_percentage": "10.00",
                "nhf_percentage": "2.50",
                "leave_allowance_percentage": "12.50",
                "pays_thirteenth_month": "on",
                "thirteenth_month_percentage": "20.00",
                "tiers-TOTAL_FORMS": "0",
                "tiers-INITIAL_FORMS": "0",
                "tiers-MIN_NUM_FORMS": "0",
                "tiers-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertRedirects(response, reverse("payroll:company_payroll_settings"))
        setting.refresh_from_db()
        self.assertEqual(setting.leave_allowance_percentage, Decimal("12.50"))

    def test_leave_request_cannot_overlap_existing_pending_or_approved_request(self):
        LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 4, 10),
            end_date=date(2026, 4, 12),
            reason="Vacation",
            status="PENDING",
        )
        overlapping = LeaveRequest(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 4, 11),
            end_date=date(2026, 4, 15),
            reason="Overlap request",
            status="PENDING",
        )
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    @patch("payroll.notification_signals.event_dispatcher.dispatch")
    @patch("payroll.notification_signals.NotificationService.send_notification")
    def test_iou_rejected_event_uses_rejected_event_type(
        self, mocked_send_notification, mocked_dispatch
    ):
        iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal("20000.00"),
            tenor=2,
            status="REJECTED",
        )

        _dispatch_iou_rejected_event(iou)

        kwargs = mocked_dispatch.call_args.kwargs
        self.assertEqual(kwargs["event_type"], "iou.rejected")
        self.assertEqual(kwargs["event_data"]["event_type"], "iou.rejected")


class IOUTenorApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="IOU Workflow Co")
        self.user = User.objects.create_user(
            email="iou-workflow@example.com",
            password="testpass123",
            first_name="Iou",
            last_name="Employee",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.employee_pay = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("200000.00"),
        )
        self.employee.net_pay = Decimal("200000.00")
        self.employee.save(update_fields=["company", "status", "employee_pay", "net_pay"])

    def test_request_form_accepts_user_selected_tenor(self):
        form = IOURequestForm(
            data={
                "amount": "50000.00",
                "tenor": "4",
                "reason": "Medical support",
            },
            max_iou_amount=Decimal("150000.00"),
        )
        self.assertTrue(form.is_valid(), form.errors)
        iou = form.save(commit=False)
        iou.employee_id = self.employee
        iou.save()
        self.assertEqual(iou.tenor, 4)
        expected_due_date = IOURequestForm._add_months(timezone.localdate(), 4)
        self.assertEqual(iou.due_date, expected_due_date)

    def test_approval_form_can_override_tenor_and_set_repayment_percentage(self):
        iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal("120000.00"),
            tenor=3,
            reason="Urgent support",
            status="PENDING",
        )
        form = IOUApprovalForm(
            data={
                "status": "APPROVED",
                "approved_at": "2026-03-01",
                "tenor": "6",
                "repayment_deduction_percentage": "20.00",
            },
            instance=iou,
        )
        self.assertTrue(form.is_valid(), form.errors)
        approved_iou = form.save()
        self.assertEqual(approved_iou.status, "APPROVED")
        self.assertEqual(approved_iou.tenor, 6)
        self.assertEqual(
            approved_iou.repayment_deduction_percentage, Decimal("20.00")
        )

    def test_salary_deduction_is_created_from_netpay_percentage(self):
        iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal("100000.00"),
            tenor=3,
            repayment_deduction_percentage=Decimal("25.00"),
            reason="Urgent support",
            status="APPROVED",
            approved_at=date(2026, 7, 1),
        )
        payroll_entry = PayrollEntry.objects.create(
            company=self.company,
            pays=self.employee,
            status="active",
        )
        payroll_run = PayrollRun.objects.create(
            company=self.company,
            name="July Payroll",
            paydays=date(2026, 7, 1),
            is_active=True,
        )

        PayrollRunEntry.objects.create(
            payroll_run=payroll_run,
            payroll_entry=payroll_entry,
        )

        expected_deduction = (
            Decimal(self.employee.net_pay) * Decimal("25.00") / Decimal("100")
        )
        deduction = iou.deductions.get(payday=payroll_run)
        self.assertEqual(deduction.amount, expected_deduction)
        payroll_entry.refresh_from_db()
        self.assertEqual(payroll_entry.netpay, Decimal(self.employee.net_pay) - expected_deduction)

    def test_iou_payment_slip_page_renders(self):
        iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal("120000.00"),
            tenor=6,
            repayment_deduction_percentage=Decimal("20.00"),
            reason="Urgent support",
            status="APPROVED",
            approved_at=date(2026, 3, 1),
        )
        self.client.login(email=self.user.email, password="testpass123")
        response = self.client.get(
            reverse("payroll:iou_payment_slip", kwargs={"pk": iou.pk})
        )
        self.assertEqual(response.status_code, 200)


class EmployeeLeaveIOUTemplateSmokeTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Smoke Co")
        self.user = User.objects.create_user(
            email="smoke-admin@example.com",
            password="testpass123",
            first_name="Smoke",
            last_name="Admin",
            company=self.company,
            active_company=self.company,
            is_staff=True,
            is_superuser=True,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])

        self.leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 12),
            reason="Template smoke leave",
            status="PENDING",
        )
        self.iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal("25000.00"),
            tenor=2,
            reason="Template smoke iou",
            status="PENDING",
            due_date=date(2026, 6, 30),
        )
        self.client.login(email=self.user.email, password="testpass123")

    def test_leave_and_iou_pages_render_without_server_error(self):
        targets = [
            ("payroll:apply_leave", {}),
            ("payroll:leave_requests", {}),
            ("payroll:manage_leave_requests", {}),
            ("payroll:edit_leave_request", {"pk": self.leave.pk}),
            ("payroll:view_leave_request", {"pk": self.leave.pk}),
            ("payroll:request_iou", {}),
            ("payroll:approve_iou", {"iou_id": self.iou.pk}),
            ("payroll:iou_update", {"pk": self.iou.pk}),
            ("payroll:iou_delete", {"pk": self.iou.pk}),
            ("payroll:iou_history", {}),
            ("payroll:my_iou_tracker", {}),
            ("payroll:iou_list", {}),
            ("payroll:iou_detail", {"pk": self.iou.pk}),
        ]

        for route_name, kwargs in targets:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name, kwargs=kwargs))
                self.assertIn(
                    response.status_code,
                    (200, 302),
                    f"{route_name} returned {response.status_code}",
                )


class EmployeeLeaveIOUUrlWalkSmokeTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="URL Walk Co")
        self.user = User.objects.create_user(
            email="url-walk-admin@example.com",
            password="testpass123",
            first_name="Url",
            last_name="Walker",
            company=self.company,
            active_company=self.company,
            is_staff=True,
            is_superuser=True,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])

        self.target_user = User.objects.create_user(
            email="url-walk-target@example.com",
            password="testpass123",
            first_name="Target",
            last_name="Employee",
            company=self.company,
            active_company=self.company,
        )
        self.target_employee = EmployeeProfile.objects.get(user=self.target_user)
        self.target_employee.company = self.company
        self.target_employee.status = "active"
        self.target_employee.save(update_fields=["company", "status"])

        self.leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
            reason="URL walk leave",
            status="PENDING",
        )
        self.leave_to_delete = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="CASUAL",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
            reason="URL walk leave delete",
            status="PENDING",
        )
        self.iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal("10000.00"),
            tenor=2,
            reason="URL walk iou",
            status="PENDING",
            due_date=date(2026, 8, 31),
        )

        self.client.login(email=self.user.email, password="testpass123")

    def test_every_employee_leave_iou_route_responds_without_server_error(self):
        targets = [
            ("payroll:employee_profile", {}),
            ("payroll:hr_dashboard", {}),
            ("payroll:employee_list", {}),
            ("payroll:add_employee", {}),
            ("payroll:profile", {"user_id": self.employee.user_id}),
            ("payroll:update_employee", {"id": self.employee.id}),
            ("payroll:apply_leave", {}),
            ("payroll:leave_requests", {}),
            ("payroll:manage_leave_requests", {}),
            ("payroll:leave_policies", {}),
            ("payroll:edit_leave_request", {"pk": self.leave.pk}),
            ("payroll:view_leave_request", {"pk": self.leave.pk}),
            ("payroll:request_iou", {}),
            ("payroll:approve_iou", {"iou_id": self.iou.pk}),
            ("payroll:iou_update", {"pk": self.iou.pk}),
            ("payroll:iou_delete", {"pk": self.iou.pk}),
            ("payroll:iou_history", {}),
            ("payroll:my_iou_tracker", {}),
            ("payroll:iou_list", {}),
            ("payroll:iou_detail", {"pk": self.iou.pk}),
            ("payroll:delete_leave_request", {"pk": self.leave_to_delete.pk}),
        ]

        for route_name, kwargs in targets:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name, kwargs=kwargs))
                self.assertLess(
                    response.status_code,
                    500,
                    f"{route_name} returned server error {response.status_code}",
                )

        post_targets = [
            ("payroll:approve_leave", {"pk": self.leave.pk}),
            ("payroll:reject_leave", {"pk": self.leave.pk}),
            ("payroll:delete_employee", {"id": self.target_employee.id}),
        ]

        for route_name, kwargs in post_targets:
            with self.subTest(route=route_name):
                response = self.client.post(reverse(route_name, kwargs=kwargs))
                self.assertLess(
                    response.status_code,
                    500,
                    f"{route_name} returned server error {response.status_code}",
                )


class PayrollReportSmokeTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Report Co")
        self.user = User.objects.create_user(
            email="report-admin@example.com",
            password="testpass123",
            first_name="Report",
            last_name="Admin",
            company=self.company,
            active_company=self.company,
            is_staff=True,
            is_superuser=True,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])

        payroll_config = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("120000.00"),
        )
        self.employee.employee_pay = payroll_config
        self.employee.save(update_fields=["employee_pay"])

        self.payroll_run = PayrollRun.objects.create(
            company=self.company,
            name="June 2026 Payroll",
            paydays=date(2026, 6, 1),
            is_active=True,
        )
        payroll_entry = PayrollEntry.objects.create(
            company=self.company,
            pays=self.employee,
            status="active",
        )
        PayrollRunEntry.objects.create(
            payroll_run=self.payroll_run,
            payroll_entry=payroll_entry,
        )
        self.client.login(email=self.user.email, password="testpass123")

    def test_nhis_and_nhf_report_pages_render(self):
        nhis_response = self.client.get(
            reverse("payroll:nhisreport", kwargs={"pay_id": self.payroll_run.id})
        )
        nhf_response = self.client.get(
            reverse("payroll:nhfReport", kwargs={"pay_id": self.payroll_run.id})
        )
        self.assertEqual(nhis_response.status_code, 200)
        self.assertEqual(nhf_response.status_code, 200)


class PayslipDetailFallbackTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Payslip Fallback Co")
        self.user = User.objects.create_user(
            email="fallback@example.com",
            password="testpass123",
            first_name="Fallback",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])

        payroll_config = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("120000.00"),
        )
        self.employee.employee_pay = payroll_config
        self.employee.save(update_fields=["employee_pay"])

        payroll_run = PayrollRun.objects.create(
            company=self.company,
            name="April 2026 Payroll",
            paydays=date(2026, 4, 1),
            is_active=True,
        )
        PayrollEntry.objects.create(
            company=self.company,
            pays=self.employee,
            status="active",
        )
        self.payroll_entry = PayrollEntry.objects.create(
            company=self.company,
            pays=self.employee,
            status="active",
        )
        self.payslip = PayrollRunEntry.objects.create(
            payroll_run=payroll_run,
            payroll_entry=self.payroll_entry,
        )
        self.client.login(email=self.user.email, password="testpass123")

    def test_payslip_detail_falls_back_when_employee_id_is_used(self):
        response = self.client.get(
            reverse("payroll:payslip", kwargs={"id": self.employee.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "April 2026")

    def test_payslip_detail_falls_back_when_payroll_entry_id_is_used(self):
        response = self.client.get(
            reverse("payroll:payslip", kwargs={"id": self.payroll_entry.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "April 2026")

    def test_payslip_detail_allows_self_access_when_user_company_context_changes(self):
        other_company = Company.objects.create(name="Other Company")
        self.user.company = other_company
        self.user.active_company = other_company
        self.user.save(update_fields=["company", "active_company"])

        response = self.client.get(
            reverse("payroll:payslip", kwargs={"id": self.payslip.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "April 2026")

    def test_payslip_pdf_accepts_payroll_run_entry_id(self):
        response = self.client.get(
            reverse("payroll:payslip_pdf", kwargs={"id": self.payslip.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")


class WorkforceExpansionFoundationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Expansion Co")
        self.user = User.objects.create_user(
            email="foundations@example.com",
            password="testpass123",
            first_name="Foundation",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save(update_fields=["company", "status"])

    def test_can_create_workforce_foundation_records(self):
        position = Position.objects.create(
            company=self.company,
            title="Senior Product Analyst",
            department=self.employee.department,
            employment_type=Position.EmploymentType.FULL_TIME,
            status=Position.Status.OPEN,
        )
        skill = Skill.objects.create(
            company=self.company,
            name="Payroll Compliance",
            category="Compliance",
        )
        employee_skill = EmployeeSkill.objects.create(
            company=self.company,
            employee=self.employee,
            skill=skill,
            proficiency=EmployeeSkill.Proficiency.ADVANCED,
        )
        attendance = AttendanceRecord.objects.create(
            company=self.company,
            employee=self.employee,
            work_date=date(2026, 4, 1),
            status=AttendanceRecord.Status.PRESENT,
            hours_worked=Decimal("8.00"),
        )
        document = EmployeeDocument.objects.create(
            company=self.company,
            employee=self.employee,
            title="Signed Handbook",
            document_type=EmployeeDocument.DocumentType.POLICY,
            acknowledgement_required=True,
            is_acknowledged=True,
        )
        category = AssetCategory.objects.create(
            company=self.company,
            name="Laptop",
        )
        asset = EmployeeAsset.objects.create(
            company=self.company,
            employee=self.employee,
            category=category,
            asset_tag="LAP-001",
            name="MacBook Pro",
            status=EmployeeAsset.Status.IN_USE,
        )
        workflow = WorkflowTemplate.objects.create(
            company=self.company,
            name="Employee Onboarding",
            workflow_type=WorkflowTemplate.WorkflowType.ONBOARDING,
            trigger_event="employee.created",
        )
        execution = WorkflowExecution.objects.create(
            company=self.company,
            template=workflow,
            employee=self.employee,
            status=WorkflowExecution.Status.IN_PROGRESS,
        )
        goal = Goal.objects.create(
            company=self.company,
            employee=self.employee,
            title="Reduce payroll processing exceptions",
            cycle="Q2 2026",
            status=Goal.Status.ACTIVE,
        )
        one_on_one = OneOnOne.objects.create(
            company=self.company,
            employee=self.employee,
            manager=self.user,
            scheduled_for=timezone.now(),
            status=OneOnOne.Status.SCHEDULED,
        )
        survey = SurveyTemplate.objects.create(
            company=self.company,
            name="Quarterly Pulse",
            survey_type=SurveyTemplate.SurveyType.PULSE,
            is_anonymous=False,
        )
        question = SurveyQuestion.objects.create(
            survey=survey,
            prompt="How supported do you feel at work?",
            question_type=SurveyQuestion.QuestionType.RATING,
            order=1,
        )
        response = SurveyResponse.objects.create(
            company=self.company,
            survey=survey,
            question=question,
            employee=self.employee,
            numeric_response=4,
        )
        course = LearningCourse.objects.create(
            company=self.company,
            title="Workplace Conduct",
            course_type=LearningCourse.CourseType.COMPLIANCE,
            delivery_mode=LearningCourse.DeliveryMode.SELF_PACED,
        )
        enrollment = CourseEnrollment.objects.create(
            company=self.company,
            course=course,
            employee=self.employee,
            status=CourseEnrollment.Status.ENROLLED,
        )
        benefit = BenefitPlan.objects.create(
            company=self.company,
            name="Health Plus",
            plan_type=BenefitPlan.PlanType.HEALTH,
            enrollment_window_start=date(2026, 4, 1),
            enrollment_window_end=date(2026, 4, 30),
        )
        benefit_enrollment = BenefitEnrollment.objects.create(
            company=self.company,
            plan=benefit,
            employee=self.employee,
            status=BenefitEnrollment.Status.ENROLLED,
        )

        self.assertEqual(str(position), "Senior Product Analyst")
        self.assertEqual(employee_skill.skill.name, "Payroll Compliance")
        self.assertEqual(attendance.hours_worked, Decimal("8.00"))
        self.assertTrue(document.is_acknowledged)
        self.assertEqual(asset.asset_tag, "LAP-001")
        self.assertEqual(execution.template, workflow)
        self.assertEqual(goal.employee, self.employee)
        self.assertEqual(one_on_one.manager, self.user)
        self.assertEqual(response.numeric_response, 4)
        self.assertEqual(enrollment.course, course)
        self.assertEqual(benefit_enrollment.plan, benefit)


class HiringWorkflowFoundationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Hiring Workflow Co")
        self.hr_user = User.objects.create_user(
            email="hiring-hr@example.com",
            password="password123",
            first_name="Hiring",
            last_name="HR",
            company=self.company,
            active_company=self.company,
        )
        self.position = Position.objects.create(
            company=self.company,
            title="Senior Payroll Specialist",
            employment_type=Position.EmploymentType.FULL_TIME,
            status=Position.Status.OPEN,
        )

    def test_standard_hiring_stages_are_created_in_objective_order(self):
        stages = create_standard_hiring_stages(self.company)

        self.assertEqual(
            [stage.stage_type for stage in stages],
            [
                HiringStage.StageType.SOURCED,
                HiringStage.StageType.SCREENING,
                HiringStage.StageType.STRUCTURED_INTERVIEW,
                HiringStage.StageType.SCORECARD_REVIEW,
                HiringStage.StageType.REFERENCE_CHECK,
                HiringStage.StageType.OFFER,
                HiringStage.StageType.HIRED,
            ],
        )
        self.assertTrue(all(stage.requires_scorecard for stage in stages[2:4]))
        self.assertTrue(all(stage.is_active for stage in stages))

    def test_candidate_cannot_advance_past_scorecard_stage_without_scorecard(self):
        stages = create_standard_hiring_stages(self.company)
        requisition = JobRequisition.objects.create(
            company=self.company,
            position=self.position,
            title="Senior Payroll Specialist",
            hiring_manager=self.hr_user,
            opened_by=self.hr_user,
        )
        candidate = HiringCandidate.objects.create(
            company=self.company,
            requisition=requisition,
            first_name="Ada",
            last_name="Candidate",
            email="ada@example.com",
            current_stage=stages[1],
        )

        with self.assertRaisesMessage(ValueError, "scorecard"):
            advance_candidate(candidate, stages[2], advanced_by=self.hr_user)

    def test_scorecard_allows_structured_candidate_progression(self):
        stages = create_standard_hiring_stages(self.company)
        requisition = JobRequisition.objects.create(
            company=self.company,
            position=self.position,
            title="Senior Payroll Specialist",
            hiring_manager=self.hr_user,
            opened_by=self.hr_user,
        )
        candidate = HiringCandidate.objects.create(
            company=self.company,
            requisition=requisition,
            first_name="Tomi",
            last_name="Candidate",
            email="tomi@example.com",
            current_stage=stages[1],
        )

        scorecard = record_candidate_scorecard(
            candidate=candidate,
            stage=stages[2],
            interviewer=self.hr_user,
            competency_scores={
                "role_fit": 4,
                "technical_depth": 5,
                "values_alignment": 4,
            },
            recommendation=HiringStageScorecard.Recommendation.STRONG_YES,
            notes="Evidence-based structured interview.",
        )
        advance_candidate(candidate, stages[2], advanced_by=self.hr_user)

        candidate.refresh_from_db()
        self.assertEqual(scorecard.average_score, Decimal("4.33"))
        self.assertEqual(candidate.current_stage, stages[2])
        self.assertEqual(candidate.status, HiringCandidate.Status.IN_PROCESS)

    def test_accepting_offer_marks_candidate_hired_and_starts_onboarding(self):
        stages = create_standard_hiring_stages(self.company)
        onboarding_template = WorkflowTemplate.objects.create(
            company=self.company,
            name="New Hire Onboarding",
            workflow_type=WorkflowTemplate.WorkflowType.ONBOARDING,
            trigger_event="candidate.hired",
        )
        requisition = JobRequisition.objects.create(
            company=self.company,
            position=self.position,
            title="Senior Payroll Specialist",
            hiring_manager=self.hr_user,
            opened_by=self.hr_user,
            headcount=1,
        )
        candidate = HiringCandidate.objects.create(
            company=self.company,
            requisition=requisition,
            first_name="Mira",
            last_name="Hire",
            email="mira@example.com",
            current_stage=stages[5],
            status=HiringCandidate.Status.OFFER,
        )
        offer = create_job_offer(
            candidate=candidate,
            title="Senior Payroll Specialist",
            employment_type=Position.EmploymentType.FULL_TIME,
            salary_amount=Decimal("450000.00"),
            currency="NGN",
            start_date=date(2026, 7, 1),
            created_by=self.hr_user,
        )

        execution = accept_job_offer(offer, accepted_by=self.hr_user)

        candidate.refresh_from_db()
        requisition.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(candidate.status, HiringCandidate.Status.HIRED)
        self.assertEqual(candidate.current_stage.stage_type, HiringStage.StageType.HIRED)
        self.assertEqual(offer.status, JobOffer.Status.ACCEPTED)
        self.assertEqual(requisition.status, JobRequisition.Status.FILLED)
        self.assertEqual(execution.template, onboarding_template)
        self.assertEqual(execution.context["candidate_email"], "mira@example.com")


class EWAAdvanceEngineTests(TestCase):
    """EWA productizes the IOU engine: advance caps, frequency rules, guardrails."""

    def setUp(self):
        self.company = Company.objects.create(name="EWA Co")
        self.user = get_user_model().objects.create_user(
            email="ewa@example.com",
            password="testpass123",
            first_name="Ewa",
            last_name="Employee",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.employee_pay = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("200000.00")
        )
        self.employee.save(update_fields=["company", "status", "employee_pay"])
        # EmployeeProfile.save() recomputes net_pay; pin it via update() so
        # the engine tests assert against a deterministic 200,000.
        EmployeeProfile.objects.filter(pk=self.employee.pk).update(
            net_pay=Decimal("200000.00")
        )
        self.employee.refresh_from_db()
        self.setting = CompanyPayrollSetting.objects.create(
            company=self.company, ewa_enabled=True
        )

    def _add_advance(self, amount, status="APPROVED", created=None):
        iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal(amount),
            tenor=1,
            status=status,
            is_ewa=True,
        )
        if created:
            IOU.objects.filter(pk=iou.pk).update(created_at=created)
        return iou

    def test_advance_cap_scales_with_earned_pay(self):
        # June 2026 has 30 days: by the 15th half the net is earned, and the
        # 50% advance cap = 50,000 for a 200,000 monthly net.
        limits = ew_advance_limits(self.employee, as_of=date(2026, 6, 15))
        self.assertTrue(limits["enabled"])
        self.assertEqual(limits["earned_net"], Decimal("100000.00"))
        self.assertEqual(limits["cycle_advance_cap"], Decimal("50000.00"))
        self.assertEqual(limits["max_available"], Decimal("50000.00"))
        self.assertTrue(limits["eligible"])

    def test_frequency_rule_blocks_after_max_per_cycle(self):
        self._add_advance("20000")
        self._add_advance("30000")
        limits = ew_advance_limits(self.employee, as_of=timezone.localdate())
        self.assertEqual(limits["advances_this_cycle"], 2)
        self.assertEqual(limits["remaining_this_cycle"], 0)
        self.assertFalse(limits["eligible"])
        self.assertTrue(any("used all 2" in reason for reason in limits["reasons"]))

    def test_min_days_between_blocks_repeat_requests(self):
        self._add_advance("20000")  # created today
        blocked = ew_advance_limits(
            self.employee, as_of=timezone.localdate() + timedelta(days=3)
        )
        self.assertFalse(blocked["eligible"])
        self.assertTrue(
            any("next advance" in reason.lower() for reason in blocked["reasons"])
        )
        # After the waiting window the frequency rule no longer blocks.
        allowed = ew_advance_limits(
            self.employee, as_of=timezone.localdate() + timedelta(days=7)
        )
        self.assertTrue(allowed["eligible"])

    def test_net_pay_guardrail_binds_below_cycle_cap(self):
        # A 60,000 outstanding advance from a prior cycle leaves 40,000 of
        # headroom against the 50% take-home floor (100,000) - which binds
        # below the 50,000 earned-pay cap.
        self._add_advance("60000", created=date(2026, 5, 1))
        limits = ew_advance_limits(self.employee, as_of=date(2026, 6, 15))
        self.assertEqual(limits["outstanding_total"], Decimal("60000.00"))
        self.assertEqual(limits["outstanding_in_cycle"], Decimal("0.00"))
        self.assertEqual(limits["guardrail_cap"], Decimal("40000.00"))
        self.assertEqual(limits["max_available"], Decimal("40000.00"))
        self.assertTrue(limits["eligible"])

    def test_ew_advance_ineligible_when_disabled(self):
        self.setting.ewa_enabled = False
        self.setting.save(update_fields=["ewa_enabled"])
        limits = ew_advance_limits(self.employee, as_of=date(2026, 6, 15))
        self.assertFalse(limits["enabled"])
        self.assertFalse(limits["eligible"])
        self.assertEqual(limits["max_available"], Decimal("0.00"))


class EWASelfServiceViewTests(TestCase):
    """The self-service EWA request flow enforces the rules engine."""

    def setUp(self):
        self.company = Company.objects.create(name="EWA View Co")
        self.user = get_user_model().objects.create_user(
            email="ewa-view@example.com",
            password="testpass123",
            first_name="Ewa",
            last_name="View",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.employee_pay = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("200000.00")
        )
        self.employee.save(update_fields=["company", "status", "employee_pay"])
        # The view reads net_pay from the DB; pin it for deterministic caps.
        EmployeeProfile.objects.filter(pk=self.employee.pk).update(
            net_pay=Decimal("200000.00")
        )
        CompanyPayrollSetting.objects.create(
            company=self.company, ewa_enabled=True
        )
        self.client.login(email=self.user.email, password="testpass123")

    def test_request_ewa_page_renders_limits(self):
        response = self.client.get(reverse("payroll:request_ewa"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "iou/request_ewa_new.html")
        self.assertContains(response, "Earned Wage Access")
        self.assertContains(response, "Maximum advance")

    def test_request_ewa_creates_advance_with_one_month_tenor(self):
        # 2,000 is below the smallest possible earned-pay cap (day 1 of any
        # month: 200,000 / 31 x 50%), so the test is date-independent.
        response = self.client.post(
            reverse("payroll:request_ewa"),
            data={"amount": "2000", "tenor": "5", "reason": "School fees"},
        )
        self.assertRedirects(
            response,
            reverse("payroll:iou_history"),
            fetch_redirect_response=False,
        )
        advance = IOU.objects.get(employee_id=self.employee)
        self.assertTrue(advance.is_ewa)
        self.assertEqual(advance.tenor, 1)

    def test_request_ewa_rejects_over_cap_amount(self):
        setting = CompanyPayrollSetting.objects.get(company=self.company)
        setting.ewa_advance_percent = Decimal("5.00")
        setting.save(update_fields=["ewa_advance_percent"])
        response = self.client.post(
            reverse("payroll:request_ewa"),
            data={"amount": "100000", "tenor": "1", "reason": "Too much"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot be more than")
        self.assertFalse(IOU.objects.filter(employee_id=self.employee).exists())

    def test_request_ewa_blocked_when_disabled(self):
        setting = CompanyPayrollSetting.objects.get(company=self.company)
        setting.ewa_enabled = False
        setting.save(update_fields=["ewa_enabled"])
        response = self.client.get(reverse("payroll:request_ewa"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not enabled for your company")


class AuditSignalCascadeDeleteTests(TestCase):
    """
    Audit signal handlers must never break cascade teardown.

    Deleting a User (or Company) tears down the employee and its children;
    ``post_delete`` handlers that resolve ``instance.user`` / ``instance.employee``
    previously raised ``DoesNotExist`` when the related row was already gone,
    crashing the delete. The hardened handlers resolve the audit user safely
    and always fall back to ``None``.
    """

    def setUp(self):
        self.company = Company.objects.create(name="Cascade Audit Co")
        self.user = get_user_model().objects.create_user(
            email="cascade-audit@example.com",
            password="testpass123",
            first_name="Cascade",
            last_name="Audit",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.employee_pay = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("120000.00")
        )
        self.employee.save(update_fields=["company", "status", "employee_pay"])
        Allowance.objects.create(
            employee=self.employee,
            allowance_type="transport",
            amount=Decimal("10000"),
        )
        LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date="2026-07-01",
            end_date="2026-07-10",
            status="PENDING",
            reason="family",
        )

    def test_user_cascade_delete_does_not_crash_audit_signals(self):
        # Deleting the owning user cascades to the employee and its children;
        # the post_delete audit handlers must not crash on the gone user row.
        self.user.delete()  # must not raise
        self.assertFalse(
            EmployeeProfile.objects.filter(pk=self.employee.pk).exists()
        )
        # The teardown is still audited (with user=None once the row is gone).
        self.assertTrue(
            AuditTrail.objects.filter(action="Deleted EmployeeProfile").exists()
        )

    def test_company_cascade_delete_does_not_crash_audit_signals(self):
        # Payroll.company is PROTECTed, so use a company without a salary
        # config: deleting it hard-deletes the employee and children via the
        # collector, and the audit handlers must still complete.
        company = Company.objects.create(name="Cascade Audit Co 2")
        user = get_user_model().objects.create_user(
            email="cascade-audit-2@example.com",
            password="testpass123",
            first_name="Cascade",
            last_name="Two",
            company=company,
            active_company=company,
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = company
        employee.status = "active"
        employee.save(update_fields=["company", "status"])
        Allowance.objects.create(
            employee=employee,
            allowance_type="transport",
            amount=Decimal("10000"),
        )

        company.delete()  # must not raise
        self.assertFalse(EmployeeProfile.objects.filter(pk=employee.pk).exists())

    def test_employee_delete_path_is_soft_and_does_not_crash(self):
        # The delete_employee view deletes the profile directly; EmployeeProfile
        # is a soft-delete model, so no post_delete fires - it must simply not
        # crash and mark the row deleted.
        self.employee.delete()  # must not raise
        self.assertIsNotNone(
            EmployeeProfile.all_objects.filter(pk=self.employee.pk)
            .values_list("deleted_at", flat=True)
            .first()
        )
