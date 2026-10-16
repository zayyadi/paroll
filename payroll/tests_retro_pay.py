"""Tests for retroactive pay deltas (P1-5).

Gap #5 of docs/world_class_employee_management_research_2026-10-14.md: a backdated
salary change produces a delta in the current period, with an audit trail and a
matching negative entry if reversed.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from company.models import Company
from payroll.models import (
    Allowance,
    EmployeeProfile,
    Payroll,
    RetroPayDelta,
)
from payroll.services import retro_pay_service as retro


class RetroPayFixture(TestCase):
    """One employee whose salary is raised from 100k to 120k basic."""

    OLD_BASIC = Decimal("100000.00")
    NEW_BASIC = Decimal("120000.00")
    EFFECTIVE = date(2026, 4, 15)  # backdated into April
    CATCHUP_PERIOD = date(2026, 6, 1)  # paid in the June run

    def setUp(self):
        self.company = Company.objects.create(name="Retro Pay Co")
        user = get_user_model().objects.create_user(
            email="retro@example.com",
            password="password123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.save()

        self.old_config = Payroll.objects.create(
            company=self.company, basic_salary=self.OLD_BASIC
        )
        self.new_config = Payroll.objects.create(
            company=self.company, basic_salary=self.NEW_BASIC
        )
        # Employee is on the NEW config (the raise is already applied).
        self.employee.employee_pay = self.new_config
        self.employee.save()


class ComputeDeltaTests(RetroPayFixture):
    def test_delta_is_monthly_difference_times_months(self):
        computed = retro.compute_retro_delta(
            self.old_config,
            self.new_config,
            effective_date=self.EFFECTIVE,
            period=self.CATCHUP_PERIOD,
        )
        # April 15 -> June 1 = 2 whole months (May, June).
        self.assertEqual(computed["months_owed"], 2)
        old_monthly = retro.monthly_net_for(self.old_config)
        new_monthly = retro.monthly_net_for(self.new_config)
        self.assertEqual(
            computed["monthly_delta"], (new_monthly - old_monthly).quantize(Decimal("0.01"))
        )
        self.assertEqual(
            computed["total_delta"],
            (computed["monthly_delta"] * 2).quantize(Decimal("0.01")),
        )

    def test_same_month_change_owes_nothing(self):
        computed = retro.compute_retro_delta(
            self.old_config,
            self.new_config,
            effective_date=date(2026, 6, 10),
            period=self.CATCHUP_PERIOD,
        )
        self.assertEqual(computed["months_owed"], 0)
        self.assertEqual(computed["total_delta"], Decimal("0.00"))

    def test_future_change_owes_nothing(self):
        computed = retro.compute_retro_delta(
            self.old_config,
            self.new_config,
            effective_date=date(2026, 8, 1),
            period=self.CATCHUP_PERIOD,
        )
        self.assertEqual(computed["months_owed"], 0)

    def test_downgrade_claws_back_nothing(self):
        computed = retro.compute_retro_delta(
            self.new_config,
            self.old_config,
            effective_date=self.EFFECTIVE,
            period=self.CATCHUP_PERIOD,
        )
        self.assertEqual(computed["monthly_delta"], Decimal("0.00"))
        self.assertEqual(computed["total_delta"], Decimal("0.00"))


class ApplyDeltaTests(RetroPayFixture):
    def _apply(self):
        return retro.apply_retro_delta(
            employee=self.employee,
            from_config=self.old_config,
            to_config=self.new_config,
            effective_date=self.EFFECTIVE,
            period=self.CATCHUP_PERIOD,
        )

    def test_apply_creates_audit_row_and_allowance(self):
        delta = self._apply()
        self.assertEqual(delta.status, RetroPayDelta.Status.APPLIED)
        self.assertEqual(delta.months_owed, 2)
        self.assertIsNotNone(delta.allowance_id)
        allowance = delta.allowance
        self.assertEqual(allowance.employee, self.employee)
        self.assertEqual(allowance.allowance_type, "Retro")
        self.assertEqual(allowance.amount, delta.total_delta)

    def test_apply_requires_current_config(self):
        # Bypass the EmployeeProfile.save() guard; fixture setup only.
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE payroll_employeeprofile SET employee_pay_id = %s "
                "WHERE id = %s",
                [self.old_config.pk, self.employee.pk],
            )
        self.employee.refresh_from_db()
        with self.assertRaises(ValidationError):
            retro.apply_retro_delta(
                employee=self.employee,
                from_config=self.old_config,
                to_config=self.new_config,
                effective_date=self.EFFECTIVE,
                period=self.CATCHUP_PERIOD,
            )

    def test_apply_rejects_zero_delta(self):
        with self.assertRaises(ValidationError):
            retro.apply_retro_delta(
                employee=self.employee,
                from_config=self.new_config,
                to_config=self.new_config,
                effective_date=self.EFFECTIVE,
                period=self.CATCHUP_PERIOD,
            )


class ReverseDeltaTests(RetroPayFixture):
    def _apply(self):
        return retro.apply_retro_delta(
            employee=self.employee,
            from_config=self.old_config,
            to_config=self.new_config,
            effective_date=self.EFFECTIVE,
            period=self.CATCHUP_PERIOD,
        )

    def test_reverse_records_negative_and_neutralises_allowance(self):
        delta = self._apply()
        original_amount = delta.total_delta
        reversal = retro.reverse_retro_delta(delta)
        self.assertEqual(reversal.total_delta, -original_amount)
        self.assertEqual(reversal.status, RetroPayDelta.Status.REVERSED)
        delta.refresh_from_db()
        self.assertEqual(delta.status, RetroPayDelta.Status.REVERSED)
        delta.allowance.refresh_from_db()
        self.assertEqual(delta.allowance.amount, Decimal("0.00"))

    def test_reverse_only_applied_deltas(self):
        delta = self._apply()
        retro.reverse_retro_delta(delta)
        with self.assertRaises(ValidationError):
            retro.reverse_retro_delta(delta)

    def test_audit_is_append_only(self):
        delta = self._apply()
        before = RetroPayDelta.objects.count()
        retro.reverse_retro_delta(delta)
        # Original row still present; reversal is a second row.
        self.assertEqual(RetroPayDelta.objects.count(), before + 1)
        self.assertTrue(RetroPayDelta.objects.filter(pk=delta.pk).exists())


class MonthsBetweenTests(TestCase):
    def test_cross_year_boundary(self):
        self.assertEqual(retro._months_between(date(2025, 11, 1), date(2026, 2, 1)), 3)

    def test_same_month_is_zero(self):
        self.assertEqual(retro._months_between(date(2026, 6, 20), date(2026, 6, 1)), 0)

    def test_effective_after_period_is_zero(self):
        self.assertEqual(retro._months_between(date(2026, 7, 1), date(2026, 6, 1)), 0)
