from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import time
from payroll.models import EmployeeProfile
from payroll.models.workforce import Shift, ShiftTemplate, ShiftAssignment
from company.models import Company

User = get_user_model()


class ShiftSchedulingTest(TestCase):
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
        self.morning = Shift.objects.create(
            company=self.company, name="Morning",
            start_time=time(9, 0), end_time=time(17, 0),
        )
        self.evening = Shift.objects.create(
            company=self.company, name="Evening",
            start_time=time(14, 0), end_time=time(22, 0),
        )

    def test_create_shift(self):
        self.assertEqual(self.morning.name, "Morning")
        self.assertEqual(self.morning.start_time, time(9, 0))

    def test_create_template(self):
        template = ShiftTemplate.objects.create(
            company=self.company, name="Standard Week",
            monday=self.morning, tuesday=self.morning,
            wednesday=self.morning, thursday=self.morning,
            friday=self.morning,
        )
        from datetime import date
        monday = date(2026, 6, 15)
        shift = template.get_shift_for_day(monday)
        self.assertEqual(shift, self.morning)

    def test_create_assignment(self):
        from datetime import date
        template = ShiftTemplate.objects.create(
            company=self.company, name="Standard Week",
            monday=self.morning,
        )
        assignment = ShiftAssignment.objects.create(
            company=self.company, employee=self.employee,
            shift_template=template, effective_from=date(2026, 6, 1),
        )
        self.assertEqual(assignment.shift_template, template)
        self.assertEqual(assignment.employee, self.employee)

    def test_tenant_isolation(self):
        other_company = Company.objects.create(name="Other Co")
        self.assertFalse(
            Shift.objects.filter(company=other_company).exists()
        )
