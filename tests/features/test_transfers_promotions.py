from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from payroll.models import EmployeeProfile, Department, EmployeeTransfer, Promotion
from company.models import Company

User = get_user_model()


class EmployeeTransferTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        self.user = User.objects.create_user(
            email="hr@test.com", password="testpass123", is_staff=True
        )
        self.user.active_company = self.company
        self.user.save()
        self.dept_a = Department.objects.create(company=self.company, name="Engineering")
        self.dept_b = Department.objects.create(company=self.company, name="Marketing")
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.first_name = "John"
        self.employee.last_name = "Doe"
        self.employee.department = self.dept_a
        self.employee.job_title = "Engineer"
        self.employee.save()
        self.client = Client()
        self.client.login(email="hr@test.com", password="testpass123")

    def test_create_transfer(self):
        transfer = EmployeeTransfer.objects.create(
            company=self.company,
            employee=self.employee,
            from_department=self.dept_a,
            to_department=self.dept_b,
            from_position="Engineer",
            to_position="Marketing Lead",
            effective_date="2026-07-01",
            reason="Career change",
            requested_by=self.user,
        )
        self.assertEqual(transfer.status, "PENDING")
        self.assertEqual(transfer.to_department, self.dept_b)

    def test_approve_transfer_updates_employee(self):
        transfer = EmployeeTransfer.objects.create(
            company=self.company,
            employee=self.employee,
            from_department=self.dept_a,
            to_department=self.dept_b,
            to_position="Marketing Lead",
            effective_date="2026-07-01",
            requested_by=self.user,
        )
        from payroll.services.transfer_service import approve_transfer, execute_transfer
        approve_transfer(transfer=transfer, approved_by=self.user)
        self.assertEqual(transfer.status, "APPROVED")
        execute_transfer(transfer=transfer, performed_by=self.user)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department, self.dept_b)
        self.assertEqual(self.employee.job_title, "Marketing Lead")
        self.assertEqual(transfer.status, "COMPLETED")

    def test_reject_transfer(self):
        transfer = EmployeeTransfer.objects.create(
            company=self.company, employee=self.employee,
            to_department=self.dept_b, effective_date="2026-07-01",
            requested_by=self.user,
        )
        from payroll.services.transfer_service import reject_transfer
        reject_transfer(transfer=transfer, approved_by=self.user)
        self.assertEqual(transfer.status, "REJECTED")


class PromotionTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        self.user = User.objects.create_user(
            email="hr@test.com", password="testpass123", is_staff=True
        )
        self.user.active_company = self.company
        self.user.save()
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.first_name = "Jane"
        self.employee.last_name = "Smith"
        self.employee.job_title = "Engineer"
        self.employee.save()

    def test_create_promotion(self):
        promotion = Promotion.objects.create(
            company=self.company, employee=self.employee,
            old_title="Engineer", new_title="Senior Engineer",
            effective_date="2026-07-01", requested_by=self.user,
        )
        self.assertEqual(promotion.status, "PENDING")

    def test_approve_promotion_updates_employee(self):
        promotion = Promotion.objects.create(
            company=self.company, employee=self.employee,
            old_title="Engineer", new_title="Senior Engineer",
            effective_date="2026-07-01", requested_by=self.user,
        )
        from payroll.services.transfer_service import approve_promotion, execute_promotion
        approve_promotion(promotion=promotion, approved_by=self.user)
        execute_promotion(promotion=promotion, performed_by=self.user)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.job_title, "Senior Engineer")
        self.assertEqual(promotion.status, "COMPLETED")

    def test_tenant_isolation(self):
        other_company = Company.objects.create(name="Other Co")
        transfer = EmployeeTransfer.objects.create(
            company=self.company, employee=self.employee,
            effective_date="2026-07-01",
        )
        self.assertFalse(
            EmployeeTransfer.objects.filter(company=other_company).exists()
        )
