from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from unittest.mock import patch

from company.models import Company
from accounting.models import DisciplinaryCase, DisciplinarySanction
from payroll.forms import PayrollRunCreateForm
from payroll.models import (
    CompanyPayrollSetting,
    EmployeeProfile,
    LeaveRequest,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
    Appraisal,
    AppraisalAssignment,
    Review,
    Rating,
    Metric,
)
from payroll.views.payroll_view import _send_payslips_for_payroll_run

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

        # 15% of monthly basic salary (120,000) = 18,000
        self.assertEqual(payroll_entry.calc_allowance, Decimal("18000.00"))

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

        # December leave allowance (15%) + 13th month (20% annual) = 306,000
        self.assertEqual(payroll_entry.calc_allowance, Decimal("306000.00"))
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
        self.employee.save(update_fields=["company", "status"])

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
    @patch("payroll.views.payroll_view.custom_send_mail")
    @patch("payroll.views.payroll_view.generate_payslip_pdf")
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
        self.assertEqual(skipped_count, 0)
        self.assertEqual(mocked_send_mail.call_count, 1)
        kwargs = mocked_send_mail.call_args.kwargs
        self.assertEqual(kwargs["recipient_list"], [user.email])
        self.assertEqual(kwargs["template_name"], "email/payslip_email.html")
        self.assertTrue(kwargs["attachments"])
