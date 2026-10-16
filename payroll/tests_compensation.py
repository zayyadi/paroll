"""Tests for compensation planning cycles and salary bands (P2-11).

Gap #11 of docs/world_class_employee_management_research_2026-10-14.md:
create -> recommend -> approve -> apply on top of SalaryHistory, plus salary
bands per position.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from company.models import Company
from payroll.models import (
    CompCycle,
    CompReview,
    EmployeeProfile,
    Payroll,
    SalaryBand,
    SalaryHistory,
)
from payroll.services import compensation_service as svc
from tests.approval_helpers import approve_request

CENTS = Decimal("0.01")


def submit_for_approval(review, actor):
    """Drive an approved review's raise through the real approval workflow.

    ``apply_review`` submits the raise as a ``salary.change`` proposal (it
    cannot write the salary inline — the assigned-config guard forbids it). A
    distinct, permissioned checker then approves it, which executes the change
    under a genuine approval context. Returns the refreshed review.
    """
    review, approval = svc.apply_review(review=review, actor=actor)
    from payroll.models import Payroll

    approve_request(approval)
    review.refresh_from_db()
    review.employee.refresh_from_db()
    # The change operation swaps in a *new* Payroll config; rebind the fixture
    # handle so callers can assert on the live config.
    review.live_config = review.employee.employee_pay
    return review


class CompensationFixture(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Comp Co")
        user = get_user_model().objects.create_user(
            email="comp@example.com",
            password="password123",
            first_name="Ada",
            last_name="Lovelace",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=user)
        self.employee.company = self.company
        self.employee.status = "active"
        self.employee.job_title = "M"
        self.employee.save()
        config = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("600000.00")
        )
        self.employee.employee_pay = config
        self.employee.save()
        self.config = config

        self.cycle = svc.create_cycle(
            company=self.company,
            name="2026 review",
            effective_date=date(2026, 9, 1),
            budget_amount=Decimal("120000.00"),
        )

        # Submitter for salary-change proposals. ``approve_request`` supplies
        # its own distinct, permissioned checker at each stage.
        from tests.approval_helpers import approval_user

        self.actor = approval_user(
            self.company, ["payroll.change_payroll"]
        )

    def _review(self, proposed="650000.00"):
        review = svc.add_review(cycle=self.cycle, employee=self.employee)
        return svc.propose_review(
            review=review, proposed_basic=Decimal(proposed)
        )


class CycleLifecycleTests(CompensationFixture):
    def test_create_cycle_defaults_open(self):
        self.assertEqual(self.cycle.status, CompCycle.Status.OPEN)

    def test_negative_budget_rejected(self):
        with self.assertRaises(ValidationError):
            svc.create_cycle(
                company=self.company,
                name="Bad",
                effective_date=date(2026, 9, 1),
                budget_amount=Decimal("-1"),
            )

    def test_add_review_snapshots_current_basic(self):
        review = svc.add_review(cycle=self.cycle, employee=self.employee)
        self.assertEqual(review.current_basic, Decimal("600000.00"))
        self.assertEqual(review.status, CompReview.Status.PROPOSED)

    def test_add_review_requires_salary_config(self):
        user = get_user_model().objects.create_user(
            email="no-config@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = self.company
        employee.save()
        with self.assertRaises(ValidationError):
            svc.add_review(cycle=self.cycle, employee=employee)

    def test_review_only_added_to_open_cycle(self):
        self.cycle.status = CompCycle.Status.APPROVED
        self.cycle.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            svc.add_review(cycle=self.cycle, employee=self.employee)

    def test_full_lifecycle_apply_updates_basic_and_history(self):
        review = self._review()
        self.assertEqual(review.status, CompReview.Status.RECOMMENDED)
        review = svc.approve_review(review=review)
        self.assertEqual(review.status, CompReview.Status.APPROVED)

        review = submit_for_approval(review, actor=self.actor)
        self.assertEqual(review.status, CompReview.Status.APPLIED)
        self.assertIsNotNone(review.applied_at)

        # Live config moved: the salary-change operation swaps in a new,
        # approved config rather than editing the old one in place.
        self.employee.refresh_from_db()
        live = self.employee.employee_pay
        self.assertEqual(live.basic_salary, Decimal("650000.00"))
        self.assertNotEqual(live.pk, self.config.pk)

        # SalaryHistory snapshot written by the approved operation. The
        # EmployeeProfile swap-hook also writes a same-config row dated today;
        # the approved change carries the cycle's effective date.
        history = SalaryHistory.objects.get(
            employee=self.employee,
            salary_config=live,
            effective_date=date(2026, 9, 1),
        )
        self.assertIsNotNone(history.approved_by)

    def test_cycle_status_rolls_up(self):
        review = self._review()
        self.assertEqual(review.cycle.status, CompCycle.Status.RECOMMENDED)
        svc.approve_review(review=review)
        self.assertEqual(review.cycle.status, CompCycle.Status.APPROVED)
        submit_for_approval(review, actor=self.actor)
        self.assertEqual(review.cycle.status, CompCycle.Status.APPLIED)

    def test_increases_and_percent(self):
        review = self._review("660000.00")
        self.assertEqual(review.increase_amount, Decimal("60000.00"))
        self.assertEqual(review.increase_percent, Decimal("10.00"))


class GuardRailTests(CompensationFixture):
    def test_cannot_cut_pay(self):
        review = svc.add_review(cycle=self.cycle, employee=self.employee)
        with self.assertRaises(ValidationError):
            svc.propose_review(
                review=review, proposed_basic=Decimal("500000.00")
            )

    def test_only_recommended_can_be_approved(self):
        review = svc.add_review(cycle=self.cycle, employee=self.employee)
        with self.assertRaises(ValidationError):
            svc.approve_review(review=review)  # still proposed

    def test_only_approved_can_be_applied(self):
        review = self._review()
        with self.assertRaises(ValidationError):
            svc.apply_review(review=review)  # recommended, not approved

    def test_budget_overflow_rejected(self):
        review = self._review("750000.00")  # +150k > 120k budget
        with self.assertRaises(ValidationError):
            svc.approve_review(review=review)
        review.refresh_from_db()
        self.assertEqual(review.status, CompReview.Status.RECOMMENDED)

    def test_budget_within_limit_approved(self):
        review = self._review("700000.00")  # +100k <= 120k
        svc.approve_review(review=review)
        self.assertEqual(review.status, CompReview.Status.APPROVED)

    def test_reject_review(self):
        review = self._review()
        svc.reject_review(review=review, note="Not this year")
        self.assertEqual(review.status, CompReview.Status.REJECTED)
        self.assertEqual(review.cycle.status, CompCycle.Status.CLOSED)

    def test_apply_is_idempotent_guard(self):
        review = self._review()
        svc.approve_review(review=review)
        submit_for_approval(review, actor=self.actor)
        # Once an approval is attached, the raise cannot be re-submitted.
        with self.assertRaises(ValidationError):
            svc.apply_review(review=review, actor=self.actor)

    def test_apply_recomputes_basic_for_net_pay(self):
        # The approved change swaps in a new config whose derived components
        # (net pay, gross, etc.) are recomputed from the raised basic.
        review = self._review()
        svc.approve_review(review=review)
        submit_for_approval(review, actor=self.actor)
        self.employee.refresh_from_db()
        live = self.employee.employee_pay
        self.assertEqual(live.basic_salary, Decimal("650000.00"))
        self.assertGreater(live.gross_income, 0)


class CycleTotalsTests(CompensationFixture):
    def test_totals_sum_increases_and_budget(self):
        self._review("650000.00")
        totals = svc.cycle_totals(self.cycle)
        self.assertEqual(totals["review_count"], 1)
        self.assertEqual(totals["total_increase"], Decimal("50000.00"))
        self.assertEqual(totals["budget"], Decimal("120000.00"))
        self.assertEqual(
            totals["budget_remaining"], Decimal("70000.00")
        )

    def test_unbounded_budget_has_no_remaining(self):
        cycle = svc.create_cycle(
            company=self.company,
            name="No budget",
            effective_date=date(2026, 9, 1),
        )
        totals = svc.cycle_totals(cycle)
        self.assertIsNone(totals["budget_remaining"])


class SalaryBandTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Band Co")

    def _band(self, **overrides):
        defaults = dict(
            company=self.company,
            position_title="M",
            min_salary=Decimal("500000"),
            mid_salary=Decimal("700000"),
            max_salary=Decimal("900000"),
        )
        defaults.update(overrides)
        return SalaryBand.objects.create(**defaults)

    def test_band_ordering_validated(self):
        band = SalaryBand(
            company=self.company,
            position_title="M",
            min_salary=Decimal("900000"),
            mid_salary=Decimal("700000"),
            max_salary=Decimal("500000"),
        )
        with self.assertRaises(ValidationError):
            band.full_clean()

    def test_contains(self):
        band = self._band()
        self.assertTrue(band.contains(Decimal("600000")))
        self.assertFalse(band.contains(Decimal("450000")))
        self.assertFalse(band.contains(Decimal("950000")))

    def test_review_within_band_property(self):
        user = get_user_model().objects.create_user(
            email="band@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = self.company
        employee.job_title = "M"
        employee.save()
        config = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("600000")
        )
        employee.employee_pay = config
        employee.save()

        self._band()
        cycle = svc.create_cycle(
            company=self.company,
            name="Band cycle",
            effective_date=date(2026, 9, 1),
        )
        review = svc.add_review(cycle=cycle, employee=employee)
        svc.propose_review(
            review=review, proposed_basic=Decimal("800000")
        )
        self.assertTrue(review.within_band)

        svc.propose_review(
            review=review, proposed_basic=Decimal("1000000")
        )
        self.assertFalse(review.within_band)

    def test_review_without_band_is_none(self):
        user = get_user_model().objects.create_user(
            email="noband@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = self.company
        employee.job_title = "JS"
        employee.save()
        config = Payroll.objects.create(
            company=self.company, basic_salary=Decimal("200000")
        )
        employee.employee_pay = config
        employee.save()
        cycle = svc.create_cycle(
            company=self.company,
            name="No band cycle",
            effective_date=date(2026, 9, 1),
        )
        review = svc.add_review(cycle=cycle, employee=employee)
        self.assertIsNone(review.within_band)
