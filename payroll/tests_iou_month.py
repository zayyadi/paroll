from datetime import date
from decimal import Decimal

from django.test import TestCase
from monthyear import Month

from company.models import Company
from payroll.models import EmployeeProfile, IOUDeduction, IOU, Payroll, PayrollEntry, PayrollRunEntry, PayrollRun


class IOUPayrollEntryMonthSignalTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Paroll Nigeria Demo Ltd")
        self.payroll = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal("100000"),
        )
        self.employee = EmployeeProfile.objects.create(
            company=self.company,
            first_name="Ngozi",
            last_name="Okonkwo",
            email="ngozi.okonkwo@example.ng",
            employee_pay=self.payroll,
            net_pay=Decimal("100000"),
            status="active",
        )
        self.payroll_entry = PayrollEntry.objects.create(
            company=self.company,
            pays=self.employee,
            status="active",
        )
        self.iou = IOU.objects.create(
            employee_id=self.employee,
            amount=Decimal("10000"),
            tenor=3,
            repayment_deduction_percentage=Decimal("30.00"),
            interest_rate=Decimal("0.00"),
            payment_method="SALARY_DEDUCTION",
            status="APPROVED",
            approved_at=date(2026, 1, 1),
        )

    def test_payroll_entry_signal_handles_month_object(self):
        payroll_run = PayrollRun.objects.create(
            company=self.company,
            name="Payroll 2026-02",
            paydays=date(2026, 2, 1),
        )
        payroll_run.refresh_from_db()

        self.assertIsInstance(payroll_run.paydays, Month)

        PayrollRunEntry.objects.create(
            payroll_run=payroll_run,
            payroll_entry=self.payroll_entry,
        )

        deduction = IOUDeduction.objects.get(iou=self.iou, payday=payroll_run)
        self.assertEqual(deduction.amount, Decimal("10000"))
        self.iou.refresh_from_db()
        self.assertEqual(self.iou.status, "PAID")
