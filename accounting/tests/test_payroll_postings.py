from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from django.test import TestCase

from accounting.models import Account, Journal
from accounting.utils import create_journal_with_entries
from company.models import Company
from payroll.models import (
    Allowance,
    Deduction,
    EmployeeProfile,
    IOU,
    IOUDeduction,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
)
from users.models import CustomUser


class PayrollClosePostingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Payroll Co")
        self.cash_account, _ = Account.objects.get_or_create(
            account_number="1100",
            defaults={
                "name": "Cash and Cash Equivalents",
                "type": Account.AccountType.ASSET,
            },
        )
        self.employee_advances_account, _ = Account.objects.get_or_create(
            account_number="1400",
            defaults={
                "name": "Employee Advances",
                "type": Account.AccountType.ASSET,
            },
        )
        self.opening_equity_account, _ = Account.objects.get_or_create(
            account_number="3000",
            defaults={
                "name": "Opening Balance Equity",
                "type": Account.AccountType.EQUITY,
            },
        )

        # Seed opening balances so payroll-close asset credits pass balance validation.
        create_journal_with_entries(
            date=date.today().replace(day=1),
            description="Opening balances for payroll posting tests",
            entries=[
                {
                    "account": self.cash_account,
                    "entry_type": "DEBIT",
                    "amount": Decimal("1000000.00"),
                    "memo": "Opening cash",
                },
                {
                    "account": self.employee_advances_account,
                    "entry_type": "DEBIT",
                    "amount": Decimal("1000000.00"),
                    "memo": "Opening employee advances",
                },
                {
                    "account": self.opening_equity_account,
                    "entry_type": "CREDIT",
                    "amount": Decimal("2000000.00"),
                    "memo": "Opening balance offset",
                },
            ],
            auto_post=True,
        )

    def _q(self, amount):
        return Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _create_employee_stack(self, basic_salary="50000.00", housing=True, nhif=True):
        user = CustomUser.objects.create_user(
            email=f"tester-{CustomUser.objects.count()+1}@example.com",
            password="secret123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )

        payroll = Payroll.objects.create(
            company=self.company,
            basic_salary=Decimal(basic_salary),
            is_housing=housing,
            is_nhif=nhif,
        )

        # EmployeeProfile is auto-created by CustomUser post_save signal.
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = self.company
        employee.first_name = "Ada"
        employee.last_name = "Lovelace"
        employee.slug = f"ada-lovelace-{employee.pk}"
        employee.employee_pay = payroll
        employee.status = "active"
        employee.save()

        entry = PayrollEntry.objects.create(
            company=self.company,
            pays=employee,
            status="active",
        )
        return payroll, employee, entry

    def _close_run_and_get_journal(self, entry):
        payroll_date = date.today().replace(day=1)
        run = PayrollRun.objects.create(
            company=self.company,
            name=f"Period {payroll_date:%Y-%m}",
            paydays=payroll_date,
            is_active=True,
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        run.closed = True
        run.save()

        run_ct = ContentType.objects.get_for_model(PayrollRun)
        return Journal.objects.get(content_type=run_ct, object_id=run.pk), run

    def test_close_payroll_posts_balanced_journal(self):
        _, employee, entry = self._create_employee_stack()
        journal, _ = self._close_run_and_get_journal(entry)

        self.assertEqual(journal.status, Journal.JournalStatus.POSTED)

        debits = (
            journal.entries.filter(entry_type="DEBIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or Decimal("0.00")
        )
        credits = (
            journal.entries.filter(entry_type="CREDIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or Decimal("0.00")
        )
        self.assertEqual(self._q(debits), self._q(credits))

        cash_credit = (
            journal.entries.filter(account__account_number="1100", entry_type="CREDIT")
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )
        self.assertEqual(self._q(cash_credit), self._q(entry.netpay))

        salary_debit = (
            journal.entries.filter(account__account_number="6010", entry_type="DEBIT")
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )
        expected_salary_debit = (
            Decimal(entry.netpay)
            + Decimal(employee.employee_pay.payee or 0)
            + (Decimal(employee.employee_pay.pension_employee or 0) / Decimal("12"))
            + (Decimal(employee.employee_pay.nhf or 0) / Decimal("12"))
            + (Decimal(employee.employee_pay.employee_health or 0) / Decimal("12"))
        )
        self.assertEqual(self._q(salary_debit), self._q(expected_salary_debit))

    def test_close_payroll_maps_iou_and_other_deductions_to_liabilities(self):
        _, employee, entry = self._create_employee_stack()

        Allowance.objects.create(employee=employee, amount=Decimal("1000.00"))
        Deduction.objects.create(
            employee=employee,
            deduction_type="MISC",
            amount=Decimal("500.00"),
        )
        iou = IOU.objects.create(employee_id=employee, amount=Decimal("1200.00"), tenor=3)

        payroll_date = date.today().replace(day=1)
        run = PayrollRun.objects.create(
            company=self.company,
            name=f"Period {payroll_date:%Y-%m} DED",
            paydays=payroll_date,
            is_active=True,
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        IOUDeduction.objects.create(
            iou=iou,
            employee=employee,
            payday=run,
            amount=Decimal("250.00"),
        )

        # Refresh to include allowance/deduction effects in netpay before close.
        entry.save()
        run.closed = True
        run.save()

        run_ct = ContentType.objects.get_for_model(PayrollRun)
        journal = Journal.objects.get(content_type=run_ct, object_id=run.pk)

        other_ded_credit = (
            journal.entries.filter(account__account_number="2160", entry_type="CREDIT")
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )
        iou_recovery_credit = (
            journal.entries.filter(account__account_number="1400", entry_type="CREDIT")
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )

        self.assertEqual(self._q(other_ded_credit), Decimal("500.00"))
        self.assertEqual(self._q(iou_recovery_credit), Decimal("250.00"))
