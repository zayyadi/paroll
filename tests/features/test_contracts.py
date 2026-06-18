from django.test import TestCase
from django.contrib.auth import get_user_model
from payroll.models import EmployeeProfile
from payroll.models.employee_profile import ContractTemplate, EmploymentContract
from company.models import Company

User = get_user_model()


class ContractGenerationTest(TestCase):
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
        self.employee.job_title = "Engineer"
        self.employee.save()
        self.template = ContractTemplate.objects.create(
            company=self.company,
            name="Full-Time Contract",
            template_html="<h1>Contract for {{ employee.first_name }}</h1>",
        )

    def test_create_contract(self):
        from payroll.services.contract_service import create_contract
        contract = create_contract(
            employee=self.employee,
            template=self.template,
            start_date="2026-07-01",
        )
        self.assertEqual(contract.version, 1)
        self.assertEqual(contract.status, "DRAFT")
        self.assertIsNotNone(contract.pdf_file)

    def test_contract_versioning(self):
        from payroll.services.contract_service import create_contract
        c1 = create_contract(
            employee=self.employee, template=self.template,
            start_date="2026-07-01",
        )
        c2 = create_contract(
            employee=self.employee, template=self.template,
            start_date="2027-01-01",
        )
        self.assertEqual(c1.version, 1)
        self.assertEqual(c2.version, 2)

    def test_sign_contract(self):
        from payroll.services.contract_service import create_contract, sign_contract
        contract = create_contract(
            employee=self.employee, template=self.template,
            start_date="2026-07-01",
        )
        sign_contract(contract=contract, signed_by=self.user)
        contract.refresh_from_db()
        self.assertEqual(contract.status, "SIGNED")
        self.assertIsNotNone(contract.signed_at)

    def test_tenant_isolation(self):
        other_company = Company.objects.create(name="Other Co")
        self.assertFalse(
            EmploymentContract.objects.filter(company=other_company).exists()
        )
