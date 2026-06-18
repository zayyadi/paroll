from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import datetime
from payroll.models import EmployeeProfile
from payroll.models.workforce import OvertimePolicy, OvertimeEntry, AttendanceRecord
from company.models import Company

User = get_user_model()


class OvertimePolicyTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        self.user = User.objects.create_user(
            email="hr@test.com", password="testpass123", is_staff=True
        )
        self.user.active_company = self.company
        self.user.save()
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.first_name = "John"
        self.employee.last_name = "Doe"
        self.employee.save()
        self.policy = OvertimePolicy.objects.create(
            company=self.company,
            daily_threshold_hours=Decimal("8.00"),
            weekday_rate_multiplier=Decimal("1.50"),
            weekend_rate_multiplier=Decimal("2.00"),
            max_daily_overtime_hours=Decimal("4.00"),
            requires_approval=True,
        )

    def test_overtime_calculated_when_exceeding_threshold(self):
        from payroll.services.overtime_service import calculate_overtime_for_attendance
        attendance = AttendanceRecord.objects.create(
            company=self.company, employee=self.employee,
            work_date="2026-06-10", status="Present",
            clock_in=datetime(2026, 6, 10, 9, 0),
            clock_out=datetime(2026, 6, 10, 19, 0),
            hours_worked=Decimal("10.00"),
        )
        entry = calculate_overtime_for_attendance(attendance=attendance)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.hours, Decimal("2.00"))
        self.assertEqual(entry.rate_multiplier, Decimal("1.50"))
        self.assertEqual(entry.status, "PENDING")

    def test_no_overtime_when_below_threshold(self):
        from payroll.services.overtime_service import calculate_overtime_for_attendance
        attendance = AttendanceRecord.objects.create(
            company=self.company, employee=self.employee,
            work_date="2026-06-10", status="Present",
            clock_in=datetime(2026, 6, 10, 9, 0),
            clock_out=datetime(2026, 6, 10, 17, 0),
            hours_worked=Decimal("8.00"),
        )
        entry = calculate_overtime_for_attendance(attendance=attendance)
        self.assertIsNone(entry)

    def test_weekend_rate_multiplier(self):
        from payroll.services.overtime_service import calculate_overtime_for_attendance
        attendance = AttendanceRecord.objects.create(
            company=self.company, employee=self.employee,
            work_date="2026-06-14", status="Present",
            clock_in=datetime(2026, 6, 14, 8, 0),
            clock_out=datetime(2026, 6, 14, 18, 0),
            hours_worked=Decimal("10.00"),
        )
        entry = calculate_overtime_for_attendance(attendance=attendance)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.rate_multiplier, Decimal("2.00"))

    def test_max_daily_overtime_cap(self):
        from payroll.services.overtime_service import calculate_overtime_for_attendance
        attendance = AttendanceRecord.objects.create(
            company=self.company, employee=self.employee,
            work_date="2026-06-10", status="Present",
            clock_in=datetime(2026, 6, 10, 6, 0),
            clock_out=datetime(2026, 6, 10, 22, 0),
            hours_worked=Decimal("16.00"),
        )
        entry = calculate_overtime_for_attendance(attendance=attendance)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.hours, Decimal("4.00"))

    def test_approve_overtime(self):
        from payroll.services.overtime_service import approve_overtime
        entry = OvertimeEntry.objects.create(
            company=self.company, employee=self.employee,
            date="2026-06-10", hours=Decimal("2.00"),
            rate_multiplier=Decimal("1.50"),
        )
        approve_overtime(entry=entry, approved_by=self.user)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "APPROVED")
        self.assertEqual(entry.approved_by, self.user)
