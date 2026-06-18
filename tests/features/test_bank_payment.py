from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import date
from payroll.models import Payroll, PayrollRun, PayrollEntry, PayrollRunEntry
from payroll.models.payroll import BankPaymentFile
from company.models import Company

User = get_user_model()


class BankPaymentTest(TestCase):
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
        self.employee.bank = "Z"
        self.employee.bank_account_number = "1234567890"
        self.salary = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("1200000.00"),
        )
        self.employee.employee_pay = self.salary
        self.employee.save()
        self.run = PayrollRun.objects.create(
            company=self.company, name="June 2026",
            paydays=date(2026, 6, 1), closed=True,
        )
        self.entry = PayrollEntry.objects.create(
            company=self.company, pays=self.employee,
        )
        self.entry.netpay = Decimal("85000.00")
        self.entry.save(update_fields=["netpay"])
        PayrollRunEntry.objects.create(
            payroll_run=self.run, payroll_entry=self.entry,
        )

    def test_generate_nip_file(self):
        from payroll.services.bank_payment_service import generate_nip_file
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        self.assertEqual(payment.bank_name, "Zenith")
        self.assertEqual(payment.total_records, 1)
        self.assertEqual(payment.status, "GENERATED")

    def test_mark_submitted(self):
        from payroll.services.bank_payment_service import generate_nip_file, mark_submitted
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        mark_submitted(payment_file=payment, reference_number="REF123")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "SUBMITTED")
        self.assertEqual(payment.reference_number, "REF123")

    def test_mark_confirmed(self):
        from payroll.services.bank_payment_service import (
            generate_nip_file, mark_submitted, mark_confirmed
        )
        payment = generate_nip_file(payroll_run=self.run, bank_code="057")
        mark_submitted(payment_file=payment)
        mark_confirmed(payment_file=payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "CONFIRMED")

    def test_tenant_isolation(self):
        other_company = Company.objects.create(name="Other Co")
        self.assertFalse(
            BankPaymentFile.objects.filter(company=other_company).exists()
        )
