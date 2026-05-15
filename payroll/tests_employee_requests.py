from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from company.models import Company
from payroll.models import (
    Allowance,
    CompanyPayrollSetting,
    EmployeeProfile,
    IOU,
    LeaveBalance,
    LeaveRequest,
    Payroll,
)


User = get_user_model()


class EmployeeRequestAccessTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Request Co")
        self.payroll = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("200000.00"),
        )
        CompanyPayrollSetting.objects.create(
            company=self.company,
            leave_allowance_percentage=Decimal("10.00"),
        )
        self.employee_user = User.objects.create_user(
            email="employee-requests@test.com",
            password="password123",
            first_name="Employee",
            last_name="Requester",
            company=self.company,
            active_company=self.company,
        )
        self.employee = self.employee_user.employee_user
        self.employee.company = self.company
        self.employee.employee_pay = self.payroll
        self.employee.net_pay = Decimal("150000.00")
        self.employee.save(update_fields=["company", "employee_pay", "net_pay"])

        self.manager_user = User.objects.create_user(
            email="manager-requests@test.com",
            password="password123",
            first_name="Manager",
            last_name="Approver",
            company=self.company,
            active_company=self.company,
            is_manager=True,
        )
        self.manager = self.manager_user.employee_user
        self.manager.company = self.company
        self.manager.save(update_fields=["company"])

        self.other_user = User.objects.create_user(
            email="other-requests@test.com",
            password="password123",
            first_name="Other",
            last_name="Employee",
            company=self.company,
            active_company=self.company,
        )
        self.other_employee = self.other_user.employee_user
        self.other_employee.company = self.company
        self.other_employee.employee_pay = self.payroll
        self.other_employee.save(update_fields=["company", "employee_pay"])

        self.staff_user = User.objects.create_user(
            email="staff-requests@test.com",
            password="password123",
            first_name="Staff",
            last_name="NotApprover",
            company=self.company,
            active_company=self.company,
            is_staff=True,
        )
        self.staff_employee = self.staff_user.employee_user
        self.staff_employee.company = self.company
        self.staff_employee.save(update_fields=["company"])

    def test_employee_without_model_permission_can_submit_leave_request(self):
        self.client.force_login(self.employee_user)

        response = self.client.post(
            reverse("payroll:apply_leave"),
            {
                "leave_type": "ANNUAL",
                "start_date": "2026-06-01",
                "end_date": "2026-06-02",
                "reason": "Family event",
            },
        )

        self.assertRedirects(response, reverse("payroll:leave_requests"))
        request = LeaveRequest.objects.get(employee=self.employee)
        self.assertEqual(request.status, "PENDING")
        self.assertEqual(request.reason, "Family event")

    def test_employee_tracks_only_their_own_leave_requests(self):
        own_request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            reason="Own request",
        )
        LeaveRequest.objects.create(
            employee=self.other_employee,
            leave_type="SICK",
            start_date=date(2026, 7, 2),
            end_date=date(2026, 7, 2),
            reason="Other request",
        )

        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("payroll:leave_requests"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_request.reason)
        self.assertNotContains(response, "Other request")

    def test_employee_can_edit_own_pending_leave_request(self):
        request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
            reason="Original reason",
        )

        self.client.force_login(self.employee_user)
        response = self.client.post(
            reverse("payroll:edit_leave_request", args=[request.pk]),
            {
                "leave_type": "ANNUAL",
                "start_date": "2026-07-10",
                "end_date": "2026-07-11",
                "reason": "Updated reason",
            },
        )

        self.assertRedirects(response, reverse("payroll:leave_requests"))
        request.refresh_from_db()
        self.assertEqual(request.reason, "Updated reason")
        self.assertEqual(request.end_date, date(2026, 7, 11))
        self.assertEqual(request.status, "PENDING")

    def test_employee_can_view_approved_leave_allowance_slip(self):
        request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 7, 15),
            end_date=date(2026, 7, 15),
            reason="Approved allowance",
            status="APPROVED",
        )
        allowance = Allowance.objects.get(source_leave_request=request)

        self.client.force_login(self.employee_user)
        response = self.client.get(
            reverse("payroll:leave_allowance_slip", args=[allowance.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leave Allowance Slip")
        self.assertContains(response, "Approved allowance")
        self.assertContains(response, "₦20,000.00")

    def test_employee_cannot_view_another_employee_leave_allowance_slip(self):
        request = LeaveRequest.objects.create(
            employee=self.other_employee,
            leave_type="ANNUAL",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 20),
            reason="Other allowance",
            status="APPROVED",
        )
        allowance = Allowance.objects.get(source_leave_request=request)

        self.client.force_login(self.employee_user)
        response = self.client.get(
            reverse("payroll:leave_allowance_slip", args=[allowance.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_regular_employee_cannot_approve_leave_request(self):
        request = LeaveRequest.objects.create(
            employee=self.other_employee,
            leave_type="ANNUAL",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            reason="Needs approval",
        )

        self.client.force_login(self.employee_user)
        response = self.client.post(reverse("payroll:approve_leave", args=[request.pk]))

        self.assertEqual(response.status_code, 403)
        request.refresh_from_db()
        self.assertEqual(request.status, "PENDING")

    def test_staff_without_request_permission_cannot_approve_leave_request(self):
        request = LeaveRequest.objects.create(
            employee=self.other_employee,
            leave_type="ANNUAL",
            start_date=date(2026, 8, 3),
            end_date=date(2026, 8, 3),
            reason="Staff should not approve",
        )

        self.client.force_login(self.staff_user)
        response = self.client.post(reverse("payroll:approve_leave", args=[request.pk]))

        self.assertEqual(response.status_code, 403)
        request.refresh_from_db()
        self.assertEqual(request.status, "PENDING")

    def test_manager_can_review_and_approve_leave_requests(self):
        request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 1),
            reason="Manager approval",
        )

        self.client.force_login(self.manager_user)
        list_response = self.client.get(reverse("payroll:manage_leave_requests"))
        approve_response = self.client.post(
            reverse("payroll:approve_leave", args=[request.pk])
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Manager approval")
        self.assertRedirects(approve_response, reverse("payroll:manage_leave_requests"))
        request.refresh_from_db()
        self.assertEqual(request.status, "APPROVED")
        self.assertEqual(request.approved_by, self.manager_user)

    def test_approval_failure_for_insufficient_leave_balance_returns_to_manage_page(self):
        LeaveBalance.objects.create(
            employee=self.employee,
            year=2026,
            annual_leave=0,
            sick_leave=10,
            casual_leave=7,
            maternity_leave=90,
            paternity_leave=14,
        )
        request = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 5),
            reason="No balance available",
        )

        self.client.force_login(self.manager_user)
        response = self.client.post(
            reverse("payroll:approve_leave", args=[request.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse("payroll:manage_leave_requests"))
        self.assertContains(response, "Insufficient annual leave balance.")
        request.refresh_from_db()
        self.assertEqual(request.status, "PENDING")
        self.assertIsNone(request.approved_by)

    def test_employee_without_model_permission_can_submit_iou_request(self):
        self.client.force_login(self.employee_user)

        response = self.client.post(
            reverse("payroll:request_iou"),
            {
                "amount": "50000.00",
                "tenor": "3",
                "reason": "Emergency expense",
            },
        )

        self.assertRedirects(response, reverse("payroll:iou_history"))
        iou = IOU.objects.get(employee_id=self.employee)
        self.assertEqual(iou.status, "PENDING")
        self.assertEqual(iou.reason, "Emergency expense")

    def test_employee_can_track_only_their_own_iou_requests(self):
        own_iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal("20000.00"),
            tenor=2,
            reason="Own IOU",
        )
        IOU.objects.create(
            employee_id=self.other_employee,
            amount=Decimal("30000.00"),
            tenor=2,
            reason="Other IOU",
        )

        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("payroll:iou_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_iou.reason)
        self.assertNotContains(response, "Other IOU")

    def test_regular_employee_cannot_approve_iou_request(self):
        iou = IOU.objects.create(
            employee_id=self.other_employee,
            amount=Decimal("35000.00"),
            tenor=3,
            reason="Needs IOU approval",
        )

        self.client.force_login(self.employee_user)
        response = self.client.post(
            reverse("payroll:approve_iou", args=[iou.pk]),
            {
                "status": "APPROVED",
                "approved_at": "2026-05-02",
                "tenor": "3",
                "repayment_deduction_percentage": "25.00",
            },
        )

        self.assertEqual(response.status_code, 403)
        iou.refresh_from_db()
        self.assertEqual(iou.status, "PENDING")

    def test_manager_can_approve_iou_request(self):
        iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal("35000.00"),
            tenor=3,
            reason="Manager IOU approval",
        )

        self.client.force_login(self.manager_user)
        response = self.client.post(
            reverse("payroll:approve_iou", args=[iou.pk]),
            {
                "status": "APPROVED",
                "approved_at": "2026-05-02",
                "tenor": "3",
                "repayment_deduction_percentage": "25.00",
            },
        )

        self.assertRedirects(response, reverse("payroll:iou_history"))
        iou.refresh_from_db()
        self.assertEqual(iou.status, "APPROVED")
