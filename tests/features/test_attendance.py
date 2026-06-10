from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from company.models import Company
from payroll.models import AttendanceRecord, LeaveRequest
from payroll.services.attendance import populate_attendance_for_leave


User = get_user_model()


class AttendanceFeatureTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Attendance Co")
        self.user = User.objects.create_user(
            email="attendance@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.first_name = "Present"
        self.employee.last_name = "Worker"
        self.employee.save(update_fields=["company", "first_name", "last_name"])

    def _grant(self, codename):
        permission = Permission.objects.get(
            content_type__app_label="payroll",
            codename=codename,
        )
        self.user.user_permissions.add(permission)

    def test_approved_leave_populates_weekday_attendance(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type="ANNUAL",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            reason="Rest",
            status="APPROVED",
            hr_override=True,
        )

        populate_attendance_for_leave(leave)

        self.assertEqual(
            AttendanceRecord.objects.filter(
                employee=self.employee,
                status=AttendanceRecord.Status.LEAVE,
            ).count(),
            5,
        )

    def test_employee_attendance_views_and_clock_flow(self):
        AttendanceRecord.objects.create(
            company=self.company,
            employee=self.employee,
            work_date=timezone.localdate(),
            status=AttendanceRecord.Status.ABSENT,
        )
        self._grant("view_employeeprofile")
        self.client.force_login(self.user)

        my_day = self.client.get(reverse("payroll:attendance_my_day"))
        clock = self.client.post(
            reverse("payroll:attendance_clock"),
            {"action": "clock_in"},
        )
        overview = self.client.get(reverse("payroll:attendance_overview"))
        who_is_out = self.client.get(reverse("payroll:who_is_out"))

        self.assertEqual(my_day.status_code, 200)
        self.assertEqual(clock.status_code, 302)
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(who_is_out.status_code, 200)
        self.assertTrue(
            AttendanceRecord.objects.filter(
                employee=self.employee,
                work_date=timezone.localdate(),
                status=AttendanceRecord.Status.PRESENT,
            ).exists()
        )
