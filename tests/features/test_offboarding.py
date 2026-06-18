from django.test import TestCase
from django.contrib.auth import get_user_model
from payroll.models import EmployeeProfile
from payroll.models.workforce import OffboardingChecklist, OffboardingTask
from company.models import Company

User = get_user_model()


class OffboardingTest(TestCase):
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

    def test_initiate_offboarding_creates_checklist_with_tasks(self):
        from payroll.services.offboarding_service import initiate_offboarding
        checklist = initiate_offboarding(
            employee=self.employee,
            last_working_day="2026-07-15",
            reason="RESIGNATION",
            initiated_by=self.user,
        )
        self.assertEqual(checklist.status, "IN_PROGRESS")
        self.assertEqual(checklist.reason, "RESIGNATION")
        self.assertEqual(checklist.tasks.count(), 6)

    def test_complete_task(self):
        from payroll.services.offboarding_service import initiate_offboarding, complete_task
        checklist = initiate_offboarding(
            employee=self.employee,
            last_working_day="2026-07-15",
            reason="RESIGNATION",
            initiated_by=self.user,
        )
        task = checklist.tasks.first()
        complete_task(task=task, completed_by=self.user, notes="Done")
        task.refresh_from_db()
        self.assertTrue(task.is_completed)
        self.assertEqual(task.completed_by, self.user)

    def test_complete_offboarding_requires_all_tasks(self):
        from payroll.services.offboarding_service import initiate_offboarding, complete_offboarding
        checklist = initiate_offboarding(
            employee=self.employee,
            last_working_day="2026-07-15",
            reason="RESIGNATION",
            initiated_by=self.user,
        )
        with self.assertRaises(ValueError):
            complete_offboarding(checklist=checklist)

    def test_complete_offboarding_when_all_tasks_done(self):
        from payroll.services.offboarding_service import (
            initiate_offboarding, complete_task, complete_offboarding
        )
        checklist = initiate_offboarding(
            employee=self.employee,
            last_working_day="2026-07-15",
            reason="RESIGNATION",
            initiated_by=self.user,
        )
        for task in checklist.tasks.all():
            complete_task(task=task, completed_by=self.user)
        complete_offboarding(checklist=checklist)
        checklist.refresh_from_db()
        self.assertEqual(checklist.status, "COMPLETED")
        self.assertIsNotNone(checklist.completed_at)
